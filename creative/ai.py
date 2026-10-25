# -*- coding: utf-8 -*-
# CoverUp: MusicBrainz Picard plugin. GPL-2.0-or-later.
"""AI image-generation backends. All are configured by the user with their own endpoint and key;
CoverUp bundles and hosts nothing.

- automatic1111: a local Stable Diffusion web UI started with ``--api`` (``/sdapi/v1/txt2img``, ``img2img``)
- openai: any OpenAI-compatible ``/v1/images/generations`` endpoint
- custom: POST JSON ``{prompt, negative_prompt, width, height, seed, n}``; the response may contain
  ``images: [base64]``, ``image: base64`` or ``data: [{b64_json | url}]``
- cloudflare: Cloudflare Workers AI text-to-image (``/client/v4/accounts/{id}/ai/run/{model}``), free daily
  allowance on a free account. FLUX.1 schnell answers JSON ``{result: {image: base64}}``; the SDXL models
  answer raw PNG bytes.
- aihorde: AI Horde (aihorde.net), crowdsourced volunteer GPUs. Asynchronous: submit, poll ``check``, then read
  ``status``; the job is cancelled (DELETE) when it takes longer than the user's limit.

The last two are remote services, so ``generate`` asks for consent before using them like any other.
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import time
import urllib.parse
from dataclasses import dataclass

from ..net import HttpClient, HttpError

log = logging.getLogger("coverup.creative.ai")

BACKENDS = ("none", "automatic1111", "openai", "custom", "cloudflare", "aihorde")


class AIServiceError(Exception):
    """An AI service refused a request or could not finish it. The message is meant for the user."""


def _service_error(service: str, exc: HttpError) -> AIServiceError:
    msg = exc.api_message()
    return AIServiceError(f"{service} answered HTTP {exc.status}" + (f": {msg}" if msg else ""))


def _looks_like_image(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n" or data[:3] == b"\xff\xd8\xff" or (data[:4] == b"RIFF" and data[8:12] == b"WEBP")


@dataclass
class GenRequest:
    prompt: str
    negative: str
    size: int
    seed: int
    n: int = 1
    reference: bytes | None = None  # image-to-image source (e.g. the low-resolution cover)
    strength: float = 0.55  # img2img denoising: lower stays closer to the reference


def is_remote(url: str) -> bool:
    """True unless the host is localhost or a private/LAN address."""
    host = urllib.parse.urlsplit(url).hostname or ""
    if host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local)
    except ValueError:
        return True


def host_of(url: str) -> str:
    return urllib.parse.urlsplit(url).hostname or url


def _b64(s: str) -> bytes:
    if "," in s[:100] and s.startswith("data:"):
        s = s.split(",", 1)[1]
    return base64.b64decode(s)


def decode_images(payload, http: HttpClient | None = None) -> list[bytes]:
    """Accept the common response shapes of image APIs."""
    out: list[bytes] = []
    if not isinstance(payload, dict):
        return out
    for img in payload.get("images") or []:
        if isinstance(img, str):
            out.append(_b64(img))
    if isinstance(payload.get("image"), str):
        out.append(_b64(payload["image"]))
    for item in payload.get("data") or []:
        if isinstance(item, dict):
            if item.get("b64_json"):
                out.append(_b64(item["b64_json"]))
            elif item.get("url") and http is not None:
                out.append(http.get(item["url"], cache=False).data)
    return out


class Backend:
    NAME = "none"

    def __init__(self, http: HttpClient, url: str, api_key: str = "", model: str = "", steps: int = 30):
        self.http = http
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.steps = steps

    def supports_img2img(self) -> bool:
        return False

    def generate(self, req: GenRequest) -> list[bytes]:
        raise NotImplementedError


class Automatic1111(Backend):
    NAME = "automatic1111"

    def supports_img2img(self) -> bool:
        return True

    def generate(self, req: GenRequest) -> list[bytes]:
        body = {
            "prompt": req.prompt,
            "negative_prompt": req.negative,
            "width": req.size,
            "height": req.size,
            "seed": req.seed,
            "steps": self.steps,
            "batch_size": req.n,
            "n_iter": 1,
        }
        endpoint = "/sdapi/v1/txt2img"
        if req.reference:
            body["init_images"] = [base64.b64encode(req.reference).decode("ascii")]
            body["denoising_strength"] = req.strength
            endpoint = "/sdapi/v1/img2img"
        if self.model:
            body["override_settings"] = {"sd_model_checkpoint": self.model}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        return decode_images(self.http.post_json(self.url + endpoint, body, headers, timeout=600))


class OpenAICompatible(Backend):
    NAME = "openai"

    def generate(self, req: GenRequest) -> list[bytes]:
        base = self.url if self.url.endswith("/v1") else self.url + "/v1"
        body = {
            "prompt": f"{req.prompt}\nAvoid: {req.negative}",
            "n": req.n,
            "size": f"{req.size}x{req.size}",
        }
        if self.model:
            body["model"] = self.model
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            payload = self.http.post_json(base + "/images/generations", body, headers, timeout=600)
        except HttpError as exc:
            if exc.status == 400 and req.n > 1:  # some models only allow n=1
                out = []
                for _ in range(req.n):
                    out += decode_images(self.http.post_json(base + "/images/generations", {**body, "n": 1}, headers, timeout=600), self.http)
                return out
            raise
        return decode_images(payload, self.http)


class CustomHttp(Backend):
    NAME = "custom"

    def supports_img2img(self) -> bool:
        return True

    def generate(self, req: GenRequest) -> list[bytes]:
        body = {
            "prompt": req.prompt, "negative_prompt": req.negative, "width": req.size, "height": req.size,
            "seed": req.seed, "n": req.n, "model": self.model or None,
        }
        if req.reference:
            body["init_image"] = base64.b64encode(req.reference).decode("ascii")
            body["strength"] = req.strength
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        return decode_images(self.http.post_json(self.url, body, headers, timeout=600), self.http)


# ---------------------------------------------------------------------------------- Cloudflare Workers AI
CLOUDFLARE_API = "https://api.cloudflare.com/client/v4/accounts"
CLOUDFLARE_DEFAULT_MODEL = "@cf/black-forest-labs/flux-1-schnell"


@dataclass(frozen=True)
class CloudflareModel:
    steps_key: str  # FLUX and Lucid Origin call it "steps", the SDXL models and Phoenix "num_steps"
    max_steps: int
    size: tuple[int, int] | None  # accepted width/height range; None = the model takes no size
    negative: bool  # accepts negative_prompt


# From each model's input schema on developers.cloudflare.com/workers-ai/models/
CLOUDFLARE_MODELS = {
    "@cf/black-forest-labs/flux-1-schnell": CloudflareModel("steps", 8, None, False),
    "@cf/stabilityai/stable-diffusion-xl-base-1.0": CloudflareModel("num_steps", 20, (256, 2048), True),
    "@cf/bytedance/stable-diffusion-xl-lightning": CloudflareModel("num_steps", 20, (256, 2048), True),
    "@cf/leonardo/lucid-origin": CloudflareModel("steps", 40, (256, 2500), False),
    "@cf/leonardo/phoenix-1.0": CloudflareModel("num_steps", 50, (256, 2048), True),
}
# A model typed in by hand: send only what every text-to-image model takes
_CLOUDFLARE_OTHER = CloudflareModel("steps", 50, None, False)


class CloudflareWorkersAI(Backend):
    NAME = "cloudflare"
    SERVICE = "Cloudflare Workers AI"

    def __init__(self, http: HttpClient, account_id: str, api_token: str, model: str = "", steps: int = 4):
        acct = urllib.parse.quote(account_id.strip(), safe="")
        super().__init__(http, f"{CLOUDFLARE_API}/{acct}/ai/run", api_token.strip(), model.strip() or CLOUDFLARE_DEFAULT_MODEL, steps)

    @classmethod
    def from_settings(cls, http: HttpClient, settings) -> "CloudflareWorkersAI":
        account, token = str(settings["ai_cf_account_id"] or "").strip(), str(settings["ai_cf_api_token"] or "").strip()
        if not account or not token:
            raise AIServiceError("Cloudflare Workers AI needs your account ID and an API token (Options > Plugins > CoverUp > Create)")
        return cls(http, account, token, str(settings["ai_cf_model"] or ""), int(settings["ai_cf_steps"] or 4))

    def spec(self) -> CloudflareModel:
        return CLOUDFLARE_MODELS.get(self.model, _CLOUDFLARE_OTHER)

    def body(self, req: GenRequest, seed: int) -> dict:
        spec = self.spec()
        body: dict = {"prompt": req.prompt, spec.steps_key: max(1, min(spec.max_steps, int(self.steps))), "seed": seed}
        if spec.size:
            lo, hi = spec.size
            side = max(lo, min(hi, int(req.size)))
            body["width"] = body["height"] = side - side % 8
        if spec.negative and req.negative:
            body["negative_prompt"] = req.negative
        return body

    def generate(self, req: GenRequest) -> list[bytes]:
        url = f"{self.url}/{urllib.parse.quote(self.model, safe='@/.-_')}"
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "image/*, application/json"}
        out: list[bytes] = []
        for i in range(max(1, req.n)):  # one image per call
            try:
                resp = self.http.post(url, self.body(req, req.seed + i), headers, timeout=300)
                out += self.decode(resp)
            except (HttpError, AIServiceError) as exc:
                err = _service_error(self.SERVICE, exc) if isinstance(exc, HttpError) else exc
                if not out:
                    raise err from None
                log.warning("%s stopped after %d image(s): %s", self.SERVICE, len(out), err)
                break
        return out

    def decode(self, resp) -> list[bytes]:
        """FLUX answers JSON with a base64 JPEG; the SDXL models answer the PNG itself."""
        ctype = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
        if ctype.startswith("image/") or (ctype != "application/json" and _looks_like_image(resp.data)):
            return [resp.data]
        try:
            payload = resp.json()
        except (ValueError, UnicodeDecodeError):
            raise AIServiceError(f"{self.SERVICE} sent a response CoverUp does not understand ({ctype or 'no content type'})") from None
        if not isinstance(payload, dict):
            return []
        if payload.get("success") is False:
            errors = [e.get("message", "") for e in payload.get("errors") or [] if isinstance(e, dict)]
            raise AIServiceError(f"{self.SERVICE}: {'; '.join(e for e in errors if e) or 'the request failed'}")
        result = payload.get("result", payload)
        return decode_images(result if isinstance(result, dict) else {}, self.http)


# ------------------------------------------------------------------------------------------------ AI Horde
HORDE_API = "https://aihorde.net/api/v2"
HORDE_ANONYMOUS_KEY = "0000000000"
HORDE_DEFAULT_MODEL = "AlbedoBase XL (SDXL)"
HORDE_CLIENT_AGENT = "CoverUp:{version}:https://github.com/herculepirate/picard-coverup"


class _HordeTimeout(Exception):
    def __init__(self, queue_position):
        super().__init__("timed out")
        self.queue_position = queue_position


class AIHorde(Backend):
    NAME = "aihorde"
    SERVICE = "AI Horde"
    STEPS = 25

    def __init__(self, http: HttpClient, api_key: str = "", model: str = "", max_wait: int = 300, sleep=None, clock=None):
        super().__init__(http, HORDE_API, api_key.strip() or HORDE_ANONYMOUS_KEY, model.strip() or HORDE_DEFAULT_MODEL, self.STEPS)
        self.max_wait = max(10, int(max_wait))
        self._sleep = sleep or http._sleep  # cancellable: raises net.Cancelled when the user stops the run
        self._clock = clock or time.monotonic

    @classmethod
    def from_settings(cls, http: HttpClient, settings) -> "AIHorde":
        return cls(http, str(settings["ai_horde_api_key"] or ""), str(settings["ai_horde_model"] or ""), int(settings["ai_horde_max_wait"] or 300))

    @property
    def anonymous(self) -> bool:
        return self.api_key == HORDE_ANONYMOUS_KEY

    def headers(self) -> dict[str, str]:
        return {"apikey": self.api_key, "Client-Agent": HORDE_CLIENT_AGENT.format(version=getattr(self.http, "version", "0"))}

    def side(self, size: int) -> int:
        """Width and height must be multiples of 64; anonymous requests stay within 1024 px."""
        hi = 1024 if self.anonymous else 2048
        return max(512, min(hi, int(round(int(size) / 64)) * 64))

    def body(self, req: GenRequest) -> dict:
        side = self.side(req.size)
        n = max(1, min(20, req.n))
        params: dict = {"width": side, "height": side, "steps": self.STEPS, "n": n, "sampler_name": "k_euler_a", "cfg_scale": 7}
        if n == 1:  # with several images one fixed seed could repeat the same picture: let the Horde pick
            params["seed"] = str(req.seed)
        prompt = f"{req.prompt} ### {req.negative}" if req.negative.strip() else req.prompt  # "###" starts the negative prompt
        return {"prompt": prompt, "params": params, "models": [self.model], "nsfw": False, "censor_nsfw": True, "r2": True}

    def generate(self, req: GenRequest) -> list[bytes]:
        headers = self.headers()
        try:
            job = self.http.post_json(f"{self.url}/generate/async", self.body(req), headers, timeout=60)
        except HttpError as exc:
            raise _service_error(self.SERVICE, exc) from None
        job_id = job.get("id") if isinstance(job, dict) else None
        if not job_id:
            raise AIServiceError(f"{self.SERVICE} did not accept the request: {(job or {}).get('message') or 'no job id'}")
        log.info("AI Horde job %s queued (model %s, about %s kudos)", job_id, self.model, job.get("kudos", "?"))
        try:
            status = self._wait_for(job_id, headers)
        except _HordeTimeout as exc:
            images = self.images(self._cancel(job_id, headers))
            if images:
                log.warning("AI Horde did not finish within %d s; using the %d image(s) made so far", self.max_wait, len(images))
                return images
            where = f" (still at queue position {exc.queue_position})" if exc.queue_position else ""
            raise AIServiceError(
                f"{self.SERVICE} did not finish within {self.max_wait} s{where}, so the request was cancelled. "
                "Try again later, raise the waiting time, or use a registered API key for priority."
            ) from None
        except BaseException:  # errors and cancellation: free the volunteers' queue
            self._cancel(job_id, headers)
            raise
        return self.images(status)

    def _wait_for(self, job_id: str, headers: dict[str, str]) -> dict:
        deadline = self._clock() + self.max_wait
        while True:
            try:
                check = self.http.get_json(f"{self.url}/generate/check/{job_id}", headers, cache=False)
            except HttpError as exc:
                raise _service_error(self.SERVICE, exc) from None
            if check.get("faulted"):
                raise AIServiceError(f"{self.SERVICE}: the request failed on the server")
            if check.get("done"):
                break
            if check.get("is_possible") is False:
                raise AIServiceError(f"{self.SERVICE}: no worker can serve model {self.model!r} with these settings right now; try another model")
            remaining = deadline - self._clock()
            if remaining <= 0:
                raise _HordeTimeout(check.get("queue_position"))
            wait = float(check.get("wait_time") or 0)
            log.debug("AI Horde job %s: queue position %s, about %.0f s left", job_id, check.get("queue_position"), wait)
            self._sleep(min(max(2.0, min(10.0, wait)), max(1.0, remaining)))
        try:
            return self.http.get_json(f"{self.url}/generate/status/{job_id}", headers, cache=False)
        except HttpError as exc:
            raise _service_error(self.SERVICE, exc) from None

    def _cancel(self, job_id: str, headers: dict[str, str]) -> dict:
        """DELETE the job (also after the user cancelled). Returns its final status, which lists any finished images."""
        try:
            resp = self.http.delete(f"{self.url}/generate/status/{job_id}", headers, timeout=30, force=True)
            log.info("AI Horde job %s cancelled", job_id)
            payload = resp.json()
            return payload if isinstance(payload, dict) else {}
        except Exception as exc:
            log.debug("Could not cancel AI Horde job %s: %s", job_id, exc)
            return {}

    def images(self, status: dict) -> list[bytes]:
        """generations[].img is a short-lived download link when r2 is on (fetch it now), else a base64 WebP."""
        out: list[bytes] = []
        for g in (status or {}).get("generations") or []:
            if not isinstance(g, dict):
                continue
            if g.get("censored"):
                log.info("An AI Horde worker's safety filter blanked one image; skipped")
                continue
            img = g.get("img")
            if not isinstance(img, str) or not img:
                continue
            if img.startswith(("https://", "http://")):
                try:
                    out.append(self.http.get(img, cache=False).data)
                except HttpError as exc:
                    log.warning("Could not download an AI Horde image: %s", exc)
            else:
                out.append(_b64(img))
        return out


def make_backend(name: str, http: HttpClient, settings) -> Backend | None:
    """The configured backend, or None for "none". Raises AIServiceError when a service lacks required settings."""
    if name == "cloudflare":
        return CloudflareWorkersAI.from_settings(http, settings)
    if name == "aihorde":
        return AIHorde.from_settings(http, settings)
    cls = {"automatic1111": Automatic1111, "openai": OpenAICompatible, "custom": CustomHttp}.get(name)
    if not cls:
        return None
    return cls(http, settings["ai_url"], settings["ai_api_key"], settings["ai_model"], int(settings["ai_steps"]))
