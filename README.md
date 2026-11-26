# NHI-timeline

An interactive timeline of the stories told about non-human intelligence and disclosure: which story is told about which era and place, by whom and in which podcasts and documents, and how well each is corroborated across the corpus. Stories, not facts: the data records who said what, and the corroboration does the ranking. `CLAUDE.md` is the working contract, `schema.md` the data shapes, `scoring.md` the score.

## Run

Python 3.12 and `uv`; `yt-dlp` and `claude` on the path for the first two steps. No dependencies
beyond the standard library; `../creator-watch` checked out beside this repo, with its `.venv` and
keys file, for the Gemini fallback only. The link pass works in groups of about ten candidates per
`claude -p` call (`--batch N`, default 10), saving the candidate file after each group, so a killed
run picks up at the first candidate without a `link`.

Where `uv run` cannot start, each line is `.venv/bin/python -m pipeline.<stage>`.

```sh
uv run python -m pipeline.check --fixture               # the whole chain on the fictional fixtures, offline
uv run python -m pipeline.captions <video id or URL>    # captions in: sources/captions/<id>.en.txt, data/episodes/<id>.json
../creator-watch/.venv/bin/python -m pipeline.gemini_captions <video id>   # fallback on a 429 or no caption track: a Gemini transcript as the caption text
uv run python -m pipeline.extract <video id>            # claude -p over the captions: data/candidates/<id>.json
uv run python -m pipeline.link <video id>               # claude -p, about ten candidates a call (--batch): is each the same story as one held, a variant, or new
uv run python -m pipeline.merge                         # candidates into data/stories, data/people, data/documents
uv run python -m pipeline.clips --report                # claude -p, about six groups a call: clips a host cut into another episode, who speaks them, from where (data/clips.json); prints what it would change
uv run python -m pipeline.clips                         # the same, then a telling inside a replayed clip gets replay_of and the clip's speaker as teller
uv run python -m pipeline.sources <manifest.json>       # public sources the stories name: their words as document tellings, sources/documents/<id>.txt, source notes (--hosts: the sites it reaches)
uv run python -m pipeline.documents --fold              # data/document-folds.json applied: each title of a document becomes one id, the document files and texts merged
uv run python -m pipeline.people --fold                 # data/person-folds.json applied: each spelling of a person becomes one id, the person files merged
uv run python -m pipeline.score                         # score into each story, data/scores.json
uv run python -m pipeline.explain --all --model opus    # claude -p, about twelve stories a call: a plain telling for every story, written ground up
uv run python -m pipeline.images <manifest.json>        # found photographs in: site/images/<owner>/<n>.jpg, data/images/<owner>/<n>.json (--hosts: the sites it reaches)
uv run python -m pipeline.build                         # site/data.json and site/data.js, the plain tellings in site/plain.json and site/plain.js
uv run python -m pipeline.check                         # every story has a telling, every id resolves, every quote is verbatim
open site/index.html                                    # the 3D page from disk (reads site/data.js)
python3 -m http.server -d site 8000                     # or over http (reads site/data.json): http://127.0.0.1:8000/
```

A long explain run splits into n background runs side by side, `explain --all --shard 1/4` to
`--shard 4/4`: each takes every fourth story of the ordered list from its own start, so together they
cover the list once over disjoint sets.

