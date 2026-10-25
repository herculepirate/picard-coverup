# -*- coding: utf-8 -*-
"""Test helpers: synthetic images (Qt) and a fake HTTP client serving canned responses."""

from __future__ import annotations

import json
import threading

from coverup.net import HttpClient, HttpError, Response


def make_image(pattern: str = "a", size: int = 600, fmt: str = "jpeg", w: int | None = None, h: int | None = None) -> bytes:
    from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF
    from PyQt6.QtGui import QColor, QImage, QPainter

    w, h = w or size, h or size
    img = QImage(w, h, QImage.Format.Format_RGB32)
    p = QPainter(img)
    if pattern == "a":  # horizontal gradient bars
        for x in range(w):
            v = int(255 * x / max(1, w - 1))
            p.setPen(QColor(v, 80, 255 - v))
            p.drawLine(x, 0, x, h)
    elif pattern == "b":  # checkerboard
        step = max(4, w // 8)
        for y in range(0, h, step):
            for x in range(0, w, step):
                p.fillRect(QRectF(x, y, step, step), QColor("white") if ((x // step + y // step) % 2) else QColor("black"))
    elif pattern == "c":  # circles
        img.fill(QColor("#203040"))
        p.setBrush(QColor("#f0c040"))
        for i in range(5):
            p.drawEllipse(QPointF(w * (i + 1) / 6, h / 2 + (i % 2) * h / 5), w / 10, w / 10)
    elif pattern == "blank":
        img.fill(QColor("#808080"))
    p.end()
    buf = QByteArray()
    dev = QBuffer(buf)
    dev.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(dev, "JPEG" if fmt == "jpeg" else "PNG", 90)
    dev.close()
    return bytes(buf.data())


class FakeHttp(HttpClient):
    """Routes requests by exact URL or by prefix to bytes / JSON-able objects / HttpError status codes.

    A route may also be a ``Response`` (served as is) or a callable taking the URL and returning any of those,
    for multi-step APIs. Every request's method, URL and headers are recorded in ``sent``."""

    def __init__(self, routes: dict[str, object] | None = None):
        super().__init__(version="test", cache_dir=None)
        self.routes = dict(routes or {})
        self.calls: list[str] = []
        self.posts: list[tuple[str, object]] = []
        self.deletes: list[str] = []
        self.sent: list[tuple[str, str, dict]] = []
        self.lock = threading.Lock()

    def _lookup(self, url: str):
        if url in self.routes:
            val = self.routes[url]
        else:
            best = None
            for k in self.routes:
                if url.startswith(k) and (best is None or len(k) > len(best)):
                    best = k
            if best is None:
                raise HttpError(404, url)
            val = self.routes[best]
        return val(url) if callable(val) else val

    def _respond(self, url: str) -> Response:
        val = self._lookup(url)
        if isinstance(val, Response):
            return val
        if isinstance(val, int):
            raise HttpError(val, url)
        if isinstance(val, (bytes, bytearray)):
            data = bytes(val)
            ctype = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg" if data[:2] == b"\xff\xd8" else "application/octet-stream"
            return Response(url, 200, data, {"content-type": ctype})
        return Response(url, 200, json.dumps(val).encode("utf-8"), {"content-type": "application/json"})

    def get(self, url, headers=None, cache=True, max_bytes=0, range_bytes=None):
        with self.lock:
            self.calls.append(url)
            self.sent.append(("GET", url, dict(headers or {})))
        resp = self._respond(url)
        if range_bytes:
            resp = Response(url, resp.status, resp.data[:range_bytes], resp.headers)
        return resp

    def post_json(self, url, payload, headers=None, timeout=None):
        self.posts.append((url, payload))
        self.sent.append(("POST", url, dict(headers or {})))
        val = self._lookup(url)
        if isinstance(val, int):
            raise HttpError(val, url)
        return val

    def post(self, url, payload, headers=None, timeout=None):
        self.posts.append((url, payload))
        self.sent.append(("POST", url, dict(headers or {})))
        return self._respond(url)

    def delete(self, url, headers=None, timeout=None, force=False):
        self.deletes.append(url)
        self.sent.append(("DELETE", url, dict(headers or {})))
        return self._respond(url)
