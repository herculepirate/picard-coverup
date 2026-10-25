# -*- coding: utf-8 -*-
# CoverUp: MusicBrainz Picard plugin. GPL-2.0-or-later.
"""All user settings: defaults, typed access and conversion from Picard's plugin config.

This is the single source of truth for option names and defaults. ``enable()`` registers every key in
``DEFAULTS`` with Picard, and the pipeline reads a ``Settings`` object built from them. Pure Python.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

from .model import ArtType

SETTINGS_VERSION = 3

# Defaults that changed between settings versions: (version introduced, key, old default, new default).
# A user still on the old default gets the new one; anything they chose themselves is kept.
CHANGED_DEFAULTS = [
    (2, "apply_types", ["front"], ["front", "back", "disc", "booklet"]),
    (2, "prefer_largest", False, True),
    (2, "apply_min_side", 500, 600),
    (2, "jpeg_quality", 92, 95),
    (2, "record_source_in_comment", True, False),
    (2, "min_back", 300, 500),
    (2, "min_disc", 300, 500),
    (2, "min_booklet", 300, 500),
    (2, "min_artist", 300, 500),
    # 3: artist photos are collected by default, and Wikimedia Commons (no key) is searched
    (3, "apply_types", ["front", "back", "disc", "booklet"], ["front", "back", "disc", "booklet", "artist"]),
    (3, "providers_enabled", ["caa", "discogs", "fanart", "audiodb", "itunes", "deezer", "local"],
     ["caa", "discogs", "wikimedia", "fanart", "audiodb", "itunes", "deezer", "local"]),
]

# Embed choices offered in the dialog and options
EMBED_CHOICES = [
    (["front"], "Front cover only"),
    (["front", "back"], "Front and back"),
    (["front", "back", "disc", "booklet"], "Everything chosen"),
    ([], "Nothing (files only)"),
]

# Provider ids, in default query order
PROVIDERS = ("caa", "discogs", "wikimedia", "fanart", "audiodb", "itunes", "deezer", "lastfm", "websearch", "local")

PROVIDER_LABELS = {
    "caa": "Cover Art Archive (MusicBrainz)",
    "discogs": "Discogs",
    "wikimedia": "Wikimedia Commons (artist photos and logos, no key)",
    "fanart": "Fanart.tv",
    "audiodb": "TheAudioDB",
    "itunes": "Apple Music (iTunes)",
    "deezer": "Deezer",
    "lastfm": "Last.fm",
    "websearch": "Web image search (paid API key)",
    "local": "Local files in the album folder",
}

# Secret option names (masked in logs and diagnostics bundles)
SECRET_KEYS = (
    "discogs_token",
    "fanart_api_key",
    "fanart_client_key",
    "audiodb_api_key",
    "lastfm_api_key",
    "websearch_api_key",
    "ai_api_key",
    "ai_cf_account_id",
    "ai_cf_api_token",
    "ai_horde_api_key",
)

# Public keys that are safe to show and pointless to mask
PUBLIC_KEYS = {"123": "public test key", "0000000000": "anonymous key"}

# Cloudflare Workers AI text-to-image models offered in Options (any other model ID can be typed in)
CLOUDFLARE_MODELS = (
    ("@cf/black-forest-labs/flux-1-schnell", "FLUX.1 schnell (fast, cheapest)"),
    ("@cf/stabilityai/stable-diffusion-xl-base-1.0", "Stable Diffusion XL base 1.0"),
    ("@cf/bytedance/stable-diffusion-xl-lightning", "SDXL Lightning (ByteDance)"),
    ("@cf/leonardo/lucid-origin", "Leonardo Lucid Origin (costly: over 2,000 neurons a cover)"),
    ("@cf/leonardo/phoenix-1.0", "Leonardo Phoenix 1.0 (costly: over 2,000 neurons a cover)"),
)

DEFAULTS: dict[str, Any] = {
    # ---- sources ----
    "providers_enabled": ["caa", "discogs", "wikimedia", "fanart", "audiodb", "itunes", "deezer", "local"],
    "provider_order": list(PROVIDERS),
    "discogs_token": "",
    "fanart_api_key": "",
    "fanart_client_key": "",
    "audiodb_api_key": "123",  # TheAudioDB public test key (limited rate)
    "lastfm_api_key": "",
    "websearch_engine": "brave",  # brave | google
    "websearch_api_key": "",
    "websearch_google_cx": "",
    "http_cache_hours": 24,
    "max_candidates_per_provider": 12,
    # ---- matching ----
    "hamming_threshold": 10,
    "conflict_min_sources": 3,
    "auto_apply_mode": "confident",  # confident | never
    # ---- art types ----
    "apply_types": ["front", "back", "disc", "booklet", "artist"],  # collected by default (dialog and auto-apply)
    "artist_art": True,  # look for artist images at all
    "artist_types": ["thumb"],  # which artist images are pre-selected: thumb | logo | background | banner
    # ---- resolution (search limits, per type) ----
    "min_front": 500,
    "min_back": 500,
    "min_disc": 500,
    "min_booklet": 500,
    "min_artist": 500,
    "max_side": 0,  # 0 = no maximum
    "target_size": 1200,
    "prefer_largest": True,  # collectors want the best scan available
    "front_aspect_tolerance": 0.05,
    "max_file_mb": 25,
    # ---- resolution (apply limits) ----
    "apply_min_side": 600,  # below this, art is not applied (and can trigger the creative fallback)
    "embed_max_side": 1200,
    "file_max_side": 0,  # 0 = keep original size
    "upscale_to_minimum": False,
    # ---- output ----
    "embed": True,
    "embed_types": ["front"],  # which chosen types go into tags; the rest are saved as files only
    "save_files": True,
    "folder_mode": "subfolder",  # same | subfolder
    "folder_name": "covers",
    "front_in_album_folder": True,  # per-type routing: front cover also as <album>/cover.jpg
    "naming_preset": "default",  # default | kodi | plex | custom
    "name_front": "cover",
    "name_back": "back",
    "name_disc": "disc{discnumber}",
    "name_booklet": "booklet-{n}",
    "name_artist_thumb": "artist",
    "name_artist_logo": "logo",
    "name_artist_background": "fanart",
    "name_artist_banner": "banner",
    "save_artist_art": True,  # write artist images into the artist folder (parent of the album folder)
    "jpeg_quality": 95,
    "collision_policy": "if_better",  # skip | overwrite | if_better | keep_both
    "backups": True,
    "write_files_when": "on_save",  # on_save | immediately
    "multi_folder": "every",  # every | first   (albums whose discs are in separate folders)
    "replace_embedded": True,  # remove existing embedded images of the applied types first
    "record_source_in_comment": False,  # provenance goes to coverup.json, keeping tags clean
    "write_sidecar": True,  # coverup.json next to written files
    # ---- creative / AI ----
    "creative_triggers": [],  # any of: no_cover, below_min, low_confidence
    "creative_always": False,
    "creative_method_order": ["fanart", "ai", "template"],
    "creative_template": "art",
    "creative_custom_prompt": 'Album cover artwork for "{album}" by {artist}, {genre}, {era}. No text, no letters.',
    "creative_match_era": True,
    "creative_match_genre": True,
    "creative_variations": 4,
    "creative_overlay_logo": True,
    "creative_overlay_title": True,
    "creative_logo_position": "top",  # top | center | bottom
    "creative_max_per_run": 20,
    "ai_backend": "none",  # none | automatic1111 | openai | custom | cloudflare | aihorde
    "ai_url": "http://127.0.0.1:7860",
    "ai_model": "",
    "ai_api_key": "",
    "ai_size": 1024,
    "ai_steps": 30,
    "ai_img2img": False,  # send the low-resolution cover as a reference (local backends only by default)
    "ai_allow_remote_reference": False,
    "ai_consented_hosts": [],
    # Cloudflare Workers AI (free daily allowance on a free Cloudflare account)
    "ai_cf_account_id": "",
    "ai_cf_api_token": "",
    "ai_cf_model": "@cf/black-forest-labs/flux-1-schnell",
    "ai_cf_steps": 4,  # FLUX.1 schnell allows 1..8
    # AI Horde (crowdsourced; the anonymous key works, a registered key gets priority)
    "ai_horde_api_key": "0000000000",
    "ai_horde_model": "AlbedoBase XL (SDXL)",
    "ai_horde_max_wait": 300,  # seconds before the request is cancelled
    "logo_choices": "{}",  # JSON text: artist MBID -> chosen logo URL (text keeps Picard's config simple)
    # ---- logging ----
    "log_mode": "fixed",  # fixed | total | age | session | off
    "log_max_mb": 2,
    "log_backups": 3,
    "log_total_cap_mb": 25,
    "log_retain_days": 14,
    "log_sessions_keep": 5,
    "log_level": "INFO",
    "log_anonymise": False,
    "log_folder": "",  # empty = default under Picard's cache folder
    "settings_version": 0,
}

NAMING_PRESETS: dict[str, dict[str, str]] = {
    "default": {
        "name_front": "cover",
        "name_back": "back",
        "name_disc": "disc{discnumber}",
        "name_booklet": "booklet-{n}",
        "name_artist_thumb": "artist",
        "name_artist_logo": "logo",
        "name_artist_background": "fanart",
        "name_artist_banner": "banner",
    },
    # Kodi / Jellyfin / Emby conventions (Navidrome also reads cover.* and folder.*)
    "kodi": {
        "name_front": "folder",
        "name_back": "back",
        "name_disc": "cdart{discnumber}",
        "name_booklet": "booklet-{n}",
        "name_artist_thumb": "folder",
        "name_artist_logo": "logo",
        "name_artist_background": "fanart",
        "name_artist_banner": "banner",
    },
    "plex": {
        "name_front": "cover",
        "name_back": "back",
        "name_disc": "disc{discnumber}",
        "name_booklet": "booklet-{n}",
        "name_artist_thumb": "artist",
        "name_artist_logo": "logo",
        "name_artist_background": "background",
        "name_artist_banner": "banner",
    },
}

ART_TYPE_NAME_KEY = {
    ArtType.FRONT: "name_front",
    ArtType.BACK: "name_back",
    ArtType.DISC: "name_disc",
    ArtType.BOOKLET: "name_booklet",
    ArtType.ARTIST_THUMB: "name_artist_thumb",
    ArtType.ARTIST_LOGO: "name_artist_logo",
    ArtType.ARTIST_BACKGROUND: "name_artist_background",
    ArtType.ARTIST_BANNER: "name_artist_banner",
}

ARTIST_TYPES = (ArtType.ARTIST_THUMB, ArtType.ARTIST_LOGO, ArtType.ARTIST_BACKGROUND, ArtType.ARTIST_BANNER)
ARTIST_TYPE_KEYS = {
    "thumb": ArtType.ARTIST_THUMB,
    "logo": ArtType.ARTIST_LOGO,
    "background": ArtType.ARTIST_BACKGROUND,
    "banner": ArtType.ARTIST_BANNER,
}

# What "artist" means in the type checklist
TYPE_GROUPS = {
    "front": (ArtType.FRONT,),
    "back": (ArtType.BACK,),
    "disc": (ArtType.DISC,),
    "booklet": (ArtType.BOOKLET,),
    "artist": ARTIST_TYPES,
}


@dataclass
class Settings:
    values: dict[str, Any] = field(default_factory=lambda: dict(DEFAULTS))

    @classmethod
    def from_mapping(cls, config: Mapping[str, Any] | None) -> "Settings":
        """Build from Picard's plugin_config (or any mapping). Unknown or missing keys use defaults."""
        vals = dict(DEFAULTS)
        if config is not None:
            for key in DEFAULTS:
                try:
                    v = config[key]
                except (KeyError, TypeError):
                    continue
                if v is not None:
                    vals[key] = v
        return cls(vals)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]

    def with_(self, **overrides: Any) -> "Settings":
        """A copy with some values replaced (per-run choices made in the dialog)."""
        return Settings(dict(self.values, **overrides))

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    # ---- typed helpers ----
    def enabled_providers(self) -> list[str]:
        enabled = set(self.values["providers_enabled"])
        order = [p for p in self.values["provider_order"] if p in PROVIDERS]
        order += [p for p in PROVIDERS if p not in order]
        return [p for p in order if p in enabled]

    def secrets(self) -> list[str]:
        return [str(self.values[k]) for k in SECRET_KEYS if self.values.get(k) and str(self.values[k]) not in PUBLIC_KEYS]

    def name_template(self, art_type: ArtType) -> str:
        key = ART_TYPE_NAME_KEY.get(art_type)
        if not key:
            return art_type.value
        preset = self.values.get("naming_preset", "default")
        if preset in NAMING_PRESETS:
            return NAMING_PRESETS[preset][key]
        return str(self.values.get(key) or DEFAULTS[key])

    def artist_art_types(self) -> set[ArtType]:
        """Artist image kinds that are pre-selected (empty when artist images are switched off)."""
        if not self.values.get("artist_art"):
            return set()
        return {ARTIST_TYPE_KEYS[k] for k in self.values.get("artist_types") or [] if k in ARTIST_TYPE_KEYS}

    def apply_art_types(self) -> set[ArtType]:
        out: set[ArtType] = set()
        for group in self.values["apply_types"]:
            if group == "artist":
                out.update(self.artist_art_types())
            else:
                out.update(TYPE_GROUPS.get(group, ()))
        return out

    def embed_art_types(self) -> set[ArtType]:
        out: set[ArtType] = set()
        for group in self.values.get("embed_types") or []:
            out.update(TYPE_GROUPS.get(group, ()))
        return out

    def min_side_for(self, art_type: ArtType) -> int:
        if art_type == ArtType.FRONT:
            return int(self.values["min_front"])
        if art_type == ArtType.BACK:
            return int(self.values["min_back"])
        if art_type == ArtType.DISC:
            return int(self.values["min_disc"])
        if art_type == ArtType.BOOKLET:
            return int(self.values["min_booklet"])
        return int(self.values["min_artist"])

    def logo_choice(self, artist_mbid: str) -> str | None:
        return _json_dict(self.values.get("logo_choices")).get(artist_mbid) if artist_mbid else None

    def with_logo_choice(self, artist_mbid: str, url: str) -> str:
        """Return the updated JSON text for ``logo_choices``."""
        d = _json_dict(self.values.get("logo_choices"))
        d[artist_mbid] = url
        return json.dumps(d)

    def redacted(self) -> dict[str, Any]:
        """Settings safe to export (keys replaced by set/unset markers)."""
        out = {}
        for k, v in self.values.items():
            if k in SECRET_KEYS:
                out[k] = PUBLIC_KEYS.get(str(v)) or ("***set***" if v else "***unset***")
            else:
                out[k] = v
        return out


def _json_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return dict(value)
    try:
        d = json.loads(value or "{}")
        return d if isinstance(d, dict) else {}
    except (TypeError, ValueError):
        return {}


def migrate(config) -> list[str]:
    """Bring a stored plugin config up to SETTINGS_VERSION. Returns the keys that changed."""
    try:
        version = int(config["settings_version"] or 0)
    except (KeyError, TypeError, ValueError):
        version = 0
    changed = []
    for introduced, key, old, new in CHANGED_DEFAULTS:
        if version < introduced:
            try:
                current = config[key]
            except KeyError:
                current = old
            if current == old or (isinstance(old, list) and list(current or []) == old):
                config[key] = new
                changed.append(key)
    config["settings_version"] = SETTINGS_VERSION
    return changed
