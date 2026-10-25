"""The free AI services (Cloudflare Workers AI and AI Horde) against stubbed HTTP: request shapes, both Cloudflare
response shapes, the AI Horde submit / poll / status / cancel flow, decoding, consent and secret handling."""

import pytest

pytest.importorskip("PyQt6.QtGui", reason="PyQt6 is needed for image tests (pip install PyQt6)")

import base64
import logging

from coverup import imaging
from coverup.creative import ai
from coverup.creative.generate import ConsentRequired, CreativeOptions, generate
from coverup.creative.template_engine import load_templates
from coverup.model import Query
from coverup.net import Cancelled, HttpError, Response, redact_url
from coverup.settings import DEFAULTS, Settings
from helpers import FakeHttp, make_image

pytestmark = pytest.mark.usefixtures("qapp")
Q = Query(artist="Nightfall", album="Silver Horizons", year=1984, genre="Synthpop")
ACCOUNT, TOKEN = "acc0123456789abcdef", "cf-token-SECRET-42"
CF = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT}/ai/run/"
FLUX = "@cf/black-forest-labs/flux-1-schnell"
SDXL = "@cf/stabilityai/stable-diffusion-xl-base-1.0"
HORDE = "https://aihorde.net/api/v2"


def S(**kw):
    return Settings.from_mapping(kw)


def cf_settings(**kw):
    return S(ai_backend="cloudflare", ai_cf_account_id=ACCOUNT, ai_cf_api_token=TOKEN, ai_size=256,
             ai_consented_hosts=["api.cloudflare.com"], **kw)


def horde_settings(**kw):
    return S(ai_backend="aihorde", ai_size=256, ai_consented_hosts=["aihorde.net"], **kw)


def opts(count=1, seed=5):
    return CreativeOptions("ai", load_templates()["art"], count=count, seed=seed)


def jpeg_b64():
    return base64.b64encode(make_image("a", 256)).decode()


# ------------------------------------------------------------------------------------------- settings
def test_new_services_are_registered_with_defaults():
    assert {"cloudflare", "aihorde"} <= set(ai.BACKENDS)
    assert DEFAULTS["ai_cf_model"] == FLUX and DEFAULTS["ai_cf_steps"] == 4
    assert DEFAULTS["ai_horde_api_key"] == "0000000000" and DEFAULTS["ai_horde_model"] == "AlbedoBase XL (SDXL)"
    assert DEFAULTS["ai_horde_max_wait"] == 300


def test_tokens_are_secret_and_the_anonymous_horde_key_is_not():
    s = S(ai_cf_api_token=TOKEN, ai_cf_account_id=ACCOUNT)
    assert TOKEN in s.secrets() and ACCOUNT in s.secrets() and "0000000000" not in s.secrets()
    red = s.redacted()
    assert red["ai_cf_api_token"] == "***set***" and red["ai_horde_api_key"] == "anonymous key"
    assert S(ai_horde_api_key="my-registered-key").redacted()["ai_horde_api_key"] == "***set***"
    assert "my-registered-key" in S(ai_horde_api_key="my-registered-key").secrets()


def test_cloudflare_account_id_is_masked_in_logged_urls():
    assert ACCOUNT not in redact_url(CF + FLUX) and "/accounts/***/ai/run/" in redact_url(CF + FLUX)


# --------------------------------------------------------------------------------- Cloudflare Workers AI
def test_cloudflare_flux_request_shape_and_json_response():
    http = FakeHttp({CF + FLUX: {"result": {"image": jpeg_b64()}, "success": True, "errors": [], "messages": []}})
    out = generate(cf_settings(), http, Q, opts(count=2, seed=5))
    assert len(out) == 2 and out[0].extra["method"] == "ai" and out[0].extra["backend"] == "cloudflare"
    assert out[0].extra["model"] == FLUX and imaging.size_of(out[0].data)[0] > 0
    assert [u for u, _b in http.posts] == [CF + FLUX] * 2  # one image per call
    body = http.posts[0][1]
    assert set(body) == {"prompt", "steps", "seed"}  # FLUX takes no size or negative prompt
    assert body["steps"] == 4 and "Silver Horizons" in body["prompt"]
    assert [b["seed"] for _u, b in http.posts] == [5, 6]
    method, url, headers = http.sent[0]
    assert method == "POST" and headers["Authorization"] == f"Bearer {TOKEN}"


