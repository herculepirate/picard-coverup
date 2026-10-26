# -*- coding: utf-8 -*-
# CoverUp: MusicBrainz Picard plugin. GPL-2.0-or-later.
"""CoverUp: find, compare and apply album artwork (Picard 3 plugin).

Entry points (right-click an album, cluster, track or file):
  * CoverUp: Find artwork…      opens the review dialog
  * CoverUp: Auto-apply         applies confident results for every selected album, lists the rest
  * CoverUp: Undo last apply    restores/removes the files written by the last apply
  * a "CoverUp" entry in Options > Cover Art, so Picard's own album loading can use CoverUp too

Picard-facing modules are imported inside ``enable`` so the rest of the package can be unit tested
without Picard installed.
"""

from __future__ import annotations

import logging
from pathlib import Path

__version__ = "0.6.1"

_log = logging.getLogger("coverup")


def current_log_folder() -> Path:
    from .glue import STATE

    s = STATE.settings()
    if s["log_folder"]:
        return Path(s["log_folder"]).expanduser()
    return STATE.cache_root() / "logs"


def reconfigure_logging() -> None:
    """(Re)build the log file handler from the current settings. Safe to call at any time."""
    from .diagnostics.logging_setup import MB, LogSettings, setup_logging
    from .glue import STATE

    api = STATE.api
    s = STATE.settings()
    if STATE.log_handle is not None:
        STATE.log_handle.close()
    settings = LogSettings(
        folder=current_log_folder(),
        mode=str(s["log_mode"]),
        max_bytes=int(s["log_max_mb"]) * MB,
        backups=int(s["log_backups"]),
        total_cap_bytes=int(s["log_total_cap_mb"]) * MB,
        retain_days=int(s["log_retain_days"]),
        sessions_keep=int(s["log_sessions_keep"]),
        level=str(s["log_level"]),
        anonymise=bool(s["log_anonymise"]),
    )

    def to_picard(level: int, message: str) -> None:
        if api is None:
            return
        (api.logger.error if level >= logging.ERROR else api.logger.warning)(message)

    STATE.log_handle = setup_logging(settings, secrets=s.secrets(), picard_sink=to_picard)


def enable(api) -> None:
    """Plugin entry point (Plugin V3 API)."""
    from PyQt6.QtWidgets import QMessageBox

    from picard.plugin3.api import BaseAction, OptionsPage

    from . import glue
    from .ui.options_page import _make_options_page_class

    glue.STATE.api = api
    glue.STATE.version = __version__
    glue.register_options(api)
    reconfigure_logging()
    _log.info("CoverUp %s starting (Picard plugin API 3.0)", __version__)
    for w in getattr(glue.STATE.log_handle, "warnings", []):
        api.logger.warning(w)

    def window():
        try:
            return api.tagger.window
        except Exception:
            return None

    class FindArtwork(BaseAction):
        TITLE = "CoverUp: Find artwork…"

        def callback(self, objs):
            from .ui.review_dialog import ReviewDialog

            targets = glue.unique_targets(objs)
            if not targets:
                QMessageBox.information(window(), "CoverUp", "Select an album (or a cluster of files) first.")
                return
            if len(targets) > 1:
                ans = QMessageBox.question(
                    window(), "CoverUp",
                    f"{len(targets)} albums are selected. Review them one after another?\n"
                    "(Use “CoverUp: Auto-apply” to process many albums at once.)",
                )
                if ans != QMessageBox.StandardButton.Yes:
                    return
            for t in targets:
                if ReviewDialog(t, window()).exec() == 0 and len(targets) > 1:
                    more = QMessageBox.question(window(), "CoverUp", "Continue with the next album?")
                    if more != QMessageBox.StandardButton.Yes:
                        break

    class AutoApply(BaseAction):
        TITLE = "CoverUp: Auto-apply"

        def callback(self, objs):
            from .ui.batch_dialog import BatchDialog

            targets = glue.unique_targets(objs)
            if not targets:
                QMessageBox.information(window(), "CoverUp", "Select one or more albums first.")
                return
            dlg = BatchDialog(targets, window())
            dlg.setModal(False)
            dlg.show()
            glue.STATE.batch_dialog = dlg  # keep a reference while it runs

    class UndoApply(BaseAction):
        TITLE = "CoverUp: Undo last apply"

        def callback(self, objs):
            targets = glue.unique_targets(objs)
            lines = []
            for t in targets:
                lines += glue.undo_last(t)
            if lines:
                QMessageBox.information(window(), "CoverUp", "Undone:\n" + "\n".join(lines[:40]) + ("\n…" if len(lines) > 40 else ""))
            else:
                QMessageBox.information(
                    window(), "CoverUp",
                    "No CoverUp file changes to undo for the selection.\n"
                    "Embedded images are only written when you save; to drop unsaved changes, remove and reload the album.",
                )

    for action in (FindArtwork, AutoApply, UndoApply):
        api.register_album_action(action)
        api.register_cluster_action(action)
    api.register_track_action(FindArtwork)
    api.register_file_action(FindArtwork)
    api.register_file_post_save_processor(glue.on_file_saved)
    api.register_file_post_addition_to_track_processor(glue.on_file_attached)
    _register_cover_art_provider(api)
    api.register_options_page(_make_options_page_class(OptionsPage))
    for name, doc in glue.SCRIPT_VARIABLES.items():
        try:
            api.register_script_variable(name, documentation=doc)
        except Exception as exc:  # older 3.x without this API, or a name clash
            _log.debug("Script variable %s not registered: %s", name, exc)


def _register_cover_art_provider(api) -> None:
    """List CoverUp among Picard's cover art providers (Options > Cover Art). Never stops the plugin loading."""
    try:
        from picard.plugin3.api import CoverArtProvider

        from .picard_provider import make_provider_class

        api.register_cover_art_provider(make_provider_class(CoverArtProvider))
        _log.info("Registered as a Picard cover art provider")
    except Exception:
        _log.warning("Could not register as a Picard cover art provider", exc_info=True)


def disable() -> None:
    """Stop running work and close the log file when the plugin is disabled."""
    try:
        from .glue import STATE

        STATE.cancel.set()
        if STATE.log_handle is not None:
            STATE.log_handle.close()
            STATE.log_handle = None
    except Exception:
        pass
