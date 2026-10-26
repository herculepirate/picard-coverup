# -*- coding: utf-8 -*-
# CoverUp: MusicBrainz Picard plugin. GPL-2.0-or-later.
"""Wikimedia Commons: artist photos and logos, reached through the artist's own MusicBrainz links.

No key is needed. MusicBrainz lists the artist's Wikidata page (and sometimes a Commons file) among its
links; Wikidata names the artist's photo (property P18) and logo (P154); Commons gives the file, its real
size and its licence. Because the link comes from the tagged artist's MBID, these are exact matches (tier A).
Everything here is freely licensed or public domain, and the licence is shown in the review window.
"""

from __future__ import annotations

import html
import re
import urllib.parse

from ..model import ArtType, Candidate, Query, Tier
from ..net import HttpError
from .base import Provider
from .musicbrainz import is_mbid

MB_ARTIST = "https://musicbrainz.org/ws/2/artist/{mbid}?inc=url-rels&fmt=json"
WIKIDATA = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"

_QID = re.compile(r"wikidata\.org/(?:wiki|entity)/(Q\d+)", re.IGNORECASE)
_COMMONS_FILE = re.compile(r"commons\.wikimedia\.org/wiki/File:(.+)$", re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")
RASTER = ("image/jpeg", "image/png", "image/webp", "image/gif")

# Wikidata property -> (artist image kind, how sure we are of the kind)
PROPERTIES = (("P18", ArtType.ARTIST_THUMB, 0.9), ("P154", ArtType.ARTIST_LOGO, 0.8))


def relations(payload: dict) -> tuple[str | None, list[str]]:
    """(Wikidata id, Commons file names) from a MusicBrainz artist's URL relationships."""
    qid = None
    files: list[str] = []
    for rel in (payload or {}).get("relations") or []:
        resource = (rel.get("url") or {}).get("resource", "")
        if rel.get("type") == "wikidata":
            m = _QID.search(resource)
            if m:
                qid = m.group(1).upper()
        elif rel.get("type") in ("image", "logo"):
            m = _COMMONS_FILE.search(resource)
            if m:
                files.append(urllib.parse.unquote(m.group(1)).replace("_", " "))
    return qid, files


def claim_files(entity_json: dict, qid: str) -> list[tuple[str, ArtType, float]]:
    """File names of the photo and logo claims of a Wikidata entity."""
    entity = ((entity_json or {}).get("entities") or {}).get(qid) or {}
    out: list[tuple[str, ArtType, float]] = []
    for prop, art, conf in PROPERTIES:
        for claim in (entity.get("claims") or {}).get(prop) or []:
            value = ((claim.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(value, str) and value:
                # a 'preferred' claim is the one Wikipedia shows first
                out.append((value, art, conf + (0.05 if claim.get("rank") == "preferred" else 0.0)))
    return out


def _plain(value: str) -> str:
    return html.unescape(_TAGS.sub("", value or "")).strip()


def parse_imageinfo(payload: dict, filename: str, art: ArtType, conf: float) -> Candidate | None:
    """A Candidate from Commons' imageinfo answer, or None for non-images (audio, video, PDF)."""
    pages = ((payload or {}).get("query") or {}).get("pages") or {}
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        if not info or info.get("mime") not in RASTER + ("image/svg+xml",):
            continue
        width, height = int(info.get("width") or 0), int(info.get("height") or 0)
        if info.get("mime") == "image/svg+xml":
            # vector logos are fetched as a PNG rendering at a useful size
            url = info.get("thumburl") or ""
            if not url:
                continue
            width, height = int(info.get("thumbwidth") or 0), int(info.get("thumbheight") or 0)
        else:
            url = info.get("url") or ""
        if not url:
            continue
        meta = info.get("extmetadata") or {}
        licence = _plain((meta.get("LicenseShortName") or {}).get("value", ""))
        author = _plain((meta.get("Artist") or {}).get("value", ""))[:80]
        c = Candidate(
            provider="wikimedia",
            provider_id=filename,
            url=url,
            art_type=art,
            tier=Tier.A,
            width=width,
            height=height,
            dims_known=bool(width and height),
            bytes=int(info.get("size") or 0),
            thumb_url=info.get("thumburl") or url,
            type_confidence=conf,
            attribution="Wikimedia Commons",
            comment=", ".join(x for x in (f"File:{filename}", licence, author) if x),
        )
        c.extra["licence"] = licence
        return c
    return None


class Wikimedia(Provider):
    ID = "wikimedia"
    NAME = "Wikimedia Commons"

    def _imageinfo(self, filename: str, svg_width: int = 800) -> dict:
        params = {
            "action": "query", "format": "json", "prop": "imageinfo", "titles": f"File:{filename}",
            "iiprop": "url|size|mime|extmetadata", "iiurlwidth": svg_width,
        }
        return self.http.get_json(f"{COMMONS_API}?{urllib.parse.urlencode(params)}") or {}

    def search(self, q: Query) -> list[Candidate]:
        if not self.wants_artist_art(q) or not is_mbid(q.artist_mbid):
            return []
        # A service that fails (not "not found") is raised, so the run reports an error for this
        # source instead of "0 found" - an outage must never look like an artist without photos
        failed: HttpError | None = None
        try:
            qid, linked_files = relations(self.http.get_json(MB_ARTIST.format(mbid=q.artist_mbid)))
        except HttpError as exc:
            if exc.status == 404:
                self.log.info("MusicBrainz has no artist %s", q.artist_mbid)
                return []
            raise
        wanted: list[tuple[str, ArtType, float]] = [(f, ArtType.ARTIST_THUMB, 0.8) for f in linked_files]
        if qid:
            try:
                wanted += claim_files(self.http.get_json(WIKIDATA.format(qid=qid)), qid)
            except HttpError as exc:
                self.log.warning("Wikidata %s failed: %s", qid, exc)
                if exc.status != 404:
                    failed = exc
        out: list[Candidate] = []
        seen: set[str] = set()
        for filename, art, conf in wanted:
            if filename in seen or len(out) >= 6:
                continue
            seen.add(filename)
            try:
                c = parse_imageinfo(self._imageinfo(filename), filename, art, conf)
            except HttpError as exc:
                self.log.warning("Commons file %s failed: %s", filename, exc)
                if exc.status != 404:
                    failed = exc
                continue
            if c is not None:
                out.append(c)
        if not out and failed is not None:
            raise failed
        self.log.info("Wikimedia Commons: %d artist image(s) via %s", len(out), qid or "MusicBrainz link")
        return out