def test_cloudflare_steps_are_capped_per_model():
    http = FakeHttp({CF: {"result": {"image": jpeg_b64()}, "success": True}})
    generate(cf_settings(ai_cf_steps=30), http, Q, opts())
    assert http.posts[-1][1]["steps"] == 8  # FLUX.1 schnell maximum
    generate(cf_settings(ai_cf_steps=30, ai_cf_model=SDXL), http, Q, opts())
    assert http.posts[-1][1]["num_steps"] == 20 and "steps" not in http.posts[-1][1]


def test_cloudflare_sdxl_raw_png_response_with_size_and_negative():
    png = make_image("c", 256, fmt="png")
    http = FakeHttp({CF + SDXL: png})
    out = generate(cf_settings(ai_cf_model=SDXL, ai_cf_steps=12), http, Q, opts())
    assert len(out) == 1 and out[0].extra["model"] == SDXL
    url, body = http.posts[0]
    assert url == CF + SDXL
    assert body["width"] == body["height"] == 256 and body["num_steps"] == 12 and body["seed"] == 5
    assert "text" in body["negative_prompt"]


def test_cloudflare_size_is_clamped_to_the_model_range():
    b = ai.CloudflareWorkersAI(FakeHttp(), ACCOUNT, TOKEN, SDXL, 4)
    req = ai.GenRequest("p", "n", 4000, 1)
    assert b.body(req, 1)["width"] == 2048
    assert b.body(ai.GenRequest("p", "n", 100, 1), 1)["width"] == 256
    assert b.body(ai.GenRequest("p", "n", 1023, 1), 1)["width"] == 1016  # multiple of 8
    other = ai.CloudflareWorkersAI(FakeHttp(), ACCOUNT, TOKEN, "@cf/someone/new-model", 4).body(req, 1)
    assert set(other) == {"prompt", "steps", "seed"}  # unknown models get only the common fields


def test_cloudflare_raw_image_without_content_type_is_recognised():
    png = make_image("b", 64, fmt="png")
    b = ai.CloudflareWorkersAI(FakeHttp(), ACCOUNT, TOKEN, SDXL)
    assert b.decode(Response("u", 200, png, {})) == [png]
    assert b.decode(Response("u", 200, png, {"content-type": "image/png"})) == [png]
    jpeg = make_image("a", 64)
    payload = ('{"result": {"image": "%s"}, "success": true}' % base64.b64encode(jpeg).decode()).encode()
    assert b.decode(Response("u", 200, payload, {"content-type": "application/json; charset=utf-8"})) == [jpeg]


def test_cloudflare_errors_are_explained():
    http = FakeHttp({CF + FLUX: {"result": None, "success": False, "errors": [{"code": 3036, "message": "daily free allocation used up"}]}})
    with pytest.raises(ai.AIServiceError, match="daily free allocation used up"):
        generate(cf_settings(), http, Q, opts())

    def refuse(url):
        raise HttpError(401, url, body=b'{"success": false, "errors": [{"code": 10000, "message": "Authentication error"}]}')

    with pytest.raises(ai.AIServiceError, match="HTTP 401: Authentication error"):
        generate(cf_settings(), FakeHttp({CF + FLUX: refuse}), Q, opts())


def test_cloudflare_keeps_images_made_before_a_later_call_fails():
    calls = []

    def second_fails(url):
        calls.append(url)
        if len(calls) > 1:
            raise HttpError(429, url)
        return {"result": {"image": jpeg_b64()}, "success": True}

    out = generate(cf_settings(), FakeHttp({CF + FLUX: second_fails}), Q, opts(count=3))
    assert len(out) == 1 and len(calls) == 2


def test_cloudflare_needs_account_and_token_before_anything_is_sent():
    http = FakeHttp()
    with pytest.raises(ai.AIServiceError, match="account ID and an API token"):
        generate(S(ai_backend="cloudflare", ai_cf_api_token=TOKEN, ai_consented_hosts=["api.cloudflare.com"]), http, Q, opts())
    assert http.posts == []


def test_cloudflare_is_remote_and_asks_for_consent_first():
    http = FakeHttp({CF: {"result": {"image": jpeg_b64()}, "success": True}})
    s = cf_settings().with_(ai_consented_hosts=[])
    b = ai.make_backend("cloudflare", http, s)
    assert ai.is_remote(b.url) and ai.host_of(b.url) == "api.cloudflare.com" and not b.supports_img2img()
    with pytest.raises(ConsentRequired) as exc:
        generate(s, http, Q, opts())
    assert exc.value.host == "api.cloudflare.com" and http.posts == []


