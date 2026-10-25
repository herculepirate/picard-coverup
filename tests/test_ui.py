"""Qt UI tests (off-screen): review dialog, batch auto-apply, options page."""

import pytest

from conftest import have_picard, wait_until
from helpers import FakeHttp, make_image

pytestmark = [pytest.mark.skipif(not have_picard(), reason="set PICARD_SRC to a Picard 3 source tree"), pytest.mark.usefixtures("qapp")]

from test_glue_picard import REL, build_album, picard_env  # noqa: E402,F401  (fixture reuse)

RG = "22222222-2222-4222-8222-222222222222"


class FakeConfig(dict):
    def register_option(self, key, default, **kw):
        self.setdefault(key, default)


class FakeApi:
    def __init__(self, **cfg):
        from coverup.settings import DEFAULTS

        self.plugin_config = FakeConfig(DEFAULTS)
        self.plugin_config.update({"providers_enabled": ["caa", "deezer"], "http_cache_hours": 0, **cfg})


def routes():
    A = make_image("a", 1200)
    img = lambda i, t, u, **k: {"id": i, "types": [t], "image": u, "thumbnails": {"250": u}, **k}  # noqa: E731
    return {
        f"https://musicbrainz.org/ws/2/release/{REL}": {"title": "Album", "release-group": {"id": RG}, "media": [{"track-count": 1}] * 2},
        f"https://coverartarchive.org/release/{REL}": {"images": [
            img(1, "Front", "https://caa/f.jpg", front=True), img(2, "Back", "https://caa/b.jpg", back=True),
            img(3, "Medium", "https://caa/d2.jpg", comment="Disc 2"), img(4, "Booklet", "https://caa/p1.jpg"), img(5, "Booklet", "https://caa/p2.jpg"),
        ]},
        f"https://coverartarchive.org/release-group/{RG}": 404,
        "https://caa/f.jpg": A, "https://caa/b.jpg": make_image("c", 1000, w=1000, h=900), "https://caa/d2.jpg": make_image("b", 700),
        "https://caa/p1.jpg": make_image("b", 800, w=1200, h=600), "https://caa/p2.jpg": make_image("c", 800, w=1200, h=600),
        "https://api.deezer.com/": {"data": [{"id": 9, "title": "Album", "artist": {"name": "Artist"}, "cover_xl": "https://dz/x.jpg", "cover_medium": "https://dz/x.jpg"}]},
        "https://dz/x.jpg": A,
    }


@pytest.fixture
def state(picard_env, monkeypatch):
    from coverup import glue, imaging
    from coverup.pipeline import Pipeline

    http = FakeHttp(routes())
    api = FakeApi()
    monkeypatch.setattr(glue.STATE, "api", api)
    monkeypatch.setattr(glue.STATE, "pipeline", lambda cancel=None: Pipeline(glue.STATE.settings(), http, imaging.fingerprint))
    return glue.STATE


def open_dialog(picard_env, state):
    from coverup.ui.review_dialog import ReviewDialog

    album, files = build_album(picard_env)
    dlg = ReviewDialog(album, None, state)
    assert wait_until(lambda: dlg.result is not None), "search did not finish"
    return dlg, album, files


def slot(dlg, key):
    return next(s for s in dlg.slots if s.key == key)


def test_dialog_builds_one_tab_per_slot_and_preselects_the_set(picard_env, state):
    from coverup.model import ArtType

    dlg, _album, _ = open_dialog(picard_env, state)
    tabs = [dlg.tabs.tabText(i) for i in range(dlg.tabs.count())]
    assert tabs == ["Front (2)", "Back (1)", "Disc 1", "Disc 2 (1)", "Booklet (2)", "Artist", "Create"]
    assert slot(dlg, "front").chosen[0].provider == "caa"
    assert slot(dlg, "disc1").chosen == [] and not slot(dlg, "disc1").include.isEnabled()
    assert slot(dlg, "disc1").stack.currentIndex() == 1  # empty state with directions
    items = dlg.chosen_items()
    kinds = sorted((i.art_type.value, i.disc_number or 0, i.page or 0) for i in items)
    assert kinds == [("back", 0, 0), ("booklet", 0, 1), ("booklet", 0, 2), ("disc", 2, 0), ("front", 0, 0)]
    assert dlg.apply_btn.text() == "Apply 5 images" and dlg.apply_btn.isEnabled()
    assert "Embeds the front image in the tags" in dlg.summary.text() and "covers/" in dlg.summary.text()
    assert dlg.preview.title.text() == "Cover Art Archive"
    assert "exact release" in dlg.status.text()
    # untick the booklet: two fewer images
    slot(dlg, "booklet").include.setChecked(False)
    assert dlg.apply_btn.text() == "Apply 3 images"
    assert all(i.art_type != ArtType.BOOKLET for i in dlg.chosen_items())
    dlg.reject()


