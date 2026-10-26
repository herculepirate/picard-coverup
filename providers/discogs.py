# -*- coding: utf-8 -*-
# CoverUp: MusicBrainz Picard plugin. GPL-2.0-or-later.
"""Discogs: images of the exact Discogs release.

The release is found, in order of trust, from the MusicBrainz URL relationship, a barcode search, a
catalogue-number search, then an artist/title search. Search hits are only treated as the exact release
(tier A) when the release-match confidence is high; otherwise their images are tier C.
"""

from __future__ import annotations

import re
import urllib.parse

from ..model import ArtType, Candidate, Query, Tier
from ..net import HttpError
from .base import Provider, matches, normalize

API = "https://api.discogs.com"
CONFIDENT = 0.75


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def release_confidence(q: Query, rel: dict) -> tuple[float, list[str]]:
    """How likely a Discogs release JSON is the tagged release. Returns (0..1, reasons)."""
    score = 0.0
    weight = 0.0
    reasons: list[str] = []

    def check(ok: bool | None, w: float, label: str) -> None:
        nonlocal score, weight
        if ok is None:
            return
        weight += w
        if ok:
            score += w
            reasons.append(f"{label} matches")
        else:
            reasons.append(f"{label} differs")

    artists = " ".join(a.get("name", "") for a in rel.get("artists") or [])
    check(matches(q, re.sub(r"\s*\(\d+\)", "", artists), rel.get("title", "")) > 0, 3.0, "artist/title")
    barcodes = {_digits(i.get("value", "")) for i in rel.get("identifiers") or [] if i.get("type") == "Barcode"}
    check((_digits(q.barcode) in barcodes) if q.barcode and barcodes else None, 3.0, "barcode")
    catnos = {normalize(lab.get("catno", "")).replace(" ", "") for lab in rel.get("labels") or []}
    check((normalize(q.catalog_number).replace(" ", "") in catnos) if q.catalog_number and catnos else None, 2.0, "catalogue number")
    tracks = [t for t in rel.get("tracklist") or [] if t.get("type_", "track") == "track"]
    check((abs(len(tracks) - q.track_count) <= 1) if q.track_count and tracks else None, 1.5, "track count")
    qty = sum(int(f.get("qty") or 1) for f in rel.get("formats") or [] if f.get("name") not in ("All Media",))
    check((qty == q.medium_count) if q.medium_count and qty else None, 1.0, "medium count")
    check((int(rel.get("year") or 0) == q.year) if q.year and rel.get("year") else None, 1.0, "year")
    check((rel.get("country", "").lower()[:2] == q.country.lower()[:2]) if q.country and rel.get("country") else None, 0.5, "country")
    return (score / weight if weight else 0.0), reasons


def parse_release_images(rel: dict, tier: Tier) -> list[Candidate]:
    out: list[Candidate] = []
    rid = rel.get("id")
    for i, img in enumerate(rel.get("images") or []):
        url = img.get("uri") or img.get("resource_url") or ""
        if not url:
            continue
        primary = img.get("type") == "primary"
        out.append(
            Candidate(
                provider="discogs",
                provider_id=f"{rid}:{i}",
                url=url,
                # Discogs does not label secondary images (back, disc, booklet...): they are offered for
                # manual choice in the dialog but never auto-selected for a specific type.
                art_type=ArtType.FRONT if primary else ArtType.OTHER,
                tier=tier,
                width=int(img.get("width") or 0),
                height=int(img.get("height") or 0),
                dims_known=bool(img.get("width") and img.get("height")),
                thumb_url=img.get("uri150") or url,
                type_confidence=0.9 if primary else 0.3,
                attribution=f"Discogs release {rid}",
                page=i,
            )
        )
    return out


def parse_artist_images(artist: dict, tier: Tier) -> list[Candidate]:
    """Photos on a Discogs artist page. The first ('primary') image is the one Discogs shows as the artist's face."""
    out: list[Candidate] = []
    aid = artist.get("id")
    name = re.sub(r"\s*\(\d+\)$", "", artist.get("name", ""))  # Discogs numbers namesakes: "Genesis (2)"
    for i, img in enumerate(artist.get("images") or []):
        url = img.get("uri") or img.get("resource_url") or ""
        if not url:
            continue
        primary = img.get("type") == "primary"
        c = Candidate(
            provider="discogs",
            provider_id=f"artist:{aid}:{i}",
            url=url,
            art_type=ArtType.ARTIST_THUMB,
            tier=tier,
            width=int(img.get("width") or 0),
            height=int(img.get("height") or 0),
            dims_known=bool(img.get("width") and img.get("height")),
            thumb_url=img.get("uri150") or url,
            type_confidence=0.9 if primary else 0.6,
            attribution=f"Discogs artist {aid}",
            comment=f"Discogs artist: {name}",
            page=i,
        )
        out.append(c)
    return out


