# -*- coding: utf-8 -*-
# CoverUp: MusicBrainz Picard plugin. GPL-2.0-or-later.
"""Options > Plugins > CoverUp.

Progressive disclosure: the first tab holds what most people change (what to collect and where it goes);
quality, sources, creating covers and the fine-tuning each get their own tab, with tuning last.
Layout rules (KDE HIG): right-aligned labels in forms, checkboxes carry their own text, radio buttons for
two or three choices, combo boxes for more, headings instead of nested frames, frameless tabs.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from ..apply.files import FOLDER_PRESETS, validate_folder_name
from ..settings import CLOUDFLARE_MODELS, DEFAULTS, EMBED_CHOICES, NAMING_PRESETS, PROVIDER_LABELS, PROVIDERS

log = logging.getLogger("coverup.ui")

C = lambda *pairs: list(pairs)  # noqa: E731

ALBUM_FOLDER = "__album__"
OTHER_FOLDER = "__other__"
NO_FILES = "__none__"

# A field: (key, label, kind, options, help)
#   kinds: bool, int, float, text, password, choice, radio, multi, order, template,
#          embed (embed + embed_types), folder (save_files + folder_mode + folder_name), providers,
#          suggest (editable combo: pick a suggested value or type your own; options are (value, tooltip))
#   int/float options: (min, max, suffix)
H = "heading"
LAYOUT: dict[str, list[tuple]] = {
    "General": [
        (H, "What to collect"),
        ("apply_types", "Art types", "multi", C(("front", "Front cover"), ("back", "Back cover"), ("disc", "Disc art"), ("booklet", "Booklet pages"), ("artist", "Artist images")),
         "Ticked types are pre-selected in the review dialog and used by Auto-apply."),
        (H, "Where it goes"),
        ("embed_types", "Embed in tags", "embed", None, "Big scans make every track file bigger. Collectors usually embed the front and keep the rest as files."),
        ("folder", "Save files to", "folder", None, None),
        ("front_in_album_folder", "Also save the front cover beside the tracks", "bool", None, "Players and media servers (Navidrome, Plex, Jellyfin) look for cover.jpg or folder.jpg there."),
        ("write_files_when", "Write files", "radio", C(("on_save", "When the album is saved in Picard (follows renames and moves)"), ("immediately", "Straight away")), None),
        ("naming_preset", "File names", "choice", C(("default", "cover, back, disc1, booklet-01"), ("kodi", "Kodi and Jellyfin: folder, back, cdart1"), ("plex", "Plex: cover, back, disc1"), ("custom", "My own (set under Advanced)")), None),
        (H, "When a file already exists"),
        ("collision_policy", "Existing files", "choice", C(("if_better", "Replace only if the new image is larger"), ("overwrite", "Always replace"), ("skip", "Keep the existing file"), ("keep_both", "Keep both")), None),
        ("backups", "Keep a backup of replaced files so Undo can restore them", "bool", None, None),
    ],
    "Artists": [
        (H, "Artist images"),
        ("artist_art", "Look for artist images when I search for an album", "bool", None,
         "Photos come from Wikimedia Commons (through the artist's MusicBrainz links), Discogs (needs your token), Deezer, Fanart.tv and TheAudioDB. "
         "Logos, backgrounds and banners come from Fanart.tv (free key) and TheAudioDB. Tick or reorder sources under Sources. "
         "Compilations (Various Artists) never get artist images."),
        ("artist_types", "Pre-select", "multi", C(("thumb", "Photo"), ("logo", "Logo"), ("background", "Background"), ("banner", "Banner")),
         "Ticked kinds are pre-selected in the review window and used by Auto-apply when Artist images is ticked under General. "
         "The review window lists every kind that was found, so you can still pick the others by hand."),
        ("min_artist", "Smallest photo", "int", (0, 5000, " px"), "Smaller photos are hidden in the review window and never applied automatically."),
        (H, "Where it goes"),
        ("save_artist_art", "Save artist images in the artist folder (the folder above the album)", "bool", None,
         "For example Music/Artist/artist.jpg. Players and media servers read it from there. Several albums share it, so the larger image wins unless you set Existing files (General) otherwise."),
        (H, "File names (when File names under General is My own)"),
        ("name_artist_thumb", "Photo", "text", None, None),
        ("name_artist_logo", "Logo", "text", None, None),
        ("name_artist_background", "Background", "text", None, None),
        ("name_artist_banner", "Banner", "text", None, None),
    ],
    "Sources": [
        (H, "Where to look"),
        ("providers", "", "providers", None, "Tick the sources to search and drag to change the order. Cover Art Archive, TheAudioDB, Apple Music and Deezer need no key."),
        (H, "Keys"),
        ("discogs_token", "Discogs token", "password", None, "Discogs: Settings > Developers > Generate new token. Finds the exact pressing you tagged."),
        ("fanart_api_key", "Fanart.tv key", "password", None, "Free from fanart.tv/get-an-api-key. Adds disc art, artist photos, band logos, backgrounds and banners."),
        ("fanart_client_key", "Fanart.tv personal key", "password", None, "Optional. New uploads appear sooner."),
        ("audiodb_api_key", "TheAudioDB key", "text", None, "123 is the free public key. A personal key is faster."),
        ("lastfm_api_key", "Last.fm key", "password", None, "Optional. Last.fm images are usually small."),
        (H, "Web image search (optional, paid)"),
        ("websearch_engine", "Service", "radio", C(("brave", "Brave Search API"), ("google", "Google Programmable Search")), None),
        ("websearch_api_key", "API key", "password", None, "Brave charges per search (no free plan since May 2026); Google no longer takes new customers. Not needed: the review window's Search the web button opens Google Images in your browser for free."),
        ("websearch_google_cx", "Google engine ID", "text", None, None),
    ],
    "Image quality": [
        (H, "Which image to prefer"),
        ("prefer_largest", "Prefer", "radio", C((True, "The largest available"), (False, "The one closest to a preferred size")), None),
        ("target_size", "Preferred size", "int", (100, 10000, " px"), None),
        (H, "Smallest images to consider"),
        ("min_front", "Front", "int", (0, 5000, " px"), "Smaller images are hidden in the review dialog (you can still show them) and never applied automatically."),
        ("min_back", "Back", "int", (0, 5000, " px"), None),
        ("min_disc", "Disc", "int", (0, 5000, " px"), None),
        ("min_booklet", "Booklet", "int", (0, 5000, " px"), None),
        (H, "When applying"),
        ("apply_min_side", "Never apply below", "int", (0, 5000, " px"), "A low-resolution cover is not applied automatically; it can trigger Create instead."),
        ("embed_max_side", "Embedded images up to", "int", (0, 10000, " px"), "Larger images are scaled down for the tags only."),
        ("file_max_side", "Saved files up to", "int", (0, 30000, " px"), None),
        ("jpeg_quality", "JPEG quality", "int", (50, 100, ""), "Images are always saved as JPEG; this is the quality used when one is converted from PNG or TIFF, or resized."),
        ("upscale_to_minimum", "Enlarge images smaller than the minimum (they will look soft)", "bool", None, None),
    ],
    "Create": [
        (H, "When to create a cover"),
        ("creative_triggers", "Create when", "multi", C(("no_cover", "No cover is found"), ("below_min", "The best cover is below the apply minimum"), ("low_confidence", "Sources disagree about the cover")), "Off by default. Real covers always come first."),
        ("creative_always", "Always use a created front cover, even when a real one exists", "bool", None, None),
        ("creative_method_order", "Try", "order", C(("fanart,ai,template", "Fan art, then AI, then the built-in renderer"), ("ai,template", "AI, then the built-in renderer"), ("fanart,template", "Fan art, then the built-in renderer"), ("template", "Built-in renderer only"), ("ai", "AI only"), ("fanart", "Fan art only")), None),
        (H, "Look"),
        ("creative_template", "Style", "template", None, None),
        ("creative_custom_prompt", "Custom prompt", "text", None, "For the Custom style. {artist}, {album}, {year}, {genre} and {era} are filled in."),
        ("creative_match_era", "Match the era of the release year", "bool", None, None),
        ("creative_match_genre", "Match the genre", "bool", None, None),
        ("creative_overlay_logo", "Show the band logo (or the artist name)", "bool", None, None),
        ("creative_overlay_title", "Show the album title", "bool", None, None),
        ("creative_logo_position", "Logo position", "radio", C(("top", "Top"), ("center", "Centre"), ("bottom", "Bottom")), None),
        ("creative_variations", "Versions per click", "int", (1, 8, ""), None),
        ("creative_max_per_run", "Most covers per Auto-apply run", "int", (0, 1000, ""), None),
        (H, "AI image service"),
        ("ai_backend", "Service", "choice", C(("none", "None: use the built-in renderer"), ("automatic1111", "Stable Diffusion on this computer (AUTOMATIC1111)"), ("openai", "OpenAI-compatible images API"), ("custom", "Other (custom HTTP endpoint)"), ("cloudflare", "Cloudflare Workers AI (free daily allowance)"), ("aihorde", "AI Horde (free, run by volunteers)")), "Services outside this computer receive the artist, album, year and genre, and ask for your consent first."),
        ("ai_url", "Address", "text", None, None),
        ("ai_model", "Model", "text", None, "Optional."),
        ("ai_api_key", "API key", "password", None, None),
        ("ai_cf_account_id", "Account ID", "text", None, "Needs a free Cloudflare account. The dashboard's Workers AI page (Use REST API) shows your account ID."),
        ("ai_cf_api_token", "API token", "password", None, "Create it on the same page (Create a Workers AI API Token). It is stored like your other keys and never written to the log."),
        ("ai_cf_model", "Model", "suggest", CLOUDFLARE_MODELS,
         "Free allowance: 10,000 neurons a day. FLUX.1 schnell at 1024×1024 costs about 58 neurons, so about 170 covers a day are free; "
         "the Leonardo models cost far more. You can also type any other Workers AI text-to-image model ID."),
        ("ai_cf_steps", "Steps", "int", (1, 50, ""), "FLUX.1 schnell takes up to 8 (4 is its default), the SDXL models up to 20. Larger values are lowered to what the model allows."),
        ("ai_horde_api_key", "API key", "password", None, "0000000000 is the anonymous key and works without an account. A free registered key (aihorde.net/register) gets priority in the queue."),
        ("ai_horde_model", "Model", "text", None, "Any image model the Horde lists, for example AlbedoBase XL (SDXL). Covers are made on volunteers' computers, so expect a short queue."),
        ("ai_horde_max_wait", "Give up after", "int", (30, 3600, " s"), "The request is cancelled if no volunteer has finished it by then."),
        ("ai_size", "Image size", "int", (256, 2048, " px"), "AI Horde rounds it to a multiple of 64 (512 to 1024 px with the anonymous key). FLUX.1 schnell chooses its own size."),
        ("ai_steps", "Steps", "int", (1, 150, ""), "Stable Diffusion only."),
        ("ai_img2img", "Base new covers on the current low-resolution cover", "bool", None, None),
        ("ai_allow_remote_reference", "Allow sending that cover to services outside this computer", "bool", None, None),
    ],
    "Advanced": [
        (H, "Matching"),
        ("auto_apply_mode", "Auto-apply", "radio", C(("confident", "Only when the result is certain"), ("never", "Never: always review")), None),
        ("hamming_threshold", "Same-picture tolerance", "int", (1, 30, " of 64"), "How different two files may be and still count as the same artwork."),
        ("conflict_min_sources", "Flag a conflict at", "int", (2, 10, " sources"), "Sources agreeing on a different picture than the exact release."),
        ("front_aspect_tolerance", "Square tolerance", "float", (0.0, 0.5, ""), "Front and disc art: 0.05 accepts images up to 5% off square. Cassette, DVD and VHS covers are exempt."),
        ("max_side", "Ignore images larger than", "int", (0, 30000, " px"), None),
        ("max_file_mb", "Largest download", "int", (1, 200, " MB"), None),
        (H, "Files and tags"),
        ("multi_folder", "Albums split into CD1, CD2 folders", "radio", C(("every", "Album art in every folder"), ("first", "Album art in the first folder only")), None),
        ("replace_embedded", "Remove older embedded images of the same type", "bool", None, None),
        ("record_source_in_comment", "Note the source in the embedded image's comment", "bool", None, None),
        ("write_sidecar", "Write coverup.json describing where each file came from", "bool", None, None),
        (H, "My own file names"),
        ("name_front", "Front", "text", None, None),
        ("name_back", "Back", "text", None, None),
        ("name_disc", "Disc", "text", None, "{discnumber} becomes 1, 2, …"),
        ("name_booklet", "Booklet page", "text", None, "{n} becomes 01, 02, …"),
        (H, "Network"),
        ("http_cache_hours", "Remember search results for", "int", (0, 720, " hours"), None),
        ("max_candidates_per_provider", "Results per source", "int", (1, 50, ""), None),
        (H, "Log file"),
        ("log_mode", "Keep", "choice", C(("fixed", "Rotating files of a fixed size"), ("total", "Files up to a total size"), ("age", "Files for a number of days"), ("session", "One file per Picard session"), ("off", "No log file")), None),
        ("log_max_mb", "File size", "int", (1, 50, " MB"), None),
        ("log_backups", "Older files kept", "int", (0, 20, ""), None),
        ("log_total_cap_mb", "Total size", "int", (1, 1000, " MB"), None),
        ("log_retain_days", "Days kept", "int", (1, 365, " days"), None),
        ("log_sessions_keep", "Sessions kept", "int", (1, 50, ""), None),
        ("log_level", "Detail", "choice", C(("ERROR", "Errors only"), ("WARNING", "Warnings"), ("INFO", "Normal"), ("DEBUG", "Detailed"), ("TRACE", "Everything")), None),
        ("log_anonymise", "Hide folder paths and album names (for sharing logs)", "bool", None, None),
        ("log_folder", "Folder", "text", None, "Leave empty for the default."),
    ],
}

LOG_FIELDS = {
    "fixed": {"log_max_mb", "log_backups"},
    "total": {"log_max_mb", "log_total_cap_mb"},
    "age": {"log_max_mb", "log_retain_days"},
    "session": {"log_sessions_keep"},
    "off": set(),
}
NAME_KEYS = list(NAMING_PRESETS["default"])
ZERO_TEXT = {"embed_max_side": "Full size", "file_max_side": "Original size", "max_side": "No limit", "http_cache_hours": "Don't remember",
             "min_front": "Any size", "min_back": "Any size", "min_disc": "Any size", "min_booklet": "Any size", "min_artist": "Any size",
             "apply_min_side": "Any size", "creative_max_per_run": "None"}
# The AI fields each service uses. Fields of other services are hidden; with no service the shared ones show greyed out.
_AI_GENERIC = ("ai_url", "ai_model", "ai_api_key", "ai_size", "ai_steps", "ai_img2img", "ai_allow_remote_reference")
AI_FIELDS = {
    "automatic1111": _AI_GENERIC,
    "openai": _AI_GENERIC,
    "custom": _AI_GENERIC,
    "cloudflare": ("ai_cf_account_id", "ai_cf_api_token", "ai_cf_model", "ai_cf_steps", "ai_size"),
    "aihorde": ("ai_horde_api_key", "ai_horde_model", "ai_horde_max_wait", "ai_size"),
}
AI_KEYS = tuple(dict.fromkeys(k for keys in AI_FIELDS.values() for k in keys))


def _help(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("coverupHelp")
    lab.setWordWrap(True)
    lab.setForegroundRole(QPalette.ColorRole.PlaceholderText)
    lab.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return lab


def _heading(text: str, first: bool) -> QLabel:
    lab = QLabel(text)
    f = lab.font()
    f.setBold(True)
    f.setPointSizeF(f.pointSizeF() * 1.08)
    lab.setFont(f)
    lab.setContentsMargins(0, 0 if first else 16, 0, 2)
    return lab


class _Radio(QWidget):
    """Radio buttons with a value per button (KDE HIG: up to three short choices)."""

    def __init__(self, options, horizontal: bool):
        super().__init__()
        lay = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.group = QButtonGroup(self)
        self.buttons: list[tuple[object, QRadioButton]] = []
        for value, label in options:
            b = QRadioButton(label)
            self.group.addButton(b)
            lay.addWidget(b)
            self.buttons.append((value, b))
        if horizontal:
            lay.addStretch(1)

    def value(self):
        return next((v for v, b in self.buttons if b.isChecked()), self.buttons[0][0])

    def set_value(self, value) -> None:
        for v, b in self.buttons:
            b.setChecked(v == value)
        if not any(b.isChecked() for _v, b in self.buttons):
            self.buttons[0][1].setChecked(True)


def _make_options_page_class(base):
    class CoverUpOptionsPage(base):
        NAME = "coverup"
        TITLE = "CoverUp"
        PARENT = "plugins"
        # Picard's default page style makes every QLabel wrap, which clips form labels: opt out.
        STYLESHEET = ""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.widgets: dict[str, tuple[str, object]] = {}
            self.rows: dict[str, list[QWidget]] = {}
            self.cells: dict[str, tuple[QFormLayout, QWidget]] = {}
            self._custom_names = {k: str(DEFAULTS[k]) for k in NAME_KEYS}
            outer = QVBoxLayout(self)
            outer.setContentsMargins(0, 0, 0, 0)
            self.tabs = QTabWidget()
            self.tabs.setDocumentMode(True)
            outer.addWidget(self.tabs)
            for tab, entries in LAYOUT.items():
                page = QWidget()
                col = QVBoxLayout(page)
                col.setContentsMargins(12, 10, 12, 10)
                # one form per tab, so every label in the tab lines up on the same right edge
                form = QFormLayout()
                form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
                form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.DontWrapRows)
                form.setVerticalSpacing(8)
                col.addLayout(form)
                first = True
                for entry in entries:
                    if entry[0] == H:
                        form.addRow(_heading(entry[1], first))
                        first = False
                        continue
                    self._add_field(form, *entry)
                if tab == "Create":
                    col.addLayout(self._buttons((("Open my styles folder", self._open_templates), ("Ask again before using AI services", self._forget_ai))))
                if tab == "Advanced":
                    col.addLayout(self._buttons((("Open log folder", self._open_logs), ("Export diagnostics…", self._export), ("Clear search cache", self._clear_cache))))
                col.addStretch(1)
                scroll = QScrollArea()
                scroll.setWidgetResizable(True)
                scroll.setFrameShape(QFrame.Shape.NoFrame)
                scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                scroll.setWidget(page)
                self.tabs.addTab(scroll, tab)
            self.widgets["naming_preset"][1].currentIndexChanged.connect(self._preset_changed)
            self.widgets["log_mode"][1].currentIndexChanged.connect(self._update_enabled)
            self.widgets["ai_backend"][1].currentIndexChanged.connect(self._update_enabled)
            self.widgets["websearch_engine"][1].group.buttonToggled.connect(self._update_enabled)
            self.widgets["prefer_largest"][1].group.buttonToggled.connect(self._update_enabled)
            self.widgets["creative_template"][1].currentIndexChanged.connect(self._update_enabled)
            self.widgets["artist_art"][1].toggled.connect(self._update_enabled)

        # ---- building ----
        def _add_field(self, form: QFormLayout, key, label, kind, opt, help_text) -> None:
            w = self._widget(kind, opt, key)
            self.widgets[key] = (kind, w)
            row: list[QWidget] = [w]
            # the field and its explanation share one cell, so the help sits directly under its control
            cell = QWidget()
            cell_lay = QVBoxLayout(cell)
            cell_lay.setContentsMargins(0, 0, 0, 0)
            cell_lay.setSpacing(2)
            if kind == "providers" and help_text:
                h = _help(help_text)
                cell_lay.addWidget(h)
                row.append(h)
                help_text = None
            if kind in ("int", "float", "choice", "order", "template", "embed", "suggest"):
                line = QHBoxLayout()
                line.addWidget(w)
                line.addStretch(1)
                cell_lay.addLayout(line)
            else:
                cell_lay.addWidget(w)
            if help_text:
                h = _help(help_text)
                cell_lay.addWidget(h)
                row.append(h)
            if kind == "bool":
                w.setText(label)
                form.addRow("", cell)
            elif kind == "providers":
                form.addRow(cell)
            else:
                lab = QLabel(label)
                lab.setBuddy(w.buttons[0][1] if isinstance(w, _Radio) else w)
                lab.setContentsMargins(0, 4 if kind not in ("multi", "radio") else 1, 0, 0)
                form.addRow(lab, cell)
                row.append(lab)
            self.rows[key] = row
            self.cells[key] = (form, cell)

        def _buttons(self, buttons) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setContentsMargins(0, 14, 0, 0)
            for text, fn in buttons:
                b = QPushButton(text)
                b.clicked.connect(fn)
                row.addWidget(b)
            row.addStretch(1)
            return row

        def _widget(self, kind, opt, key):
            if kind == "bool":
                return QCheckBox()
            if kind in ("int", "float"):
                w = QSpinBox() if kind == "int" else QDoubleSpinBox()
                lo, hi, suffix = opt
                w.setRange(lo, hi)
                if suffix:
                    w.setSuffix(suffix)
                if kind == "float":
                    w.setSingleStep(0.01)
                    w.setDecimals(2)
                if key in ZERO_TEXT:
                    w.setSpecialValueText(ZERO_TEXT[key])
                w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                w.setMinimumWidth(130)
                return w
            if kind in ("text", "password"):
                w = QLineEdit()
                if kind == "password":
                    w.setEchoMode(QLineEdit.EchoMode.PasswordEchoOnEdit)
                return w
            if kind == "radio":
                horizontal = all(len(str(lbl)) <= 24 for _v, lbl in opt)
                return _Radio(opt, horizontal)
            if kind == "suggest":
                w = QComboBox()
                w.setEditable(True)
                w.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
                w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
                for value, tip in opt:
                    w.addItem(value, value)
                    w.setItemData(w.count() - 1, tip, Qt.ItemDataRole.ToolTipRole)
                return w
            if kind in ("choice", "order", "template", "embed"):
                w = QComboBox()
                w.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
                w.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
                if kind == "template":
                    from ..creative.template_engine import CUSTOM, load_templates
                    from ..glue import STATE

                    for name, t in sorted(load_templates(STATE.user_templates_dir()).items(), key=lambda kv: kv[1].title):
                        w.addItem(t.title, name)
                    w.addItem("Custom prompt", CUSTOM)
                elif kind == "embed":
                    for types, label in EMBED_CHOICES:
                        w.addItem(label, types)
                else:
                    for value, label in opt:
                        w.addItem(label, value)
                return w
            if kind == "folder":
                box = QWidget()
                lay = QHBoxLayout(box)
                lay.setContentsMargins(0, 0, 0, 0)
                box.combo = QComboBox()
                for name in FOLDER_PRESETS:
                    box.combo.addItem(f"{name}/ folder inside the album", name)
                box.combo.addItem("The album folder itself", ALBUM_FOLDER)
                box.combo.addItem("Another folder inside the album…", OTHER_FOLDER)
                box.combo.addItem("Don't save files", NO_FILES)
                box.edit = QLineEdit()
                box.edit.setPlaceholderText("folder name")
                box.edit.setMaximumWidth(180)
                box.combo.currentIndexChanged.connect(lambda _i: self._update_enabled())
                lay.addWidget(box.combo)
                lay.addWidget(box.edit)
                lay.addStretch(1)
                return box
            if kind == "multi":
                box = QWidget()
                lay = QVBoxLayout(box)
                lay.setContentsMargins(0, 0, 0, 0)
                lay.setSpacing(2)
                box.checks = []
                for value, label in opt:
                    cb = QCheckBox(label)
                    cb.setProperty("value", value)
                    lay.addWidget(cb)
                    box.checks.append(cb)
                return box
            if kind == "providers":
                self.provider_list = QListWidget()
                self.provider_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
                self.provider_list.setMinimumHeight(196)
                return self.provider_list
            raise ValueError(kind)

        def _show(self, key: str, enabled: bool) -> None:
            for w in self.rows.get(key, []):
                w.setEnabled(enabled)

        def _visible(self, key: str, visible: bool) -> None:
            form, cell = self.cells[key]
            if hasattr(form, "setRowVisible"):  # Qt 6.4+
                form.setRowVisible(cell, visible)
            else:
                cell.setVisible(visible)
                for w in self.rows.get(key, []):
                    if isinstance(w, QLabel) and w.parent() is not cell:
                        w.setVisible(visible)

        def _preset_changed(self, *_):
            preset = self.widgets["naming_preset"][1].currentData()
            if getattr(self, "_last_preset", None) == "custom":
                self._custom_names = {k: self.widgets[k][1].text() for k in NAME_KEYS}
            self._last_preset = preset
            names = NAMING_PRESETS.get(preset) or self._custom_names
            for k in NAME_KEYS:
                self.widgets[k][1].setText(names[k])
            self._update_enabled()

        def _update_enabled(self, *_):
            custom = self.widgets["naming_preset"][1].currentData() == "custom"
            for k in NAME_KEYS:
                self._show(k, custom)
            folder = self.widgets["folder"][1]
            choice = folder.combo.currentData()
            folder.edit.setVisible(choice == OTHER_FOLDER)
            self._show("front_in_album_folder", choice not in (ALBUM_FOLDER, NO_FILES))
            self._show("write_files_when", choice != NO_FILES)
            mode = self.widgets["log_mode"][1].currentData()
            for k in ("log_max_mb", "log_backups", "log_total_cap_mb", "log_retain_days", "log_sessions_keep"):
                self._show(k, k in LOG_FIELDS.get(mode, set()))
            self._show("websearch_google_cx", self.widgets["websearch_engine"][1].value() == "google")
            artist_on = self.widgets["artist_art"][1].isChecked()
            for k in ("artist_types", "min_artist", "save_artist_art"):
                self._show(k, artist_on)
            self._show("target_size", self.widgets["prefer_largest"][1].value() is False)
            self._show("creative_custom_prompt", self.widgets["creative_template"][1].currentData() == "custom")
            fields = AI_FIELDS.get(self.widgets["ai_backend"][1].currentData(), ())
            shown = fields or _AI_GENERIC
            for k in AI_KEYS:
                self._visible(k, k in shown)
                self._show(k, k in fields)

        # ---- config ----
        def _cfg(self):
            return self.api.plugin_config

        def _get(self, key):
            try:
                v = self._cfg()[key]
            except Exception:
                v = None
            return DEFAULTS[key] if v is None else v

        def _set(self, key, value):
            self._cfg()[key] = value

        def load(self, source=None):
            get = source or self._get
            enabled = set(get("providers_enabled") or [])
            order = [p for p in (get("provider_order") or []) if p in PROVIDERS]
            order += [p for p in PROVIDERS if p not in order]
            self.provider_list.clear()
            for pid in order:
                item = QListWidgetItem(PROVIDER_LABELS[pid])
                item.setData(Qt.ItemDataRole.UserRole, pid)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsDragEnabled)
                item.setCheckState(Qt.CheckState.Checked if pid in enabled else Qt.CheckState.Unchecked)
                self.provider_list.addItem(item)
            for key, (kind, w) in self.widgets.items():
                if kind == "providers":
                    continue
                if kind == "folder":
                    if not get("save_files"):
                        data = NO_FILES
                    elif get("folder_mode") == "same":
                        data = ALBUM_FOLDER
                    elif get("folder_name") in FOLDER_PRESETS:
                        data = get("folder_name")
                    else:
                        data = OTHER_FOLDER
                        w.edit.setText(str(get("folder_name")))
                    w.combo.setCurrentIndex(max(0, w.combo.findData(data)))
                    continue
                if kind == "embed":
                    current = list(get("embed_types") or []) if get("embed") else []
                    w.setCurrentIndex(next((i for i, (t, _l) in enumerate(EMBED_CHOICES) if t == current), 0))
                    continue
                v = get(key)
                if kind == "bool":
                    w.setChecked(bool(v))
                elif kind == "int":
                    w.setValue(int(v))
                elif kind == "float":
                    w.setValue(float(v))
                elif kind in ("text", "password"):
                    w.setText(str(v))
                elif kind == "radio":
                    w.set_value(v)
                elif kind in ("choice", "template"):
                    w.setCurrentIndex(max(0, w.findData(v)))
                elif kind == "suggest":
                    w.setEditText(str(v))
                elif kind == "order":
                    w.setCurrentIndex(max(0, w.findData(",".join(v) if isinstance(v, (list, tuple)) else str(v))))
                elif kind == "multi":
                    vals = set(v or [])
                    for cb in w.checks:
                        cb.setChecked(cb.property("value") in vals)
            self._custom_names = {k: str(get(k)) for k in NAME_KEYS}
            self._last_preset = None
            self._preset_changed()

        def restore_defaults(self):
            """Show the defaults; nothing is stored until the user confirms the Options dialog."""
            self.load(source=lambda key: DEFAULTS[key])

        def save(self):
            order, enabled = [], []
            for i in range(self.provider_list.count()):
                item = self.provider_list.item(i)
                pid = item.data(Qt.ItemDataRole.UserRole)
                order.append(pid)
                if item.checkState() == Qt.CheckState.Checked:
                    enabled.append(pid)
            self._set("provider_order", order)
            self._set("providers_enabled", enabled)
            custom = self.widgets["naming_preset"][1].currentData() == "custom"
            for key, (kind, w) in self.widgets.items():
                if key in NAME_KEYS and not custom:
                    continue  # the fields only show the preset; keep the user's own names
                if kind == "providers":
                    continue
                if kind == "folder":
                    data = w.combo.currentData()
                    self._set("save_files", data != NO_FILES)
                    if data == ALBUM_FOLDER:
                        self._set("folder_mode", "same")
                    elif data in FOLDER_PRESETS:
                        self._set("folder_mode", "subfolder")
                        self._set("folder_name", data)
                    elif data == OTHER_FOLDER:
                        self._set("folder_mode", "subfolder")
                        try:
                            self._set("folder_name", validate_folder_name(w.edit.text().strip()))
                        except ValueError:
                            self._set("folder_name", "covers")
                    continue
                if kind == "embed":
                    types = list(w.currentData() or [])
                    self._set("embed", bool(types))
                    if types:
                        self._set("embed_types", types)
                    continue
                if kind == "bool":
                    v = w.isChecked()
                elif kind == "int":
                    v = int(w.value())
                elif kind == "float":
                    v = float(w.value())
                elif kind in ("text", "password"):
                    v = w.text().strip()
                elif kind == "radio":
                    v = w.value()
                elif kind in ("choice", "template"):
                    v = w.currentData()
                elif kind == "suggest":
                    v = w.currentText().strip() or DEFAULTS[key]
                elif kind == "order":
                    v = [x for x in str(w.currentData()).split(",") if x]
                elif kind == "multi":
                    v = [cb.property("value") for cb in w.checks if cb.isChecked()]
                else:
                    continue
                self._set(key, v)
            from .. import reconfigure_logging

            reconfigure_logging()

        # ---- buttons ----
        def _forget_ai(self):
            self._set("ai_consented_hosts", [])
            QMessageBox.information(self, "CoverUp", "CoverUp will ask again before sending album details to an AI service.")

        def _open_logs(self):
            from .. import current_log_folder

            folder = current_log_folder()
            folder.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

        def _open_templates(self):
            from ..glue import STATE

            folder = STATE.user_templates_dir()
            folder.mkdir(parents=True, exist_ok=True)
            readme = folder / "README.txt"
            if not readme.exists():
                readme.write_text(
                    "Put your own CoverUp styles here (*.toml). Copy one of the built-in styles from the plugin's\n"
                    "creative/templates folder as a starting point. A style here with the same name as a built-in\n"
                    "one replaces it.\n",
                    encoding="utf-8",
                )
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

        def _export(self):
            from .. import __version__, current_log_folder
            from ..diagnostics.bundle import create
            from ..glue import STATE

            path, _ = QFileDialog.getSaveFileName(self, "Export diagnostics", str(Path.home() / "coverup-diagnostics.zip"), "Zip (*.zip)")
            if not path:
                return
            s = STATE.settings()
            try:
                import picard

                pv = getattr(picard, "PICARD_FANCY_VERSION_STR", "?")
            except Exception:
                pv = "?"
            create(path, current_log_folder(), s.redacted(), {"coverup": __version__, "picard": pv}, s.secrets())
            QMessageBox.information(self, "CoverUp", f"Saved {path}. API keys are not included.")

        def _clear_cache(self):
            import shutil

            from ..glue import STATE

            shutil.rmtree(STATE.cache_root() / "http", ignore_errors=True)
            QMessageBox.information(self, "CoverUp", "Search cache cleared.")

    return CoverUpOptionsPage