def test_dialog_destination_controls(picard_env, state):
    from coverup.ui.review_dialog import NO_FILES, OTHER_FOLDER

    dlg, _a, _ = open_dialog(picard_env, state)
    dlg.folder_combo.setCurrentIndex(dlg.folder_combo.findData("artwork"))
    assert dlg._destination()["folder_name"] == "artwork"
    dlg.folder_combo.setCurrentIndex(dlg.folder_combo.findData(OTHER_FOLDER))
    dlg.custom_folder.setText("bad/name")
    assert not dlg.apply_btn.isEnabled() and "valid folder name" in dlg.summary.text()
    dlg.custom_folder.setText("My Scans")
    assert dlg._destination()["folder_name"] == "My Scans" and dlg.apply_btn.isEnabled()
    dlg.folder_combo.setCurrentIndex(dlg.folder_combo.findData(NO_FILES))
    dlg.embed_combo.setCurrentIndex(dlg.embed_combo.findData([]))
    assert not dlg.apply_btn.isEnabled() and "choose where" in dlg.summary.text()
    dlg.reject()


def test_dialog_apply_embeds_front_only_and_saves_the_rest(picard_env, state):
    import os

    from coverup import glue

    dlg, album, files = open_dialog(picard_env, state)
    glue.STATE.pending.clear()
    dlg._apply()
    assert wait_until(lambda: bool(glue.STATE.pending), 20), "apply did not finish"
    embedded = {tuple(i.types) for i in album.metadata.images}
    assert embedded == {("front",)}  # collector default: only the front goes into the tags
    glue.on_file_saved(None, files[1])
    cd2 = os.path.dirname(files[1].filename)
    names = sorted(os.listdir(os.path.join(cd2, "covers")))
    assert {"cover.jpg", "back.jpg", "disc2.jpg", "booklet-01.jpg", "booklet-02.jpg"} <= set(names)
    assert os.path.exists(os.path.join(cd2, "cover.jpg"))


def test_dialog_create_and_use_as_front(picard_env, state):
    dlg, _a, _ = open_dialog(picard_env, state)
    state.api.plugin_config["ai_size"] = 256
    dlg.s = state.settings()
    dlg.var_spin.setValue(2)
    dlg._generate()
    assert wait_until(lambda: dlg.creative_grid.count() == 2), "creating did not finish"
    assert dlg.use_btn.isEnabled()
    dlg._use_generated()
    front = slot(dlg, "front")
    assert front.chosen[0].generated and dlg.tabs.currentIndex() == 0
    item = [i for i in dlg.chosen_items() if i.art_type.value == "front"][0]
    assert item.candidate.comment.startswith("Generated by CoverUp")
    dlg.reject()


def test_batch_dialog_auto_applies(picard_env, state):
    from coverup.ui.batch_dialog import BatchDialog

    album, files = build_album(picard_env)
    dlg = BatchDialog([album], None, state)
    assert wait_until(lambda: not dlg.stop.isEnabled(), 30)
    assert dlg.table.item(0, 1).text().startswith("✔"), dlg.table.item(0, 2).text()
    assert {tuple(i.types) for i in album.metadata.images} == {("front",)}
    dlg.close()