def test_cloudflare_token_never_reaches_the_log(caplog):
    http = FakeHttp({CF + FLUX: {"result": {"image": jpeg_b64()}, "success": True}})
    with caplog.at_level(logging.DEBUG, logger="coverup"):
        generate(cf_settings(), http, Q, opts())
    assert caplog.records and TOKEN not in caplog.text


# ------------------------------------------------------------------------------------------- AI Horde
class Horde:
    """A scripted AI Horde: the job finishes after ``polls_until_done`` checks (never when None)."""

    def __init__(self, polls_until_done=1, generations=None, check=None, deleted_generations=()):
        self.polls = 0
        self.polls_until_done = polls_until_done
        self.check_extra = check or {}
        self.generations = generations if generations is not None else [{"img": "https://r2.example/img1.webp", "seed": "5", "id": "g1", "censored": False}]
        self.deleted_generations = list(deleted_generations)

    def routes(self, image=None):
        return {
            f"{HORDE}/generate/async": {"id": "job-1", "kudos": 12.0},
            f"{HORDE}/generate/check/job-1": self.check,
            f"{HORDE}/generate/status/job-1": lambda url: {"done": True, "generations": self.generations},
            "https://r2.example/": image if image is not None else make_image("c", 256),
        }

    def check(self, url):
        self.polls += 1
        done = self.polls_until_done is not None and self.polls >= self.polls_until_done
        return {"finished": int(done), "processing": 0, "restarted": 0, "waiting": int(not done), "done": done, "faulted": False,
                "wait_time": 30, "queue_position": 7, "kudos": 12.0, "is_possible": True, **self.check_extra}


class Clock:
    def __init__(self):
        self.now = 1000.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def horde_backend(http, clock, **kw):
    return ai.AIHorde(http, kw.pop("api_key", ""), kw.pop("model", ""), kw.pop("max_wait", 300), sleep=clock.sleep, clock=clock)


def test_horde_request_shape_poll_and_r2_download():
    horde = Horde(polls_until_done=3)
    http = FakeHttp(horde.routes())
    clock = Clock()
    http._sleep = clock.sleep  # the backend sleeps through the client (cancellable)
    out = generate(horde_settings(), http, Q, opts(count=1, seed=5))
    assert len(out) == 1 and out[0].extra["backend"] == "aihorde" and out[0].extra["model"] == "AlbedoBase XL (SDXL)"
    url, body = http.posts[0]
    assert url == f"{HORDE}/generate/async"
    assert body["models"] == ["AlbedoBase XL (SDXL)"] and body["nsfw"] is False and body["censor_nsfw"] is True and body["r2"] is True
    prompt, _, negative = body["prompt"].partition(" ### ")
    assert "Silver Horizons" in prompt and "text" in negative
    assert body["params"] == {"width": 512, "height": 512, "steps": 25, "n": 1, "sampler_name": "k_euler_a", "cfg_scale": 7, "seed": "5"}
    for method, _u, headers in http.sent:
        if method != "GET" or "aihorde.net" in _u:
            assert headers["apikey"] == "0000000000"
            assert headers["Client-Agent"] == "CoverUp:test:https://github.com/herculepirate/picard-coverup"
    gets = [u for m, u, _h in http.sent if m == "GET"]
    assert gets == [f"{HORDE}/generate/check/job-1"] * 3 + [f"{HORDE}/generate/status/job-1", "https://r2.example/img1.webp"]
    assert clock.sleeps == [10.0, 10.0]  # wait_time 30 s, polled at most every 10 s
    assert http.deletes == []


def test_horde_base64_webp_images_and_censored_ones_are_skipped():
    webp = imaging.encode(imaging.load(make_image("a", 128)), "webp", 90)
    gens = [{"img": base64.b64encode(webp).decode(), "censored": False}, {"img": base64.b64encode(webp).decode(), "censored": True}]
    http = FakeHttp(Horde(generations=gens).routes())
    images = horde_backend(http, Clock()).generate(ai.GenRequest("p", "", 512, 1))
    assert images == [webp] and imaging.size_of(images[0]) == (128, 128)


def test_horde_size_is_a_multiple_of_64_and_capped_for_anonymous_use():
    b = horde_backend(FakeHttp(), Clock())
    assert b.side(256) == 512 and b.side(1000) == 1024 and b.side(1500) == 1024
    registered = horde_backend(FakeHttp(), Clock(), api_key="registered-key")
    assert registered.side(1500) == 1472 and registered.side(1520) == 1536 and registered.side(5000) == 2048 and registered.side(700) == 704
    assert all(s % 64 == 0 for s in (b.side(n) for n in range(100, 3000, 37)))


