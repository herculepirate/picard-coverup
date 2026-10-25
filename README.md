# CoverUp for MusicBrainz Picard

Find, compare and apply album artwork from many sources, as tags embedded in your music files, as image files in a folder you name, or both.

**Version 0.6.0 · Needs MusicBrainz Picard 3.0 or newer · Python 3.10+ · GPL-2.0-or-later**

---

## Contents

1. [Why CoverUp](#why-coverup)
2. [What you get](#what-you-get)
3. [What CoverUp cannot do](#what-coverup-cannot-do)
4. [Requirements](#requirements)
5. [Install and first-time setup](#install-and-first-time-setup)
6. [Quick start (five minutes)](#quick-start-five-minutes)
7. [Everyday use](#everyday-use)
8. [How the pick is made](#how-the-pick-is-made)
9. [Settings reference](#settings-reference) (every setting, tab by tab)
10. [Recipes: settings for common goals](#recipes-settings-for-common-goals)
11. [Script variables](#script-variables)
12. [Logging and diagnostics](#logging-and-diagnostics)
13. [Privacy and network behaviour](#privacy-and-network-behaviour)
14. [Troubleshooting and FAQ](#troubleshooting-and-faq)
15. [Updating](#updating)
16. [Development and contributing](#development-and-contributing)
17. [Licence](#licence)

---

## Why CoverUp

Picard's built-in cover art providers give you one image from one place. For a careful collection that is not enough: the right pressing may only be on Discogs, the best scan may be on Fanart.tv, the back cover may be nowhere, and the covers folder your media server reads may be empty.

CoverUp asks many sources at once, tells you how sure it is (exact release, same album, or just a search match), shows you the candidates side by side, and writes the result where you want it: in the tags, in files, or both. When it is certain it can do the work for a whole selection of albums; when it is not, it stops and asks.

## What you get

- **Many sources, one window.** Cover Art Archive, Discogs, Wikimedia Commons, Fanart.tv, TheAudioDB, Apple Music (iTunes), Deezer, Last.fm, optional paid web image search, and images already in your album folder (JPG, PNG and TIFF, including sub-folders).
- **Exact release first.** Art tied to the exact MusicBrainz or Discogs release you tagged wins; otherwise the picture most independent sources agree on.
- **Every art type.** Front, back, disc (matched to the right disc), booklet pages and artist images (photo, logo, background, banner). You choose which.
- **Tags, files or both.** Embed the front cover for your player, keep full-size scans as files for your media server. Naming presets for Kodi/Jellyfin and Plex.
- **Safe by design.** Replaced files are backed up, **Undo last apply** restores them, nothing is applied when sources disagree, and every file written is recorded in `coverup.json`.
- **Your own scans, edited in place.** Every JPG, PNG and TIFF in the album folder (and its sub-folders) is offered in the Front, Back and Disc tabs, whatever it is called. **Rotate left**, **Rotate right** and **Crop…** make an edited JPEG copy without touching the original.
- **Review window.** Large preview, comparison with your current cover, plain-language labels, double-click to apply one image, paste or drag in a picture you found yourself, and a **Search the web** menu that opens image searches in your browser, pre-filled with artist, album, year and edition.
- **Works from Picard's own cover art lookup.** CoverUp can be ticked in Options > Cover Art like the built-in providers.
- **Creative fallback (off by default).** When no real cover exists, make one: fan art, an AI image service (your own, or the free Cloudflare Workers AI or AI Horde), or an offline renderer. Always labelled as generated.
- **Troubleshooting built in.** A log file with API keys masked and a one-click redacted diagnostics bundle.

## What CoverUp cannot do

Being clear about limits saves you time. CoverUp does **not**:

| You might expect | What actually happens |
|---|---|
| Search Google, Bing, Amazon, Spotify, Tidal, Bandcamp, Qobuz or YouTube Music by itself | It cannot. Those services have no free, permitted image search for this purpose. The **Search the web** menu opens them in *your browser*, pre-filled; you copy a picture and paste it into CoverUp. CoverUp never scrapes a search-engine or shop page. |
| Include a free web image search API | None exists to recommend. Google's Programmable Search is closed to new customers, and Brave's Search API is paid (no free plan). The optional key under Sources > Web image search is for people who already have one. |
| Download from sources needing an account you have not set up | Discogs needs your token; Fanart.tv needs a free key for logos, backgrounds, banners and disc art. Without them those sources are skipped (never an error). |
| Embed disc art, booklets or artist images through Picard's own cover art lookup | In that mode only the **front and back** are handed to Picard (Picard puts an image on every track, which is wrong for disc art and booklets). CoverUp writes the rest as files. Use the review window or Auto-apply to embed a disc's art into that disc's files. |
| Embed artist images in tags | Artist images are files only (in the artist folder). |
| Save anything but JPEG | By design everything written or embedded is JPEG. PNG and TIFF sources are converted (transparency becomes white). Keep your TIFF masters elsewhere; CoverUp never modifies the originals. |
| Generate back, disc or booklet art | Generated art is for the **front cover only**. The other types are always real scans. |
| Label Discogs' extra images | Discogs does not say which secondary image is a back cover or booklet page. They are offered in the Back, Disc and Booklet tabs for you to choose, and are never selected automatically. |
| Keep up with a Lookup you do afterwards | A Picard Lookup or Scan replaces a file's tags, cover included, with the release's. CoverUp then drops the image files it had queued for that file and tells you. Best order: **Lookup or Scan first, then CoverUp.** |
| Know the exact pressing from loose, untagged files | With no MusicBrainz release ID, CoverUp can only search by artist and album and will not call that an exact match. It says so, and does not auto-apply a guess. |
| Give artist images to compilations | Albums by *Various Artists* never get artist images. |
| Use Picard's proxy and network settings | CoverUp makes its own requests with Python's standard library. A proxy is read from the `HTTPS_PROXY` environment variable. |
| Undo a change in your tags after you save | **Undo last apply** reverses files CoverUp wrote. Embedded images can be changed until you save; before that, remove and reload the album to drop them. After saving, re-apply the old cover. |
| Bundle or host an AI model | Nothing is included or hosted. You choose a service: local Stable Diffusion, an OpenAI-compatible API, a custom endpoint, or one of two free ones, Cloudflare Workers AI (free account, daily allowance) and AI Horde (volunteers' computers, no account needed). |
| Guarantee every source works today | Source responses were tested against fixtures written from each service's documentation and have not all been checked against the live services. AI backends have not been tested against real servers. If a source returns nothing, export diagnostics and report it. |
| Install through Snap or non-Flatpak packaging specifics | Only the standard Picard 3 plugin installation is described here. Flatpak paths are given; other packages keep plugins elsewhere. |

## Requirements

- MusicBrainz Picard **3.0 or newer** (plugin API 3.0). Picard 2 is not supported.
- Python 3.10 or newer (Picard 3 already brings it).
- Internet access to the sources you enable.
- Optional keys: Discogs token, Fanart.tv key (free), TheAudioDB key, Last.fm key, web image search key (paid).
- Nothing else to install: CoverUp uses Picard's own Qt for images (no Pillow) and Python's standard library for network access.

## Install and first-time setup

### 1. Install the plugin

From Picard: **Options > Plugins > Install plugin…** and give it the repository address `https://github.com/herculepirate/picard-coverup`.

From a terminal:

```
picard-cli plugins install https://github.com/herculepirate/picard-coverup
```

Flatpak Picard:

```
flatpak run --command=picard-cli org.musicbrainz.Picard plugins install https://github.com/herculepirate/picard-coverup
```

Restart Picard. Right-click an album: you should see the three **CoverUp** entries. Plugins live in `~/.var/app/org.musicbrainz.Picard/data/MusicBrainz/Picard/plugins3/` on Flatpak.

### 2. Add the keys you have (Options > Plugins > CoverUp > Sources)

| Source | Key | Where to get it | Without it |
|---|---|---|---|
| Cover Art Archive | none | | works |
| Wikimedia Commons | none | | works (artist photos and logos) |
| Apple Music (iTunes) | none | | works |
| Deezer | none | | works |
| TheAudioDB | `123` public test key is pre-filled | theaudiodb.com (personal key is faster) | works, rate-limited |
| **Discogs** | personal access token | discogs.com > Settings > Developers > Generate new token | Discogs skipped; this is the best source for exact pressings, so it is worth the minute |
| **Fanart.tv** | free project API key | fanart.tv/get-an-api-key | no disc art, logos, backgrounds, banners |
| Last.fm | optional key | last.fm/api | skipped (images are usually small anyway) |
| Web image search | optional, **paid** | Brave Search API | skipped; use the free browser search in the review window instead |

### 3. Check Picard's own cover art options

CoverUp embeds through Picard, so Picard's **Options > Cover Art > Embed cover images into tags** must be on. If *Embed only a single front image* is on, only the front is embedded no matter what CoverUp is set to.

### 4. (Optional) Let Picard ask CoverUp automatically

In Picard's **Options > Cover Art**, tick **CoverUp (best match from all sources)** and drag it **above** the other providers. Picard stops asking providers once it has the front cover it needs, so a provider listed lower may never be asked. New providers are off until you tick them.

## Quick start (five minutes)

1. Load an album into Picard, then **Lookup** (or **Scan**) so it is matched to a MusicBrainz release.
2. Right-click the album > **CoverUp: Find artwork…**
3. In the window, look at the **Front** tab. The picture marked **CoverUp pick** is what would be chosen; select any other to compare it with your current cover.
4. Check **Your set** at the bottom (everything that will be applied), then **Apply**.
5. **Save** the album in Picard. Embedded images are written with the tags and `covers/` plus `cover.jpg` are written beside your tracks.
6. Not happy? Right-click > **CoverUp: Undo last apply**.

For a big library: select many albums > **CoverUp: Auto-apply**. Confident results are applied; conflicts and misses are listed for review.

## Everyday use

### The three menu items

Right-click an album, a cluster, a track or a file. Loose files under **Unclustered Files** work too: CoverUp groups them by their own album and album-artist tags.

| Menu item | What happens |
|---|---|
| **CoverUp: Find artwork…** | Searches every enabled source, then opens the review window. |
| **CoverUp: Auto-apply** | For all selected albums: applies confident results, marks conflicts and misses for review (double-click a row to review it). |
| **CoverUp: Undo last apply** | Removes the files the last apply wrote and restores any files it replaced (from `.coverup-backup`). |

### The review window

- One tab per art type: Front, Back, each disc, Booklet, Artist, and Create.
- Each picture carries a label: **Exact release**, **Same album** (possibly another edition), **Search match**, or **Generated**. Select one to see why in the preview panel.
- **CoverUp pick** marks the automatic choice. Resolution, source and licence (for Wikimedia images) are shown.
- **Rotate left / Rotate right / Crop…** work on the selected picture (from any source, including your own files). They make an edited copy that appears next to the original in the same tab and is selected; the original is never changed. Crop: drag a box over the picture, drag inside it to move it, and tick or untick *Keep it square* (on by default, because covers are square). Edited pictures are JPEG.
- **Double-click a picture** to apply just that one straight away; the window stays open for the rest.
- **Your set** is the strip of everything you are about to apply. Remove items you do not want.
- **Destination controls** at the bottom of the window set what to embed, which folder to save to and when to write, for this apply. They start from your saved settings.
- **Search the web** opens an image search in your browser (Google Images limited to large images, Bing, DuckDuckGo, Discogs, the release's MusicBrainz cover art page, or the **Shops and streaming** submenu: Amazon, Spotify, Tidal, Apple Music, YouTube Music, Bandcamp, Qobuz). Queries are plain words in the order that image search likes best: the full album title, the artist and the year, for example `Leonard (Book of Angels, Volume 30) Garth Knox The Saltarello Trio 2017` (no quote marks; multiple artists are joined with spaces); for "this pressing" also the label, catalogue number and format. Open a picture full size, right-click > Copy image, then press **Ctrl+V** in CoverUp, or drag it onto the window. It lands in the tab you are on. Pasted Google/Bing result links are turned into the real image address.

### Best order of operations

1. Lookup or Scan (so tags and release IDs are right).
2. CoverUp.
3. Save.

Applying to files that are not matched yet works, but CoverUp tells you, and a later Lookup will replace the tags (cover included) with the release's.

## How the pick is made

1. **Exact release** art (tier A: Cover Art Archive release images, or the matching Discogs release) wins.
2. Otherwise **release-group** art (tier B: CAA release group, Fanart.tv, TheAudioDB).
3. Otherwise the image that the **most independent sources agree on** visually (perceptual hashing, tier C). Two files count as the same picture when they differ by no more than *Same-picture tolerance* bits of 64.
4. If exact-release art and a large group of other sources disagree, nothing is applied automatically; the album is flagged for review.
5. Images smaller than the minimums, larger than the maximum, or not near-square (for front and disc art) are set aside.
6. Optionally, if nothing qualifies, the creative fallback can make a cover.

## Settings reference

Open **Options > Plugins > CoverUp**. There are six tabs. Everything has a safe default; the defaults are chosen for collectors. "Restore Defaults" in Picard's Options window puts them back. Settings you never changed move to new defaults when the plugin updates; settings you changed are kept.

### General

What to collect and where it goes. Most people only ever change this tab.

| Setting | Default | What it does and when to change it |
|---|---|---|
| **Art types** | Front, Back, Disc, Booklet, Artist | The types pre-selected in the review window and used by Auto-apply. Untick types you never want. Unticked types are still shown in the window for a manual pick. |
| **Embed in tags** | Front cover only | Which chosen types go inside the music files. Choices: *Front cover only*, *Front and back*, *Everything chosen*, *Nothing (files only)*. Big scans make every track file bigger, so collectors usually embed the front and keep the rest as files. Disc art is embedded only into that disc's files. |
| **Save files to** | `covers/` folder inside the album | Where image files go. Choices: `covers`, `art`, `artwork`, `booklet` (sub-folder inside the album), *the album folder itself*, *another folder inside the album…* (your own name; no slashes or illegal characters), or *Don't save files*. |
| **Also save the front cover beside the tracks** | On | Also writes the front cover as `cover.jpg` in the album folder. Players and media servers (Navidrome, Plex, Jellyfin) look for `cover.jpg` or `folder.jpg` there. |
| **Write files** | When the album is saved in Picard | *When saved* writes after Picard saves, so files follow renames and moves (recommended). *Straight away* writes immediately, which can leave files in the old location if you rename afterwards. |
| **File names** | Default | *Default*: `cover`, `back`, `disc1`, `booklet-01`. *Kodi and Jellyfin*: `folder`, `back`, `cdart1`, `logo`, `fanart`, `banner`. *Plex*: `cover`, `back`, `disc1`, artist background named `background`. *My own*: use the names set under Advanced. |
| **Existing files** | Replace only if the new image is larger | If a file of that name exists: *Replace only if larger*, *Always replace*, *Keep the existing file*, or *Keep both* (the new one is saved beside the old under a different name). |
| **Keep a backup of replaced files** | On | Copies a file into `.coverup-backup` before replacing it, so **Undo last apply** can restore it. Turn off only if disk space matters more than safety. |

### Artists

Everything about artist images (photo, logo, background, banner).

| Setting | Default | What it does and when to change it |
|---|---|---|
| **Look for artist images when I search for an album** | On | Master switch. Off removes artist images from the search, the window, and Auto-apply, and CoverUp makes no artist requests at all. Compilations never get artist images. |
| **Pre-select** | Photo | Which kinds are ticked in the window and applied by Auto-apply: *Photo*, *Logo*, *Background*, *Banner*. Every kind found is still listed so you can pick others by hand. Logos, backgrounds and banners need Fanart.tv or TheAudioDB (Wikimedia can supply logos). |
| **Smallest photo** | 500 px | Smaller photos are hidden in the window and never applied automatically. `0` accepts any size. |
| **Save artist images in the artist folder** | On | Writes into the folder above the album, e.g. `Music/Artist/artist.jpg`; `Album/CD1` layouts are recognised. Several albums share it, so the larger image wins unless *Existing files* says otherwise. Artist images are never embedded. |
| **File names: Photo / Logo / Background / Banner** | `artist` / `logo` / `fanart` / `banner` | Used when *File names* (General) is *My own*; the presets set their own. |

Sources by kind, best first:

| Kind | Sources |
|---|---|
| Photo | Wikimedia Commons (exact: linked from the artist's MusicBrainz page; shows its licence), Discogs (artist page; needs token), Fanart.tv, TheAudioDB, Deezer (name match only, so shown as a *Search match*) |
| Logo, background, banner | Fanart.tv (free key), TheAudioDB; Wikimedia Commons logos when the artist has one |

### Sources

Where to look, and the keys.

| Setting | Default | What it does and when to change it |
|---|---|---|
| **Where to look (list)** | Cover Art Archive, Discogs, Wikimedia, Fanart.tv, TheAudioDB, Apple Music, Deezer, Local files | Tick sources to search; drag to set the order. Order breaks ties and decides which is asked first. Untick anything you do not trust or need. Last.fm and Web image search are off until you tick them. |
| **Discogs token** | empty | Personal access token. Unlocks Discogs release lookup (by MusicBrainz link, barcode, catalogue number or search) and artist page photos. |
| **Fanart.tv key** | empty | Free project key. Adds disc art, artist photos, logos, backgrounds, banners. |
| **Fanart.tv personal key** | empty | Optional. Makes new uploads appear sooner. |
| **TheAudioDB key** | `123` | The free public key. A personal key is faster. |
| **Last.fm key** | empty | Optional. Last.fm images are usually small. |
| **Web image search: Service** | Brave Search API | Which paid service the key below belongs to: Brave or Google Programmable Search. |
| **Web image search: API key** | empty | Paid (Brave has no free plan since May 2026; Google no longer takes new customers). **Not needed**: the review window's Search the web button is free and opens your browser. |
| **Google engine ID** | empty | Only for Google Programmable Search. |

Keys are stored in Picard's configuration, are masked in the log, and are never put in an export.

### Image quality

Which image to prefer, the smallest to consider, and what to do on the way out.

| Setting | Default | What it does and when to change it |
|---|---|---|
| **Prefer** | The largest available | *Largest* is best for archiving. *Closest to a preferred size* suits devices with little storage; set the size below. |
| **Preferred size** | 1200 px | Used only when *Closest to a preferred size* is chosen. |
| **Smallest images to consider: Front / Back / Disc / Booklet** | 500 px each | Smaller results are hidden in the window (you can show them) and never applied automatically. `0` = any size. |
| **Never apply below** | 600 px | A cover below this is not applied automatically. It can trigger the Create fallback. `0` = any size. |
| **Embedded images up to** | 1200 px | Longest side for images going into tags; larger ones are scaled down for the tags only. `0` = full size. Keeps your music files from growing. |
| **Saved files up to** | Original size (0) | Longest side for files; `0` keeps the scan as it is. |
| **JPEG quality** | 95 | **Everything CoverUp saves or embeds is a JPEG**: PNG, TIFF and WebP sources are converted, and JPEG sources are left exactly as they are unless resized. This is the quality used when converting or resizing. |
| **Enlarge images smaller than the minimum** | Off | Upscales small images up to the minimum. They will look soft; leave off unless a device needs a minimum size. |

Images are never upscaled unless you turn that on.

### Create

Make a cover when there is none. **Off by default**; real covers always come first.

| Setting | Default | What it does and when to change it |
|---|---|---|
| **Create when** | none ticked | Triggers: *No cover is found*, *The best cover is below the apply minimum*, *Sources disagree about the cover*. |
| **Always use a created front cover** | Off | Replaces the real front cover with a generated one every time. For people who deliberately want uniform artwork. |
| **Try** | Fan art, then AI, then the built-in renderer | The order of methods: Fanart.tv fan art, your AI service, the offline renderer. Pick subsets (e.g. *Built-in renderer only* to stay fully offline). |
| **Style** | Art (painterly / abstract) | Eleven built-in styles (Art, Fantasy, Nature, Planetary, Cyberpunk/Neon, Minimal typographic, Vintage, Photographic, Geometric/Bauhaus, Dark/Gothic, Retro pop) or *Custom prompt*. Styles are editable `.toml` files; add your own in your styles folder. |
| **Custom prompt** | "Album cover artwork for "{album}" by {artist}, {genre}, {era}. No text, no letters." | Used for the Custom style. `{artist}`, `{album}`, `{year}`, `{genre}`, `{era}` are filled in. |
| **Match the era / genre** | On / On | Steers the look from the release year and genre tag. |
| **Show the band logo (or the artist name)** | On | CoverUp draws it itself, so it is sharp and spelled right. The logo is from Fanart.tv/TheAudioDB (you pick a variant once per artist and it is remembered); otherwise the name is set as text. |
| **Show the album title** | On | Drawn by CoverUp, not the AI. |
| **Logo position** | Top | Top, Centre or Bottom. |
| **Versions per click** | 4 | How many alternatives are generated in the review window. |
| **Most covers per Auto-apply run** | 20 | A safety cap on generated covers per run. `0` = none generated. |
| **AI image service: Service** | None | *None*, *Stable Diffusion on this computer (AUTOMATIC1111, started with `--api`)*, *OpenAI-compatible images API*, *Other (custom HTTP endpoint)*, *Cloudflare Workers AI (free daily allowance)* or *AI Horde (free, run by volunteers)*. Only the chosen service's settings are shown. Anything outside your computer receives the artist, album, year and genre, and asks for consent first. |
| **Address** | `http://127.0.0.1:7860` | The service address. |
| **Model** | empty | Optional model name. |
| **API key** | empty | For remote services. Masked in logs. |
| **Image size** | 1024 px | Size requested from the service. |
| **Steps** | 30 | Stable Diffusion only. |
| **Cloudflare: Account ID / API token** | empty | See *Free AI services* below. The token is masked in logs and left out of diagnostics. |
| **Cloudflare: Model** | `@cf/black-forest-labs/flux-1-schnell` | Pick FLUX.1 schnell, SDXL base 1.0, SDXL Lightning, Leonardo Lucid Origin or Leonardo Phoenix 1.0, or type any other Workers AI text-to-image model ID. |
| **Cloudflare: Steps** | 4 | FLUX.1 schnell takes up to 8, the SDXL models up to 20; larger values are lowered to the model's limit. |
| **AI Horde: API key** | `0000000000` | The anonymous key works without an account. A free registered key gets priority in the queue. Masked in logs. |
| **AI Horde: Model** | AlbedoBase XL (SDXL) | Any image model the Horde lists. |
| **AI Horde: Give up after** | 300 s | The request is cancelled if no volunteer has finished it by then. |
| **Base new covers on the current low-resolution cover** | Off | Sends your current cover as a reference (img2img). Local services only unless the next option is on. |
| **Allow sending that cover to services outside this computer** | Off | Needed before the cover goes to a remote service. |

Buttons: **Open my styles folder** and **Ask again before using AI services** (forgets consents).

#### Free AI services

Both are outside your computer, so the first cover asks for your consent (once per service). Neither can base a cover on your current one.

- **Cloudflare Workers AI.** Needs a free Cloudflare account. In the Cloudflare dashboard open **Workers AI** > **Use REST API**: copy the **Account ID**, then **Create a Workers AI API Token** and copy it. Paste both into CoverUp. The free allowance is 10,000 neurons a day. FLUX.1 schnell at 1024×1024 with 4 steps costs about 58 neurons, so about 170 covers a day are free; each version is one request. The Leonardo models cost more than 2,000 neurons a cover. FLUX.1 schnell chooses its own image size; the other models use **Image size**.
- **AI Horde** ([aihorde.net](https://aihorde.net)). A crowdsourced network of volunteers' computers; free, no account needed. Requests join a queue, so a cover can take from seconds to several minutes, and CoverUp cancels the request after **Give up after**. Image size is rounded to a multiple of 64 (512 to 1024 px with the anonymous key). Covers are requested as safe-for-work. Register at aihorde.net/register for a key with priority. Your prompt is seen by the volunteer whose computer makes the image.

Generated art is always labelled (embedded image comment "Generated by CoverUp…", `coverup.json`, `%_coverup_generated%`), never uploaded anywhere by CoverUp, and never outranks real art except where you switched it on.

### Advanced

Fine-tuning. Leave alone unless something specific is wrong.

**Matching**

| Setting | Default | What it does and when to change it |
|---|---|---|
| **Auto-apply** | Only when the result is certain | *Never: always review* turns Auto-apply into a "find and queue" tool that applies nothing by itself. |
| **Same-picture tolerance** | 10 of 64 | How different two files may be and still count as the same artwork (perceptual hash distance). Lower is stricter. Raise if the same cover from different sources is treated as different; lower if different covers are merged. |
| **Flag a conflict at** | 3 sources | If this many sources agree on a different picture than the exact release, the album is flagged for review instead of auto-applied. |
| **Square tolerance** | 0.05 | Front and disc art must be near-square: 0.05 accepts up to 5% off. Cassette, DVD and VHS covers are exempt. |
| **Ignore images larger than** | No limit | Longest side cap on candidates. |
| **Largest download** | 25 MB | Bigger files are skipped. |

**Files and tags**

| Setting | Default | What it does and when to change it |
|---|---|---|
| **Albums split into CD1, CD2 folders** | Album art in every folder | *Every folder* writes album art to each disc folder; *first folder only* writes it once. |
| **Remove older embedded images of the same type** | On | Stops tags collecting duplicate front covers. |
| **Note the source in the embedded image's comment** | Off | Provenance normally lives in `coverup.json`, keeping tags clean. Turn on if you want it inside the files too. |
| **Write coverup.json** | On | A small file beside the images recording where each came from and when. Also used by Undo. |

**My own file names** (used when *File names* on General is *My own*)

| Setting | Default | Notes |
|---|---|---|
| Front | `cover` | Extension is added. |
| Back | `back` | |
| Disc | `disc{discnumber}` | `{discnumber}` becomes 1, 2, … |
| Booklet page | `booklet-{n}` | `{n}` becomes 01, 02, … |

**Network**

| Setting | Default | What it does and when to change it |
|---|---|---|
| **Remember search results for** | 24 hours | A disk cache so repeated searches are instant and friendly to the services. `0` = don't remember. |
| **Results per source** | 12 | More means more to browse and more downloads. |

**Log file** (details under [Logging and diagnostics](#logging-and-diagnostics))

| Setting | Default | |
|---|---|---|
| **Keep** | Rotating files of a fixed size | Also: files up to a total size, files for a number of days, one file per Picard session, or no log file. |
| **File size** | 2 MB | Per file (fixed, total and age modes). |
| **Older files kept** | 3 | Fixed mode. |
| **Total size** | 25 MB | Total mode. |
| **Days kept** | 14 | Age mode. |
| **Sessions kept** | 5 | Session mode. |
| **Detail** | Normal | Errors only, Warnings, Normal, Detailed, Everything. Use *Detailed* when reproducing a problem. |
| **Hide folder paths and album names** | Off | Anonymises the log for sharing. |
| **Folder** | empty (default) | A custom log folder. |

Buttons: **Open log folder**, **Export diagnostics…**, **Clear search cache**.

## Recipes: settings for common goals

| Goal | Settings |
|---|---|
| **Collector's archive** (the defaults) | Embed front only at 1200 px; save every image full-size in `covers/`; prefer largest; replace only if larger; backups on. |
| **Media server (Plex, Jellyfin, Kodi, Navidrome)** | General: pick your *File names* preset; keep *Also save the front cover beside the tracks*; Artists: save artist images on, tick Logo/Background/Banner as your server uses them. |
| **Small portable player** | Embed front only; *Embedded images up to* 500 px; *Prefer closest to a preferred size* 600; File format JPEG. |
| **Tags only, no files** | Save files to > *Don't save files*; Embed > *Front and back*. |
| **Files only, tags untouched** | Embed > *Nothing (files only)*. |
| **Never surprise me** | Advanced > Auto-apply > *Never: always review*. |
| **Fully offline-friendly look** | Create: *Try* > *Built-in renderer only*; AI service > *None*. |
| **Uniform, generated covers** | Create: tick *Always use a created front cover*, pick a Style. |
| **Minimal network use** | Sources: untick all except Cover Art Archive and Local; raise *Remember search results* to 720 hours. |

## Script variables

Available in Picard scripts and file naming:

| Variable | Values |
|---|---|
| `%_coverup_status%` | `applied`, `review`, `none` |
| `%_coverup_source%` | The provider the front cover came from |
| `%_coverup_confidence%` | `A` exact release, `B` same album, `C` search match, `G` generated |
| `%_coverup_generated%` | Set when the cover was generated |

Example: tag albums needing attention with `$if($eq(%_coverup_status%,review),needs-cover-check)`.

## Logging and diagnostics

CoverUp writes a log for troubleshooting. By default it keeps rotating 2 MB × 3 files. API keys are always masked. On Flatpak: `~/.var/app/org.musicbrainz.Picard/cache/MusicBrainz/Picard/coverup/logs/coverup.log`. The first line of each session reads `CoverUp 0.6.0 starting`, which confirms which version Picard loaded.

To report a problem: set **Detail** to *Detailed*, reproduce it, then Advanced > **Export diagnostics…** and attach the redacted zip. Turn on *Hide folder paths and album names* first if you want the log anonymised.

## Privacy and network behaviour

- CoverUp contacts only the sources you leave ticked, plus your AI service if you configure one. It sends the artist, album, year, barcode and catalogue number a source needs to search, and the MusicBrainz IDs for exact lookups.
- Requests are rate-limited per host, and results are cached on disk for the time you set.
- Keys are stored in Picard's configuration, never logged unmasked and never included in diagnostics exports.
- The **Search the web** menu only opens links in your browser; CoverUp does not read what the search engines return.
- Generated art stays on your computer. AI services outside your computer require consent per host, and your existing cover is only sent to one if you allow that separately. With AI Horde, the prompt (artist, album, year, genre) is processed by a volunteer's computer.
- CoverUp has no telemetry and sends nothing to its author.

## Troubleshooting and FAQ

**I don't see the CoverUp menu items.**
Check Options > Plugins that CoverUp is installed and enabled, and restart Picard. Flatpak users: install with `flatpak run --command=picard-cli org.musicbrainz.Picard plugins install …`.

**The log still says an old version.**
Update (see below) and fully restart Picard. The first log line of the new session should read `CoverUp 0.6.0 starting`.

**Nothing found for an album.**
Look at the log for per-source lines. Common causes: no Discogs/Fanart.tv key, the album is not matched to a MusicBrainz release (Lookup first), the minimum sizes are too high for obscure releases, or the source is simply down. Lower *Smallest images to consider* and try again.

**CoverUp's cover is replaced after I click Lookup.**
That is Picard: a Lookup copies the release's tags (cover included) onto the file. Do Lookup or Scan first, then CoverUp. CoverUp notices and drops queued files for that file.

**Picard's cover art lookup uses another provider's cover, not CoverUp's.**
Picard stops asking providers once it has the front image it needs. In Options > Cover Art, drag CoverUp above the others.

**The covers folder was created but nothing is embedded (or the reverse).**
Check General > *Embed in tags* and *Save files to*, and Picard's own *Embed cover images into tags*. Files are written when the album is saved, not before.

**A different edition's cover was chosen.**
The label says **Same album** or **Search match** rather than **Exact release**. Pick the right one in the review window, or add a Discogs token, which finds the exact pressing by barcode or catalogue number.

**I want to see why something was or was not chosen.**
Select the picture in the review window; the preview panel explains it. For detail, set log Detail to *Detailed*.

**Artist images are missing.**
Check Artists > *Look for artist images* is on, the album is not a compilation, and the artist has a MusicBrainz ID. Photos come from Wikimedia Commons without a key; logos and banners need Fanart.tv or TheAudioDB.

**My Plex/Jellyfin/Kodi doesn't show the artist image.**
Check the File names preset matches your server and *Save artist images in the artist folder* is on. The folder above the album must be the artist folder.

**Undo didn't bring back an old cover I had embedded.**
Undo reverses the files CoverUp wrote. Embedded tags are changed in Picard and only become permanent when you save; before saving, remove and reload the album.

**Is it safe to run on my whole library?**
Use **Auto-apply** on a few albums first. With backups on and *Replace only if larger*, existing files are kept unless the new image is bigger, and Undo restores replaced files. Set Auto-apply to *Never* if you only want it to prepare a review list.

**Does the Discogs Enrichment plugin conflict?**
No. They are separate providers. Keep both updated: older Discogs Enrichment versions crashed Picard 3's cover art queue and were fixed in the repository's latest version.

**Where are CoverUp's settings stored?**
In Picard's own configuration, under the plugin's name.

## Updating

If you installed from this repository's address:

```
picard-cli plugins update CoverUp
```

(Flatpak: `flatpak run --command=picard-cli org.musicbrainz.Picard plugins update CoverUp`.) Then restart Picard. Settings you changed are kept; settings left on their defaults move to the new defaults.

## Development and contributing

```
python -m venv .venv && .venv/bin/pip install pytest ruff PyQt6
.venv/bin/python -m pytest -q                                            # core and Qt tests
PICARD_SRC=/path/to/picard-3.x-source .venv/bin/python -m pytest -q      # also the Picard integration and UI tests
.venv/bin/ruff check .
```

- `settings.py` is the single source of truth for every default and for secret keys.
- `providers/` holds one module per source; add a provider by registering it in `providers/__init__.py`.
- `ui/options_page.py` describes the settings page declaratively (`LAYOUT`).
- `docs/design-prompt.md` is the full design; `docs/phase0-api-contract.md` lists the Picard 3 APIs used, verified against the Picard 3.0 source.

Bug reports are welcome on the GitHub issue tracker: include the version line from the log, what you did, and a diagnostics export. New sources, naming presets and creative styles (`.toml`) are good first contributions; please add tests with fixtures taken from the service's documentation.

## Licence

GPL-2.0-or-later, the same as Picard.