The page in `site/` is the timeline in 3D, plain HTML, CSS and JS with three.js from jsDelivr, run locally from
`site/` as it stands and published from the kit's build of it (below). Locally the page has no `<title>` (the build
writes it from `app.json`) and its six `kit/` scripts, which it loads first in the kit's `page.json` order, are not there (a 404 each, which the page passes over: only the
published page uses them), and it shows the pictures under `site/images/`: `index.html`, `style.css`, `app.js` (the controller) and `js/` (`model.js` the data
check, the score recomputed at the reader's institutional trust and the tiers; `cards.js` the picture
cards, `corridor.js` and `globe.js` the two views (a story with pictures shows them as cards, in place of
its sphere in the corridor and above its marker on the globe); `panel.js` the story panel; `notes.js` the notes box; `desktop.js` the page as a desktop app). The corridor is the
default view: time runs ahead, stretched where many stories are told, the angle is the kind or the
region, and the rings are the tiers. The globe is the second view: regions as patches sized by story
count, eras as shells. `M` switches; the keys are listed on the page. On a phone or tablet (a coarse
pointer) the page shows a touch pad and touch guidance instead of the keys: one finger looks around,
two fingers move along time in the corridor and pinch the globe. A link may carry
`#story=<id or alias>`, `mode=globe`, `rail=time|kind|strength|links`, `trust=<0.5 to 1.25>` and
`touch` (the touch layer on a computer);
`?data=<path>` loads another data file from a relative path beside the page (a `.js` defining
`window.NHI_DATA`, or JSON over http), for a test copy. The plain tellings come in a second file the
page loads after its first draw, from the data file's folder: `plain.json` over http, `plain.js`
(`window.NHI_PLAIN`) from disk or beside a `.js` data file; until it arrives the panel shows the
story without its plain telling. At load the page recomputes every attestation
and score from the profiles and refuses to draw when they differ from the stored values. Published as an artifact with the `db` capability,
the notes box saves to the collection `notes`; anywhere else it copies the note as text. The published page
also carries the `desktop` capability: "Install as app" (in the Claude desktop app's artifact menu, or the kit's offer in
the page's footer where the install is available) makes it an app with its own window, Dock icon and application menu. The menu,
its keys and the window come from the desktop-app kit's `KitApp` (`kit/app.js`, which the app build puts beside the
page), in the order every app of the set has: File, Edit, View (Corridor on Cmd-1, Globe on Cmd-2, the view's moves, the
legend and keys, the trust reset, then Reload on Shift-Cmd-R, zoom and full screen), Story (Back and Forward over the
stories visited, find, Copy Link to This Story, the rails), Window, Help (About, the page in the browser, the source on
GitHub). Every menu key holds Command or Control, and the page's plain keys stay its own. As in every app of the set, `f` is
feedback mode wherever the page is published (in the installed app Help > Feedback Mode too): a click marks a control, a drag loops an area, and copy
prompt takes the tickets out, since a page without an engine keeps them in memory; so `G` flattens the globe. `C`
angles the corridor here, where the set's other apps give it to loop: this page has no loop. The notes box (saved to
the artifact's database) stays how the page's viewers leave notes on a story or on the page. `app.json` lists no
permission, and `check` keeps it so.

Run the first command once after any change to the pipeline; it must print `check: ok (fixture)`.
It and the review stage read what a published artifact allows a file from the desktop-app kit's `limits.json`, in the
folder the environment variable `FLUXTECH_KIT` names (there is no default; unset, they stop naming it).
Every stage takes `--root DIR` to work on another data root (the fixture check uses a temporary
copy of `tests/fixtures/`). A story the pipeline got wrong is corrected by hand in its JSON and
`check` is run again; `merge` never changes an existing story or person: it appends tellings and fills a
null `place` or missing `place_text`, nothing else. A place the extractor names in words that
`data/place-aliases.json` does not know stays unresolved until an alias or a place is added; the next
`merge` then fills it.

The images stage downloads with a descriptive User-Agent and resizes in memory with macOS ImageIO.
`.venv/bin/python -m pipeline.images <manifest> --hosts` prints the hosts the run will reach, and
`.venv/bin/python -m pipeline.images <manifest> --keep-going` runs where exactly those hosts are allowed. A refused host
stops the run with its name (`CLAUDE.md`, Working here, says what to do); the run is
idempotent, so the images already added are kept. Its manifest is a
JSON list of `{ "owner", "kind", "image_url", "source", "licence", "licence_kind", "credit",
"caption", "date"? }` (`schema.md`, Images); an image already held is kept, so a manifest can be run
again.

