import logging
import tomllib
import uuid
from pathlib import Path

import pytest

import coverup
from conftest import have_picard

ROOT = Path(__file__).resolve().parent.parent


def test_manifest_meets_picard_v3_spec():
    data = tomllib.loads((ROOT / "MANIFEST.toml").read_text(encoding="utf-8"))
    assert str(uuid.UUID(data["uuid"], version=4)) == data["uuid"]
    assert 1 <= len(data["name"]) <= 100
    assert 1 <= len(data["description"]) <= 200 and "\n" not in data["description"]
    assert data["api"] == ["3.0"]
    assert 1 <= len(data["long_description"]) <= 2000
    assert set(data["categories"]) <= {"metadata", "coverart", "ui", "scripting", "formats", "other"}
    assert data["license"] == "GPL-2.0-or-later"


class FakeConfig(dict):
    def register_option(self, key, default, **kw):
        self.setdefault(key, default)


class FakeApi:
    """Records what the plugin registers, with the same method names as Picard's PluginApi."""

    def __init__(self):
        self.plugin_config = FakeConfig()
        self.records = []
        self.registered = {}
        outer = self

        class L:
            def warning(self, m):
                outer.records.append(("warning", m))

            def error(self, m):
                outer.records.append(("error", m))

        self.logger = L()

    def __getattr__(self, name):
        if name.startswith("register_"):
            return lambda obj, **kw: self.registered.setdefault(name, []).append(obj)
        raise AttributeError(name)


@pytest.mark.skipif(not have_picard(), reason="set PICARD_SRC to a Picard 3 source tree to run")
def test_enable_registers_everything_and_logs(tmp_path, monkeypatch, qapp):
    monkeypatch.setenv("PICARD_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("PICARD_CONFIG_DIR", str(tmp_path / "config"))
    from coverup import glue

    api = FakeApi()
    coverup.enable(api)
    try:
        reg = api.registered
        assert {a.TITLE for a in reg["register_album_action"]} == {"CoverUp: Find artwork…", "CoverUp: Auto-apply", "CoverUp: Undo last apply"}
        assert len(reg["register_cluster_action"]) == 3
        assert reg["register_file_post_save_processor"] == [glue.on_file_saved]
        assert reg["register_options_page"][0].NAME == "coverup"
        assert {"_coverup_status", "_coverup_generated"} <= set(reg["register_script_variable"])
        assert api.plugin_config["log_mode"] == "fixed" and api.plugin_config["log_max_mb"] == 2
        assert api.plugin_config["folder_name"] == "covers"
        logging.getLogger("coverup").warning("forward me")
    finally:
        coverup.disable()
    log_file = tmp_path / "cache" / "coverup" / "logs" / "coverup.log"
    assert "CoverUp 0.6.0 starting" in log_file.read_text(encoding="utf-8")
    assert ("warning", "CoverUp: forward me") in api.records