def test_options_page_round_trip_and_restore_defaults(picard_env, monkeypatch):
    from unittest.mock import MagicMock, patch

    import coverup
    from coverup.ui.options_page import NO_FILES, OTHER_FOLDER, _make_options_page_class
    from picard.plugin3.api import OptionsPage

    monkeypatch.setattr(coverup, "reconfigure_logging", lambda: None)
    with patch("picard.ui.options.tagger_instance", return_value=MagicMock()):
        cls = _make_options_page_class(OptionsPage)
        cls.api = FakeApi(folder_name="artwork", log_max_mb=5, creative_triggers=["no_cover"], creative_method_order=["ai", "template"],
                          prefer_largest=False, embed_types=["front", "back"])
        page = cls()
    page.load()
    w = page.widgets
    assert w["folder"][1].combo.currentData() == "artwork"
    assert w["log_max_mb"][1].value() == 5
    assert w["creative_method_order"][1].currentData() == "ai,template"
    assert w["prefer_largest"][1].value() is False and w["target_size"][1].isEnabled()
    assert w["embed_types"][1].currentData() == ["front", "back"]
    assert w["embed_max_side"][1].specialValueText() == "Full size"
    # custom names are read-only unless the Custom preset is chosen
    assert not w["name_front"][1].isEnabled()
    w["folder"][1].combo.setCurrentIndex(w["folder"][1].combo.findData(OTHER_FOLDER))
    w["folder"][1].edit.setText("../bad")
    w["log_mode"][1].setCurrentIndex(w["log_mode"][1].findData("age"))
    w["embed_types"][1].setCurrentIndex(w["embed_types"][1].findData([]))
    page.provider_list.item(0).setCheckState(page.provider_list.item(0).checkState().__class__.Unchecked)
    page.save()
    cfg = cls.api.plugin_config
    assert cfg["folder_name"] == "covers"  # an invalid name falls back to the default
    assert cfg["log_mode"] == "age" and cfg["log_max_mb"] == 5 and cfg["prefer_largest"] is False
    assert cfg["embed"] is False
    assert cfg["creative_triggers"] == ["no_cover"] and cfg["creative_method_order"] == ["ai", "template"]
    assert "caa" not in cfg["providers_enabled"] and cfg["provider_order"][0] == "caa"
    # Restore defaults shows the collector defaults without storing them
    page.restore_defaults()
    assert w["prefer_largest"][1].value() is True and w["embed_types"][1].currentData() == ["front"]
    assert w["folder"][1].combo.currentData() == "covers" and cfg["log_mode"] == "age"
    w["folder"][1].combo.setCurrentIndex(w["folder"][1].combo.findData(NO_FILES))
    page.save()
    assert cfg["save_files"] is False


def test_search_menu_paste_and_drop(picard_env, state, monkeypatch):
    from PyQt6.QtCore import QMimeData, QUrl
    from PyQt6.QtGui import QDesktopServices, QImage
    from PyQt6.QtWidgets import QApplication

    dlg, _album, _ = open_dialog(picard_env, state)
    menu = dlg.search_btn.menu()
    menu.aboutToShow.emit()
    labels = [a.text() for a in menu.actions() if a.text()]
    assert labels[0] == "Google Images: large" and "Edit the search words…" in labels
    shops = [a for a in menu.actions() if a.text() == "Shops and streaming"][0].menu()
    assert [a.text() for a in shops.actions()][:3] == ["Amazon", "Spotify", "Tidal"]
    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    shops.actions()[1].trigger()
    assert opened[-1].startswith("https://open.spotify.com/search/") and "Album" in opened[-1]
    opened.clear()
    menu.actions()[0].trigger()
    assert opened and "tbm=isch" in opened[0] and "Album" in opened[0]
    assert "Ctrl+V" in dlg.status.text()

    front = slot(dlg, "front")
    before = front.grid.count()
    img = QImage.fromData(make_image("c", 900))
    QApplication.clipboard().setImage(img)
    dlg._paste()
    assert front.grid.count() == before + 1
    added = [c for c in front.grid.all() if c.provider == "manual"][0]
    assert (added.width, added.height) == (900, 900)

    # a Google result link dropped on the window downloads the real image
    state.pipeline_http = None
    http = dlg.pipeline.http
    http.routes["https://example.com/big.jpg"] = make_image("b", 1000)
    mime = QMimeData()
    mime.setUrls([QUrl("https://www.google.com/imgres?imgurl=https%3A%2F%2Fexample.com%2Fbig.jpg")])
    assert dlg._import_mime(mime)
    assert wait_until(lambda: front.grid.count() == before + 2)
    # a web page instead of an image is refused with a hint, not added
    http.routes["https://example.com/page"] = b"<html>not an image</html>"
    shown = []
    from PyQt6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    dlg._download("https://example.com/page")
    assert wait_until(lambda: shown)
    assert "web page, not an image" in shown[0] and front.grid.count() == before + 2
    dlg.reject()