def test_horde_several_images_in_one_job_without_a_fixed_seed():
    b = horde_backend(FakeHttp(), Clock(), model="Juggernaut XL")
    body = b.body(ai.GenRequest("p", "", 1024, 9, n=3))
    assert body["params"]["n"] == 3 and "seed" not in body["params"] and body["models"] == ["Juggernaut XL"]
    assert body["prompt"] == "p"  # no negative: no separator


def test_horde_gives_up_after_max_wait_and_cancels_the_job():
    horde = Horde(polls_until_done=None)
    routes = horde.routes()
    routes[f"{HORDE}/generate/status/job-1"] = {"done": False, "generations": []}  # what the DELETE answers: nothing finished
    http = FakeHttp(routes)
    clock = Clock()
    with pytest.raises(ai.AIServiceError, match=r"did not finish within 30 s \(still at queue position 7\)"):
        horde_backend(http, clock, max_wait=30).generate(ai.GenRequest("p", "", 512, 1))
    assert http.deletes == [f"{HORDE}/generate/status/job-1"]
    assert sum(clock.sleeps) >= 30 and horde.polls >= 3


def test_horde_timeout_keeps_images_finished_before_the_cancel():
    horde = Horde(polls_until_done=None)
    routes = horde.routes()
    routes[f"{HORDE}/generate/status/job-1"] = lambda url: {"done": False, "generations": [{"img": "https://r2.example/partial.webp"}]}
    http = FakeHttp(routes)
    images = horde_backend(http, Clock(), max_wait=20).generate(ai.GenRequest("p", "", 512, 1, n=2))
    assert len(images) == 1 and http.deletes == [f"{HORDE}/generate/status/job-1"]


def test_horde_impossible_or_faulted_requests_are_cancelled_and_explained():
    http = FakeHttp(Horde(polls_until_done=None, check={"is_possible": False}).routes())
    with pytest.raises(ai.AIServiceError, match="no worker can serve model"):
        horde_backend(http, Clock()).generate(ai.GenRequest("p", "", 512, 1))
    assert http.deletes == [f"{HORDE}/generate/status/job-1"]
    http = FakeHttp(Horde(polls_until_done=None, check={"faulted": True}).routes())
    with pytest.raises(ai.AIServiceError, match="failed on the server"):
        horde_backend(http, Clock()).generate(ai.GenRequest("p", "", 512, 1))
    assert len(http.deletes) == 1


def test_horde_user_cancel_still_frees_the_job():
    http = FakeHttp(Horde(polls_until_done=None).routes())
    clock = Clock()

    def cancelled(_seconds):
        raise Cancelled()

    clock.sleep = cancelled
    with pytest.raises(Cancelled):
        horde_backend(http, clock).generate(ai.GenRequest("p", "", 512, 1))
    assert http.deletes == [f"{HORDE}/generate/status/job-1"]


def test_horde_refusal_message_is_shown():
    def refuse(url):
        raise HttpError(403, url, body=b'{"message": "Anonymous requests are limited to 1024x1024", "rc": "KudosUpfront"}')

    http = FakeHttp({f"{HORDE}/generate/async": refuse})
    with pytest.raises(ai.AIServiceError, match="HTTP 403: Anonymous requests are limited"):
        horde_backend(http, Clock()).generate(ai.GenRequest("p", "", 512, 1))
    assert http.deletes == []  # nothing was queued


def test_horde_is_remote_and_asks_for_consent_first():
    http = FakeHttp(Horde().routes())
    s = horde_settings().with_(ai_consented_hosts=[])
    b = ai.make_backend("aihorde", http, s)
    assert ai.is_remote(b.url) and ai.host_of(b.url) == "aihorde.net" and not b.supports_img2img()
    with pytest.raises(ConsentRequired) as exc:
        generate(s, http, Q, opts())
    assert exc.value.host == "aihorde.net" and http.posts == []


def test_horde_registered_key_is_sent_and_never_logged(caplog):
    http = FakeHttp(Horde().routes())
    http._sleep = Clock().sleep
    with caplog.at_level(logging.DEBUG, logger="coverup"):
        generate(horde_settings(ai_horde_api_key="registered-SECRET-key", ai_horde_model="Juggernaut XL"), http, Q, opts())
    assert http.sent[0][2]["apikey"] == "registered-SECRET-key" and http.posts[0][1]["models"] == ["Juggernaut XL"]
    assert "registered-SECRET-key" not in caplog.text
