"""Artist image sources: Wikimedia Commons via MusicBrainz links, Deezer artist photos, Discogs artist pages,
and the switch that turns them off. Fixtures follow each API's documented response format."""

import pytest

from coverup.model import ArtType, Query, Tier
from coverup.net import HttpError
from coverup.providers.base import is_various
from coverup.providers.discogs import parse_artist_images
from coverup.providers.stores import Deezer, parse_deezer_artist
from coverup.providers.wikimedia import Wikimedia, claim_files, parse_imageinfo, relations
from coverup.settings import Settings
from helpers import FakeHttp

ART = "33333333-3333-4333-8333-333333333333"
Q = Query(artist="Pink Floyd", album="Animals", artist_mbid=ART)

MB_ARTIST = {
    "relations": [
        {"type": "wikidata", "url": {"resource": "https://www.wikidata.org/wiki/Q2306"}},
        {"type": "official homepage", "url": {"resource": "https://www.pinkfloyd.com/"}},
        {"type": "image", "url": {"resource": "https://commons.wikimedia.org/wiki/File:Pink_Floyd_-_all_members.jpg"}},
        {"type": "image", "url": {"resource": "https://example.com/some.jpg"}},
    ]
}
WIKIDATA = {
    "entities": {
        "Q2306": {
            "claims": {
                "P18": [{"rank": "normal", "mainsnak": {"datavalue": {"value": "Pink Floyd 1973.jpg"}}},
                        {"rank": "preferred", "mainsnak": {"datavalue": {"value": "Pink Floyd - all members.jpg"}}}],
                "P154": [{"mainsnak": {"datavalue": {"value": "Pink Floyd logo.svg"}}}],
                "P569": [{"mainsnak": {"datavalue": {"value": {"time": "+1965"}}}}],
            }
        }
    }
}


def imageinfo(mime="image/jpeg", width=2000, height=1500, url="https://upload.wikimedia.org/x.jpg", **extra):
    info = {"url": url, "width": width, "height": height, "mime": mime, "size": 123456,
            "thumburl": "https://upload.wikimedia.org/thumb/800px-x.jpg", "thumbwidth": 800, "thumbheight": 600,
            "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 3.0"}, "Artist": {"value": '<a href="u">Some <b>Photographer</b></a>'}}}
    info.update(extra)
    return {"query": {"pages": {"1": {"imageinfo": [info]}}}}


def test_relations_pick_wikidata_and_commons_files_only():
    qid, files = relations(MB_ARTIST)
    assert qid == "Q2306" and files == ["Pink Floyd - all members.jpg"]
    assert relations({}) == (None, [])


def test_wikidata_claims_photo_and_logo_preferred_first_confidence():
    got = claim_files(WIKIDATA, "Q2306")
    names = {n: (art, conf) for n, art, conf in got}
    assert names["Pink Floyd 1973.jpg"][0] == ArtType.ARTIST_THUMB
    assert names["Pink Floyd - all members.jpg"][1] > names["Pink Floyd 1973.jpg"][1]  # the preferred claim
    assert names["Pink Floyd logo.svg"][0] == ArtType.ARTIST_LOGO
    assert claim_files({}, "Q1") == []


def test_commons_raster_keeps_real_size_licence_and_author_without_markup():
    c = parse_imageinfo(imageinfo(), "x.jpg", ArtType.ARTIST_THUMB, 0.9)
    assert (c.width, c.height, c.tier) == (2000, 1500, Tier.A) and c.dims_known
    assert c.url == "https://upload.wikimedia.org/x.jpg" and c.provider == "wikimedia"
    assert "CC BY-SA 3.0" in c.comment and "Some Photographer" in c.comment and "<" not in c.comment


def test_commons_svg_logo_is_fetched_as_the_rendered_png_and_other_media_are_skipped():
    c = parse_imageinfo(imageinfo(mime="image/svg+xml", url="https://upload.wikimedia.org/logo.svg"), "logo.svg", ArtType.ARTIST_LOGO, 0.8)
    assert c.url.endswith("800px-x.jpg") and (c.width, c.height) == (800, 600) and c.art_type == ArtType.ARTIST_LOGO
    assert parse_imageinfo(imageinfo(mime="video/webm"), "v.webm", ArtType.ARTIST_THUMB, 0.9) is None
    assert parse_imageinfo({}, "x", ArtType.ARTIST_THUMB, 0.9) is None


def wiki_routes():
    return {
        f"https://musicbrainz.org/ws/2/artist/{ART}": MB_ARTIST,
        "https://www.wikidata.org/wiki/Special:EntityData/Q2306.json": WIKIDATA,
        "https://commons.wikimedia.org/w/api.php": imageinfo(),
    }


def test_wikimedia_provider_end_to_end_and_deduplicates_files():
    http = FakeHttp(wiki_routes())
    got = Wikimedia(http, Settings.from_mapping({})).search(Q)
    assert {c.art_type for c in got} == {ArtType.ARTIST_THUMB, ArtType.ARTIST_LOGO}
    assert all(c.tier == Tier.A for c in got)
    # "Pink Floyd - all members.jpg" is both a linked file and a Wikidata claim: fetched once
    assert sum("all+members" in u or "all%20members" in u for u in http.calls) == 1