To publish the page: it is a private artifact (its URL is `app.json`'s `artifact`,
capabilities `assets`, `db` and `desktop`; a named set replaces the stored one, so `app.json`'s `capabilities`
names `assets` and `db`, and the kit's build adds `desktop`). After `build` and a commit (the build's record names the commit it was built from), the
desktop-app kit's build makes the publish set from `site/app.json`: `app build site` (the `app` program in the
kit's folder, `desktop-apps/kit/` of universal-tools) writes `site/dist/`
(git-ignored by its own `.gitignore`): the page with its `<title>` and desktop manifest tag written from
`app.json` (their one home), the files `app.json` lists (`app.js`, `style.css`, `data.json`, `plain.json`,
the eight scripts under `js/`, and `assets.json` from `publish/assets.json`), the kit's page scripts and the
feedback module under `kit/` with `kit/build.js`, the build's record (the app's name and URL, the commits; no
folder), and `dist/publish.json`, whose `page`, `files` and `capabilities` the Artifact tool publishes to its
`url`. The build refuses a published file that names a home folder. Never `data.js` or
`plain.js` (the `file:` copies) and never a picture. An artifact version holds at most `files_per_version` files (the kit's `limits.json`), so every
picture lives in the artifact's asset store (5,000 files, 1 GB): a new picture is uploaded there
(`asset: true`, `file_paths`, as many a call as `limits.json` allows), its url (`/_blob/<id>`, same origin as the page) is
written into `publish/assets.json` under the page path `images/<owner>/<n>.ext`, and the map is
republished; `check` validates the map against `site/images/` and warns on an unmapped picture.
Uploads and the map are a mechanical agent's chore (Haiku), with the exact file lists in its
brief and the map written from the results; a builder spent 170k tokens on one such run. A
publish with `files` from a new conversation is refused until the artifact has been seen there:
first `action: list, scope: files`, then `action: read` of the page, then the publish. While any
`fair-use` image is in `site/images/` the artifact stays private.

To check a source: when a story names a public source (a paper, a book, a memo, a patent, a court
record, an article), a scout finds it and returns a manifest entry (`schema.md`, Document): the
document, a plain-text URL for a public-domain text or the quoted passages with their locators for
any other, the quotes that say what the story claims, the author, the telling's kind, a note
when the source reads otherwise than the tellers, and its pictures. Run
`.venv/bin/python -m pipeline.sources <manifest> --keep-going` after `clips` and before `documents --fold`,
where the hosts `.venv/bin/python -m pipeline.sources <manifest> --hosts` prints are allowed; it checks every quote against the text before writing an entry, keeps a text file already
there, and adds nothing twice, so a manifest can be run again. It writes the pictures to
`<manifest stem>.images.json` beside the manifest for `pipeline.images`, and prints the stories it
changed: run `documents --fold`, `people --fold` and `score`, then `explain --force` on those, then `build`.
A disputed or anonymous document (the MJ-12 papers, a leaked report, a forum thread) is quoted beside
the story as a source note only: its entry carries `"note_only": true`, a null teller and kind, the
note in `differs`, and `document.provenance`, a sentence on where the document comes from and what is
disputed about it. The note begins with that provenance, no telling is added, and the story's
attestation does not move.

To fold people: a group in `data/person-folds.json` names the spellings of one person (`members`) and
the id they become (`canonical`, held or new), with the name the page shows and the evidence; `check`
lists the near-duplicate ids to decide on, and a pair judged to be two people goes into the file's
`distinct` list with its evidence, so `check` stops listing it. `people --fold` rewrites every place an id stands, merges
the person files, keeps the members as the canonical's `aliases` and adds their names to
`data/person-aliases.json`, so the next merge maps those spellings at once; then `score`, `build` and
`check` run again.

To fold documents: a group in `data/document-folds.json` names the ids of one document under several
titles (`members`) and the id they become (`canonical`, held or new), with the title the page shows and
the evidence. `documents --fold` rewrites every telling and source manifest that names a member, merges
the document files and their texts under `sources/documents/`, and keeps the members and the slugs of every
title as the canonical's `aliases`, so the next merge or sources run maps those titles at once (a field the
members set differently is refused: settle it in the document files first); then `people --fold`, `score`,
`build` and `check` run again.

To fold viewer notes: pull the page's saved notes into `data/notes/<story id>.json` (status `open`), turn each
worth keeping into a `discussion` entry or another edit of the story by hand, mark it `folded` or `dropped`, then
run `check` and `build` again.

