# NHI-timeline

An interactive timeline of the stories told about non-human intelligence and disclosure: which story is told about which era and place, by whom and in which podcasts and documents, and how well each is corroborated across the corpus. Stories, not facts: the data records who said what, and the corroboration does the ranking. `CLAUDE.md` is the working contract, `schema.md` the data shapes, `scoring.md` the score.

## Run

Python 3.12 and `uv`; `yt-dlp` and `claude` on the path for the first two steps. No dependencies
beyond the standard library; `../creator-watch` checked out beside this repo, with its `.venv` and
keys file, for the Gemini fallback only. The link pass works in groups of about ten candidates per
`claude -p` call (`--batch N`, default 10), saving the candidate file after each group, so a killed
run picks up at the first candidate without a `link`.

```sh
uv run python -m pipeline.check --fixture               # the whole chain on the fictional fixtures, offline
uv run python -m pipeline.captions <video id or URL>    # captions in: sources/captions/<id>.en.txt, data/episodes/<id>.json
../creator-watch/.venv/bin/python -m pipeline.gemini_captions <video id>   # fallback on a 429 or no caption track: a Gemini transcript as the caption text
uv run python -m pipeline.extract <video id>            # claude -p over the captions: data/candidates/<id>.json
uv run python -m pipeline.link <video id>               # claude -p, about ten candidates a call (--batch): is each the same story as one held, a variant, or new
uv run python -m pipeline.merge                         # candidates into data/stories, data/people, data/documents
uv run python -m pipeline.clips --report                # claude -p, about six groups a call: clips a host cut into another episode, who speaks them, from where (data/clips.json); prints what it would change
uv run python -m pipeline.clips                         # the same, then a telling inside a replayed clip gets replay_of and the clip's speaker as teller
uv run python -m pipeline.sources <manifest.json>       # public sources the stories name: their words as document tellings, sources/documents/<id>.txt, source notes
uv run python -m pipeline.people --fold                 # data/person-folds.json applied: each spelling of a person becomes one id, the person files merged
uv run python -m pipeline.score                         # score into each story, data/scores.json
uv run python -m pipeline.explain --all --model opus    # claude -p, about twelve stories a call: a plain telling for every story, written ground up
uv run python -m pipeline.images <manifest.json>        # found photographs in: site/images/<owner>/<n>.jpg, data/images/<owner>/<n>.json
uv run python -m pipeline.build                         # site/data.json and site/data.js, the plain tellings in site/plain.json and site/plain.js
uv run python -m pipeline.check                         # every story has a telling, every id resolves, every quote is verbatim
open site/index.html                                    # the 3D page from disk (reads site/data.js)
cd site && python3 -m http.server 8000                  # or over http (reads site/data.json): http://127.0.0.1:8000/
```

A long explain run splits into n background runs side by side, `explain --all --shard 1/4` to
`--shard 4/4`: each takes every fourth story of the ordered list from its own start, so together they
cover the list once over disjoint sets.

The page in `site/` is the timeline in 3D, plain HTML, CSS and JS with three.js from jsDelivr and no
build step: `index.html`, `style.css`, `app.js` (the controller) and `js/` (`model.js` the data
check, the score recomputed at the reader's institutional trust and the tiers; `cards.js` the picture
cards, `corridor.js` and `globe.js` the two views (a story with pictures shows them as cards, in place of
its sphere in the corridor and above its marker on the globe); `panel.js` the story panel; `notes.js` the notes box). The corridor is the
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
the notes box saves to the collection `notes`; anywhere else it copies the note as text.

Run the first command once after any change to the pipeline; it must print `check: ok (fixture)`.
Every stage takes `--root DIR` to work on another data root (the fixture check uses a temporary
copy of `tests/fixtures/`). A story the pipeline got wrong is corrected by hand in its JSON and
`check` is run again; `merge` never changes an existing story or person: it appends tellings and fills a
null `place` or missing `place_text`, nothing else. A place the extractor names in words that
`data/place-aliases.json` does not know stays unresolved until an alias or a place is added; the next
`merge` then fills it.

The images stage downloads with a descriptive User-Agent and resizes with macOS `sips`. It is run
sandboxed first, `.venv/bin/python -m pipeline.images <manifest> --keep-going`, with the hosts
commons.wikimedia.org, upload.wikimedia.org and thumb.wikimedia.org allowed. Only when a run fails
with the `sips` temporary-file error, or with truncated downloads (the sandbox proxy cuts larger
bodies, seen as `IncompleteRead`), is that one command run again outside the sandbox; the run is
idempotent, so the images already added are kept. Its manifest is a
JSON list of `{ "owner", "kind", "image_url", "source", "licence", "licence_kind", "credit",
"caption", "date"? }` (`schema.md`, Images); an image already held is kept, so a manifest can be run
again. To publish the page as an artifact, pass `site/images/` in the artifact's `files` beside
`data.json` and `plain.json`, so the relative `images/...` paths resolve; while any `fair-use` image is among them the
artifact stays private.

To check a source: when a story names a public source (a paper, a book, a memo, a patent, a court
record, an article), a scout finds it and returns a manifest entry (`schema.md`, Document): the
document, a plain-text URL for a public-domain text or the quoted passages with their locators for
any other, the quotes that say what the story claims, the author, the telling's kind, a note
when the source reads otherwise than the tellers, and its pictures. Run
`uv run python -m pipeline.sources <manifest> --keep-going` after `clips` and before `people --fold`,
with the text's host
allowed; it checks every quote against the text before writing an entry, keeps a text file already
there, and adds nothing twice, so a manifest can be run again. It writes the pictures to
`<manifest stem>.images.json` beside the manifest for `pipeline.images`, and prints the stories it
changed: run `people --fold` and `score`, then `explain --force` on those, then `build`.

To fold people: a group in `data/person-folds.json` names the spellings of one person (`members`) and
the id they become (`canonical`, held or new), with the name the page shows and the evidence; `check`
lists the near-duplicate ids to decide on. `people --fold` rewrites every place an id stands, merges
the person files, keeps the members as the canonical's `aliases` and adds their names to
`data/person-aliases.json`, so the next merge maps those spellings at once; then `score`, `build` and
`check` run again.

To fold viewer notes: pull the page's saved notes into `data/notes/<story id>.json` (status `open`), turn each
worth keeping into a `discussion` entry or another edit of the story by hand, mark it `folded` or `dropped`, then
run `check` and `build` again.