def test_wikimedia_needs_an_artist_mbid_and_respects_the_switch_and_compilations():
    http = FakeHttp(wiki_routes())
    s = Settings.from_mapping({})
    assert Wikimedia(http, s).search(Query(artist="Pink Floyd", album="Animals")) == []
    assert Wikimedia(http, Settings.from_mapping({"artist_art": False})).search(Q) == []
    assert Wikimedia(http, s).search(Query(artist="Various Artists", album="Now", artist_mbid=ART)) == []
    assert http.calls == []  # nothing was requested in any of those cases
    assert is_various("Various Artists") and is_various("various") and not is_various("Various Cruelties")


def test_wikimedia_reports_a_failing_service_as_an_error_not_as_nothing_found():
    http = FakeHttp({f"https://musicbrainz.org/ws/2/artist/{ART}": 503})
    with pytest.raises(HttpError):                 # (the run says "error", never "0 found")
        Wikimedia(http, Settings.from_mapping({})).search(Q)
    assert Wikimedia(FakeHttp({}), Settings.from_mapping({})).search(Q) == []      # (404: no such artist)
    routes = wiki_routes()
    routes["https://commons.wikimedia.org/w/api.php"] = 503
    with pytest.raises(HttpError):                 # (every Commons file failed)
        Wikimedia(FakeHttp(routes), Settings.from_mapping({})).search(Q)
    routes = wiki_routes()
    routes["https://www.wikidata.org/wiki/Special:EntityData/Q2306.json"] = 500
    got = Wikimedia(FakeHttp(routes), Settings.from_mapping({})).search(Q)
    assert [c.art_type for c in got] == [ArtType.ARTIST_THUMB]  # the linked Commons file still arrives


DEEZER_ARTIST = {"data": [
    {"id": 5, "name": "Pink Floyd Tribute Band", "picture_xl": "https://cdn/x/1000x1000.jpg", "picture_medium": "https://cdn/m.jpg"},
    {"id": 6, "name": "Pink Floyd", "picture_xl": "https://e-cdns-images.dzcdn.net/images/artist/abc123/1000x1000-000000-80-0-0.jpg",
     "picture_medium": "https://cdn/m6.jpg", "nb_fan": 4000000},
]}


def test_deezer_artist_photo_needs_the_same_name_and_a_real_picture():
    got = parse_deezer_artist(DEEZER_ARTIST, Q)
    assert len(got) == 1 and got[0].provider_id == "artist:6" and got[0].art_type == ArtType.ARTIST_THUMB
    assert got[0].tier == Tier.C and (got[0].width, got[0].height) == (1000, 1000) and got[0].likes == 4000000
    placeholder = {"data": [{"id": 6, "name": "Pink Floyd", "picture_xl": "https://e-cdns-images.dzcdn.net/images/artist//1000x1000-000000-80-0-0.jpg"}]}
    assert parse_deezer_artist(placeholder, Q) == []
    assert parse_deezer_artist({}, Q) == []


def test_deezer_provider_searches_the_artist_only_when_artist_images_are_on():
    routes = {"https://api.deezer.com/search/album": {"data": []}, "https://api.deezer.com/search/artist": DEEZER_ARTIST}
    http = FakeHttp(routes)
    got = Deezer(http, Settings.from_mapping({})).search(Q)
    assert [c.art_type for c in got] == [ArtType.ARTIST_THUMB]
    http2 = FakeHttp(routes)
    assert Deezer(http2, Settings.from_mapping({"artist_art": False})).search(Q) == []
    assert not any("search/artist" in u for u in http2.calls)


def test_discogs_artist_page_photos():
    artist = {"id": 45467, "name": "Genesis (2)", "images": [
        {"type": "primary", "uri": "https://i.discogs.com/p.jpg", "uri150": "https://i.discogs.com/p150.jpg", "width": 600, "height": 600},
        {"type": "secondary", "uri": "https://i.discogs.com/s.jpg", "width": 400, "height": 300},
        {"type": "secondary", "uri": "", "resource_url": ""},
    ]}
    got = parse_artist_images(artist, Tier.A)
    assert len(got) == 2 and all(c.art_type == ArtType.ARTIST_THUMB and c.tier == Tier.A for c in got)
    assert got[0].type_confidence > got[1].type_confidence and got[0].thumb_url.endswith("p150.jpg")
    assert got[0].comment == "Discogs artist: Genesis"  # the namesake number is dropped


@pytest.mark.parametrize("provider", ["fanart", "audiodb"])
def test_fanart_and_audiodb_skip_artist_requests_when_switched_off(provider):
    from coverup.providers import REGISTRY

    http = FakeHttp({})
    s = Settings.from_mapping({"artist_art": False, "fanart_api_key": "k", "audiodb_api_key": "123"})
    REGISTRY[provider](http, s).search(Query(artist="A", album="B", artist_mbid=ART))
    assert not any(ART in u for u in http.calls)


def test_discogs_outage_is_an_error_not_nothing_found():
    from coverup.providers.discogs import API, Discogs
    s = Settings.from_mapping({"discogs_token": "t"})
    q = Query(artist="Pink Floyd", album="Animals", barcode="0123", discogs_release_id=99)
    routes = {f"{API}/releases/99": 503, f"{API}/database/search": {"results": [{"id": 7}]}, f"{API}/releases/7": 502}
    with pytest.raises(HttpError):
        Discogs(FakeHttp(routes), s).search(q)
    routes = {f"{API}/releases/99": 404, f"{API}/database/search": {"results": []}}
    assert Discogs(FakeHttp(routes), s).search(q) == []          # (really nothing there)