class Discogs(Provider):
    ID = "discogs"
    NAME = "Discogs"
    NEEDS_KEY = True

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Discogs token={self.settings['discogs_token']}"}

    def available(self) -> tuple[bool, str]:
        if not self.settings["discogs_token"]:
            return False, "Discogs needs a personal access token (Options > CoverUp > Sources)"
        return True, ""

    def release(self, rid: int) -> dict:
        return self.http.get_json(f"{API}/releases/{int(rid)}", self._headers())

    def _search(self, **params: str) -> list[dict]:
        params = {k: v for k, v in params.items() if v}
        params.update({"type": "release", "per_page": "10"})
        url = f"{API}/database/search?{urllib.parse.urlencode(params)}"
        return (self.http.get_json(url, self._headers()) or {}).get("results") or []

    def find_release(self, q: Query) -> tuple[dict | None, float, str]:
        """Return (release JSON, confidence, how it was found). When nothing is found because
        Discogs failed (not "not found"), the failure is raised: an outage is reported as an
        error, never as "0 found"."""
        failed: HttpError | None = None
        if q.discogs_release_id:
            try:
                return self.release(q.discogs_release_id), 1.0, "MusicBrainz URL relationship"
            except HttpError as exc:
                self.log.warning("Linked Discogs release %s failed: %s", q.discogs_release_id, exc)
                if exc.status != 404:
                    failed = exc
        attempts = []
        if q.barcode:
            attempts.append(("barcode", {"barcode": _digits(q.barcode)}))
        if q.catalog_number:
            attempts.append(("catalogue number", {"catno": q.catalog_number, "artist": q.artist}))
        if q.artist and q.album:
            attempts.append(("artist/title search", {"artist": q.artist, "release_title": q.album}))
        best: tuple[dict | None, float, str] = (None, 0.0, "")
        for how, params in attempts:
            for hit in self._search(**params)[:5]:
                try:
                    rel = self.release(hit["id"])
                except KeyError:
                    continue
                except HttpError as exc:
                    if exc.status != 404:
                        failed = exc
                    continue
                conf, reasons = release_confidence(q, rel)
                self.log.debug("Discogs candidate %s via %s: confidence %.2f (%s)", hit.get("id"), how, conf, "; ".join(reasons))
                if conf > best[1]:
                    best = (rel, conf, how)
                if conf >= 0.95:
                    return best
            if best[1] >= CONFIDENT:
                return best
        if best[0] is None and failed is not None:
            raise failed
        return best

    def search(self, q: Query) -> list[Candidate]:
        rel, conf, how = self.find_release(q)
        if not rel:
            self.log.info("No Discogs release found")
            return []
        tier = Tier.A if conf >= CONFIDENT else Tier.C
        self.log.info("Discogs release %s found via %s (confidence %.2f, tier %s)", rel.get("id"), how, conf, tier.value)
        cands = parse_release_images(rel, tier)
        for c in cands:
            c.extra["discogs_confidence"] = round(conf, 2)
            c.extra["discogs_found_via"] = how
        if self.wants_artist_art(q):
            cands += self.artist_images(q, rel, tier)
        return cands

    def artist_images(self, q: Query, rel: dict, tier: Tier) -> list[Candidate]:
        """Photos from the Discogs page of the release's main artist (never for 'Various')."""
        artists = [a for a in rel.get("artists") or [] if a.get("id") and a.get("name", "").lower() not in ("various", "various artists")]
        if not artists:
            return []
        try:
            artist = self.http.get_json(f"{API}/artists/{int(artists[0]['id'])}", self._headers())
        except HttpError as exc:
            self.log.warning("Discogs artist %s failed: %s", artists[0].get("id"), exc)
            return []
        # the release's artist is the right person even when the tagged name is spelled differently,
        # but only trust it as exact (tier A) when the release itself was an exact match
        out = parse_artist_images(artist or {}, tier)[:5]
        self.log.info("Discogs artist %s: %d image(s)", artists[0].get("id"), len(out))
        return out