def test_double_click_applies_that_picture_at_once_and_keeps_the_window_open(picard_env, state):
    from coverup import glue

    dlg, album, files = open_dialog(picard_env, state)
    glue.STATE.pending.clear()
    back = slot(dlg, "back")
    # nothing is applied by merely looking; double-clicking the back cover applies just that image
    assert not glue.STATE.pending
    dlg.accepted.connect(lambda: accepted.append(True))
    dlg._apply_now(back, back.grid.all()[0])
    assert wait_until(lambda: bool(glue.STATE.pending), 20), "double-click apply did not finish"
    accepted = []
    assert not accepted  # the window stays open
    assert dlg.status.text().startswith("CoverUp applied back")
    plan = next(iter(glue.STATE.pending.values()))
    assert [it.art_type.value for it in plan.items] == ["back"]  # only the picture that was double-clicked
    assert back.include.isChecked()
    assert dlg.apply_btn.isEnabled()  # the rest of the set can still be applied
    dlg.reject()


def test_options_page_has_an_artists_tab_with_its_own_switches(picard_env, monkeypatch):
    from unittest.mock import MagicMock, patch

    import coverup
    from coverup.ui.options_page import _make_options_page_class
    from picard.plugin3.api import OptionsPage

    monkeypatch.setattr(coverup, "reconfigure_logging", lambda: None)
    with patch("picard.ui.options.tagger_instance", return_value=MagicMock()):
        cls = _make_options_page_class(OptionsPage)
        cls.api = FakeApi(artist_types=["thumb", "logo"], min_artist=800)
        page = cls()
    page.load()
    tabs = [page.tabs.tabText(i) for i in range(page.tabs.count())]
    assert tabs[:3] == ["General", "Artists", "Sources"]
    w = page.widgets
    assert w["artist_art"][1].isChecked() and w["min_artist"][1].value() == 800
    assert {cb.property("value") for cb in w["artist_types"][1].checks if cb.isChecked()} == {"thumb", "logo"}
    assert any(PROVIDER for PROVIDER in [page.provider_list.item(i).text() for i in range(page.provider_list.count())] if "Wikimedia" in PROVIDER)
    # turning artist images off greys out what only matters when they are on
    w["artist_art"][1].setChecked(False)
    assert not w["artist_types"][1].isEnabled() and not w["min_artist"][1].isEnabled() and not w["save_artist_art"][1].isEnabled()
    next(cb for cb in w["artist_types"][1].checks if cb.property("value") == "banner").setChecked(True)
    page.save()
    cfg = cls.api.plugin_config
    assert cfg["artist_art"] is False and set(cfg["artist_types"]) == {"thumb", "logo", "banner"} and cfg["min_artist"] == 800


