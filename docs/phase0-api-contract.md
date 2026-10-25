# Phase 0: Picard 3.0 Plugin V3 API contract for CoverUp

Verified against the **Picard 3.0 source distribution** (`picard-3.0.tar.gz` from PyPI), mainly `picard/plugin3/api_impl.py`, `picard/coverart/`, `picard/file.py` and `pyproject.toml`, plus the Plugin V3 docs on GitHub (`docs/PLUGINSV3/`). Where the online docs and the source disagree, the source wins and the disagreement is noted.

## Environment
- Picard 3.0 requires **Python 3.10+**, **PyQt6 >= 6.6.1**, Windows 10+/macOS 13+ (Qt 6.6+ on Linux).
- Runtime dependencies bundled with Picard: `mutagen`, `PyQt6`, `PyYAML`, `PyJWT`, `Markdown`, `charset-normalizer`, `pygit2`, `tomlkit`, `discid`. **Pillow is not bundled**, so the pure `QImage` image path is mandatory (resolves open question 5). Plugins must not rely on `pip install`.

## Plugin layout and manifest
```
coverup/                 # plugin root (this repository root)
  MANIFEST.toml          # required
  __init__.py            # must define enable(api); may define disable()
```
Required `MANIFEST.toml` fields: `uuid` (UUID v4, never changes), `name` (1-100 chars), `description` (1-200 chars, one line), `api` (list, e.g. `["3.0"]`). Optional: `authors`, `maintainers`, `license` (SPDX), `license_url`, `long_description`, `categories` (`metadata`, `coverart`, `ui`, `scripting`, `formats`, `other`), `homepage`, `report_bugs_to`, `min_python_version`, i18n tables.

Local development: `picard-cli plugins install <path>`, `picard-cli plugins update <name>`, `picard-cli plugins info <name>`.

## Entry point and PluginApi (verified in `api_impl.py`)
`def enable(api: PluginApi)`. Relevant members:

| Need | API |
|---|---|
| Logging | `api.logger.debug/info/warning/error/exception` (online doc says `api.log`; source has `logger`) |
| Plugin settings | `api.plugin_config.register_option(name, default, title=..., bounds=...)`, `api.plugin_config['key']` (JSON-serialisable values) |
| Per-machine data (no profiles) | `api.plugin_persist` |
| Plugin install dir | `api.plugin_dir` |
| Global Picard settings | `api.global_config.setting` |
| HTTP | `api.web_service.get(host, path, handler, priority=True, important=False)` and the `get_url` / `download_url` helpers; handler signature `(response, reply, error)` |
| MusicBrainz lookups | `api.mb_api.get_release_by_id(id, handler, inc=[...])` |
| Tagger | `api.tagger` (`.window` for dialogs, `.load_album`, `.add_files`, ...) |
| Album background tasks | `api.add_album_task(album, task_id, description, timeout=None, request_factory=None, blocking=False)` and `api.complete_album_task(album, task_id)` (call in `finally`) |
| Context menu | `api.register_album_action / track / file / cluster / clusterlist (cls)` with `BaseAction` subclass: `TITLE`, `callback(self, objs)`; pass the class, `self.api` is injected |
| Tools menu | `api.register_tools_menu_action(cls)` (`MENU` tuple for submenus) |
| Options page | `api.register_options_page(cls)`; subclass `picard.plugin3.api.OptionsPage` with `NAME`, `TITLE`, `PARENT = "plugins"`, `load()`, `save()`, `__init__(self, api=None, parent=None)` |
| Cover art provider | `api.register_cover_art_provider(cls)`; subclass `CoverArtProvider` with `NAME`, `OPTIONS` (a `ProviderOptions` subclass), `queue_images()` |
| Cover art filter / processor | `register_cover_art_filter`, `register_cover_art_metadata_filter`, `register_cover_art_processor` |
| After a file is saved | `api.register_file_post_save_processor(function(api, file), priority=0)`; `file.filename` is the final path |
| Script variables | `api.register_script_variable(name, documentation=None, title=None, is_multi_value=False, is_from_mb=False)`; names starting with `_` are hidden from tag dropdowns |

Importable from `picard.plugin3.api`: `Album, BaseAction, Cluster, CoverArtImage, CoverArtProvider, File, ImageInfo, ImageProcessor, Metadata, OptionsPage, PluginApi, PluginLogger, ProviderOptions, Track, t_`.

## Cover art internals (verified in `picard/coverart/`)
- `CoverArtImage(url=None, types=None, comment='', data=None, support_types=None, support_multi_types=None, id3_type=None)`. Flags: `can_be_saved_to_tags`, `can_be_saved_to_disk`, `can_be_saved_to_metadata`, `can_be_processed`. `set_data(bytes)` fills the image. `types` is a list of strings such as `['front']`, `['back']`, `['medium']`, `['booklet']`.
- Attaching an image to an object: `picard.coverart.setters.CoverArtSetter(mode, image, source_obj, update_orig=False).set_coverart()` with `CoverArtSetterMode.APPEND` or `REPLACE`; `source_obj` can be an album, track or file.
- Files: `metadata.images` is written by Picard on save; `to_be_saved_to_tags` and `to_be_saved_to_files` honour the per-image flags.
- App dirs: `picard.const.appdirs.config_folder()`, `cache_folder()`, `plugin_folder()`.