def test_options_page_shows_only_the_chosen_ai_services_fields(picard_env, monkeypatch):
    from unittest.mock import MagicMock, patch

    import coverup
    from coverup.ui.options_page import _make_options_page_class
    from picard.plugin3.api import OptionsPage

    monkeypatch.setattr(coverup, "reconfigure_logging", lambda: None)
    with patch("picard.ui.options.tagger_instance", return_value=MagicMock()):
        cls = _make_options_page_class(OptionsPage)
        cls.api = FakeApi(ai_backend="cloudflare", ai_cf_model="@cf/someone/new-model", ai_cf_api_token="tok")
        page = cls()
    page.load()
    w = page.widgets

    def visible(key):
        form, cell = page.cells[key]
        return form.isRowVisible(cell) if hasattr(form, "isRowVisible") else not cell.isHidden()

    def on(key):
        return visible(key) and w[key][1].isEnabled()

    backend = w["ai_backend"][1]
    assert {backend.itemData(i) for i in range(backend.count())} >= {"none", "automatic1111", "openai", "custom", "cloudflare", "aihorde"}
    assert all(on(k) for k in ("ai_cf_account_id", "ai_cf_api_token", "ai_cf_model", "ai_cf_steps", "ai_size"))
    assert not any(visible(k) for k in ("ai_url", "ai_model", "ai_api_key", "ai_steps", "ai_img2img", "ai_horde_api_key", "ai_horde_model"))
    model = w["ai_cf_model"][1]
    assert model.currentText() == "@cf/someone/new-model"  # free text survives loading
    assert model.findText("@cf/stabilityai/stable-diffusion-xl-base-1.0") >= 0 and model.findText("@cf/leonardo/phoenix-1.0") >= 0
    backend.setCurrentIndex(backend.findData("aihorde"))
    assert all(on(k) for k in ("ai_horde_api_key", "ai_horde_model", "ai_horde_max_wait", "ai_size"))
    assert not any(visible(k) for k in ("ai_cf_account_id", "ai_cf_model", "ai_url"))
    assert w["ai_horde_api_key"][1].text() == "0000000000" and w["ai_horde_max_wait"][1].value() == 300
    backend.setCurrentIndex(backend.findData("none"))
    assert visible("ai_url") and not w["ai_url"][1].isEnabled() and not visible("ai_cf_model") and not visible("ai_horde_model")
    backend.setCurrentIndex(backend.findData("automatic1111"))
    assert on("ai_url") and on("ai_steps") and not visible("ai_cf_steps")
    backend.setCurrentIndex(backend.findData("cloudflare"))
    model.setCurrentIndex(model.findText("@cf/bytedance/stable-diffusion-xl-lightning"))
    w["ai_cf_account_id"][1].setText("  acct-1 ")
    w["ai_horde_model"][1].setText("Juggernaut XL")
    page.save()
    cfg = cls.api.plugin_config
    assert cfg["ai_backend"] == "cloudflare" and cfg["ai_cf_model"] == "@cf/bytedance/stable-diffusion-xl-lightning"
    assert cfg["ai_cf_account_id"] == "acct-1" and cfg["ai_cf_api_token"] == "tok" and cfg["ai_horde_model"] == "Juggernaut XL"
    model.setEditText("")
    page.save()
    assert cfg["ai_cf_model"] == "@cf/black-forest-labs/flux-1-schnell"  # empty falls back to the default


def test_local_images_are_offered_everywhere_and_can_be_rotated_and_cropped(picard_env, state, monkeypatch):
    from PyQt6.QtWidgets import QDialog

    from coverup import imaging
    from coverup.model import ArtType, Candidate, Tier
    from coverup.ui import review_dialog

    dlg, _album, _ = open_dialog(picard_env, state)
    data = make_image("a", w=800, h=400)
    local = Candidate("local", "/x/odd name.png", "file:///x/odd name.png", ArtType.OTHER, Tier.B, width=800, height=400, dims_known=True,
                      data=data, thumb_data=data, comment="odd name.png")
    dlg.result.candidates.append(local)
    dlg._refresh_all()
    for key in ("front", "back", "disc1", "disc2"):
        assert local in slot(dlg, key).grid.all(), key

    dlg.tabs.setCurrentIndex(dlg.slots.index(slot(dlg, "back")))
    grid = slot(dlg, "back").grid
    grid.setCurrentRow([c for c in grid.all()].index(local))
    grid.item([c for c in grid.all()].index(local)).setSelected(True)
    dlg._rotate(90)
    edited = [c for c in grid.all() if c.provider == "manual" and "rotated right" in c.comment]
    assert len(edited) == 1 and (edited[0].width, edited[0].height) == (400, 800)
    assert imaging._format_of(edited[0].data) == "jpeg" and local in grid.all()  # the original stays

    grid.clearSelection()
    grid.item([c for c in grid.all()].index(local)).setSelected(True)
    monkeypatch.setattr(review_dialog.CropDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    monkeypatch.setattr(review_dialog.CropDialog, "rect", lambda self: type("R", (), {"x": lambda s: 100, "y": lambda s: 0, "width": lambda s: 400, "height": lambda s: 400})())
    dlg._crop()
    cropped = [c for c in grid.all() if "cropped" in c.comment]
    assert len(cropped) == 1 and (cropped[0].width, cropped[0].height) == (400, 400)