## Design consequences (changes versus the original brief)
1. **Gather-all consensus cannot live inside a `CoverArtProvider`.** Picard runs providers in a queue and `enabled()` defaults to `not front_image_found`, so the first provider with a front image stops the rest. CoverUp's primary entry point is therefore an **album/cluster action ("CoverUp: Find artwork…")** that runs its own pipeline and then attaches images with `CoverArtSetter`. An optional **automatic mode** can later be added as a `CoverArtProvider` that runs the pipeline and returns `QueueState.WAIT`, then calls `queue_put` for the chosen image.
2. **Custom folder output** (`covers`, `art`, ...): Picard's native file saving writes into the album folder using its own naming script. For CoverUp-managed images set `can_be_saved_to_disk = False` and write the files ourselves in a **file post-save processor**, where `file.filename` is already the final renamed path. Embedding stays on Picard's normal tag-writing path (`can_be_saved_to_tags`).
3. **Logs** go under `picard.const.appdirs.cache_folder()` (or `config_folder()`), in a `coverup/logs/` subfolder, with `api.logger` receiving warnings and above.
4. **Settings** use `api.plugin_config` (profile-aware); machine-specific items such as API keys and the log folder use `api.plugin_persist` so secrets are not copied into profile exports.
5. **Pure-Python core.** All matching, scoring, hashing, naming, safety and logging code has no `picard` imports so it can be unit tested without Picard. Only `picard_glue/` and `__init__.py` touch Picard.

## Still unverified (needs a running Picard 3 or a fuller read of the source)
- Exact behaviour of `CoverArtSetter` when attaching to a cluster versus an album, and how `update_orig` interacts with the "unsaved changes" indicator.
- Whether `file.metadata` of every file in an album is available inside the post-save processor for per-disc routing (expected: yes, `file.metadata['discnumber']`).
- Whether Qt image decoding/scaling (`QImage`) is safe off the GUI thread in Picard's worker threads (expected: yes for `QImage`, no for `QPixmap`).
- Provider API terms and quotas (Discogs, Fanart.tv, TheAudioDB, Google Custom Search), and AI backend API shapes: to be checked per provider when each is implemented.
- Registry submission requirements (`picard-cli plugins` and the registry repo), to be checked in Phase 4.

## Implementation notes (v0.2.0)
- Verified by tests that import the real Picard 3.0 source (`PICARD_SRC`): plugin registration, `CoverArtImage` creation with `support_types=True` and `can_be_saved_to_disk=False`, `CoverArtSetter` on real `Album`/`File` objects, per-disc embedding, the post-save hook, and the Qt dialogs (off-screen).
- HTTP uses `urllib` in Picard's thread pool (`picard.util.thread.run_task`) rather than Picard's async web service: the multi-source pipeline is far simpler as blocking code in a worker, with its own per-host rate limits. Trade-off: Picard's proxy settings are not used (the standard proxy environment variables are).
- Settings live in `api.plugin_config` (profile-aware). `plugin_persist` is not used for keys because Picard documents it as discardable.
- Fixtures for each provider were written from its documented response format; live responses have not been recorded yet.

## Implementation notes (v0.6.0): free AI services
- **Cloudflare Workers AI** (`creative/ai.py`, `CloudflareWorkersAI`): `POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}` with `Authorization: Bearer <token>` and a JSON body, one image per request. Parameter names come from each model's input schema on developers.cloudflare.com/workers-ai/models/: FLUX.1 schnell takes `prompt`, `steps` (max 8, default 4) and `seed` (no size, no negative prompt); SDXL base 1.0 and SDXL Lightning take `num_steps` (max 20), `width`/`height` (256-2048) and `negative_prompt`; Lucid Origin takes `steps` (max 40) and `width`/`height` (up to 2500); Phoenix 1.0 takes `num_steps` (max 50), `width`/`height` and `negative_prompt`. Responses are either JSON (`{"result": {"image": "<base64>"}, "success": true}`) or the image bytes (`image/png` for SDXL); both are handled, and raw bytes are also recognised by their signature. Pricing (platform/pricing page): 10,000 free neurons a day; FLUX.1 schnell costs 4.8 neurons per 512×512 tile plus 9.6 per step, so about 58 neurons for 1024×1024 at 4 steps. Not checked against a live account: the output schema of Phoenix 1.0 and Lucid Origin (documented only as `image` in base64, or a stream), and whether FLUX.1 schnell honours `seed` (it appears only in the curl example).
- **AI Horde** (`AIHorde`): `POST https://aihorde.net/api/v2/generate/async` (headers `apikey`, `Client-Agent: CoverUp:<version>:https://github.com/herculepirate/picard-coverup`; body `prompt` with `###` before the negative prompt, `params` {`width`, `height` multiples of 64, `steps` 25, `n`, `sampler_name` `k_euler_a`, `cfg_scale` 7, `seed` as a string}, `models`, `nsfw: false`, `censor_nsfw: true`, `r2: true`) returns `{"id", "kudos"}`. `GET /v2/generate/check/{id}` is polled (fields `done`, `faulted`, `is_possible`, `wait_time`, `queue_position`) every 2-10 s depending on `wait_time` (status is cached for 1 s server-side). `GET /v2/generate/status/{id}` then gives `generations[].img`: a short-lived R2 download URL when `r2` is true (downloaded at once), otherwise base64 WebP; `censored` images are skipped. After the user's maximum wait, an error, or a user cancel, `DELETE /v2/generate/status/{id}` cancels the job; its answer can still contain finished images, which are used. The anonymous key is `0000000000`. Sources: the horde-sdk documentation (request/response models and endpoint constants) and the AI Horde integration README; the swagger page itself could not be fetched.
