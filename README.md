# NHI-timeline

An interactive timeline of the stories told about non-human intelligence and disclosure: which story is told about which era and place, by whom and in which podcasts and documents, and how well each is corroborated across the corpus. Stories, not facts: the data records who said what, and the corroboration does the ranking. `CLAUDE.md` is the working contract, `schema.md` the data shapes, `scoring.md` the score.

## Run

Python 3.12 and `uv`; `yt-dlp` and `claude` on the path for the first two steps. No dependencies
beyond the standard library; `../creator-watch` checked out beside this repo, with its `.venv` and
keys file, for the Gemini fallback only.

```sh
uv run python -m pipeline.check --fixture               # the whole chain on the fictional fixtures, offline
uv run python -m pipeline.captions <video id or URL>    # captions in: sources/captions/<id>.en.txt, data/episodes/<id>.json
../creator-watch/.venv/bin/python -m pipeline.gemini_captions <video id>   # fallback on a 429 or no caption track: a Gemini transcript as the caption text
uv run python -m pipeline.extract <video id>            # claude -p over the captions: data/candidates/<id>.json
uv run python -m pipeline.link <video id>               # claude -p: is each candidate the same story as one held, a variant, or new
uv run python -m pipeline.merge                         # candidates into data/stories, data/people, data/documents
uv run python -m pipeline.score                         # score into each story, data/scores.json
uv run python -m pipeline.build                         # site/data.json and site/data.js
uv run python -m pipeline.check                         # every story has a telling, every id resolves, every quote is verbatim
open site/index.html                                    # the 3D page from disk (reads site/data.js)
cd site && python3 -m http.server 8000                  # or over http (reads site/data.json): http://127.0.0.1:8000/
```

The page in `site/` is the timeline in 3D, plain HTML, CSS and JS with three.js from jsDelivr and no
build step: `index.html`, `style.css`, `app.js` (the controller) and `js/` (`model.js` the data
check, the score recomputed at the reader's institutional trust and the tiers; `corridor.js` and
`globe.js` the two views; `panel.js` the story panel; `notes.js` the notes box). The corridor is the
default view: time runs ahead, stretched where many stories are told, the angle is the kind or the
region, and the rings are the tiers. The globe is the second view: regions as patches sized by story
count, eras as shells. `M` switches; the keys are listed on the page. A link may carry
`#story=<id or alias>`, `mode=globe`, `rail=time|kind|strength|links` and `trust=<0.5 to 1.25>`;
`?data=<path>` loads another data file from a relative path beside the page (a `.js` defining
`window.NHI_DATA`, or JSON over http), for a test copy. At load the page recomputes every attestation
and score from the profiles and refuses to draw when they differ from the stored values. Published as an artifact with the `db` capability,
the notes box saves to the collection `notes`; anywhere else it copies the note as text.

Run the first command once after any change to the pipeline; it must print `check: ok (fixture)`.
Every stage takes `--root DIR` to work on another data root (the fixture check uses a temporary
copy of `tests/fixtures/`). A story the pipeline got wrong is corrected by hand in its JSON and
`check` is run again; `merge` never changes an existing story or person: it appends tellings and fills a
null `place` or missing `place_text`, nothing else. A place the extractor names in words that
`data/place-aliases.json` does not know stays unresolved until an alias or a place is added; the next
`merge` then fills it.

To fold viewer notes: pull the page's saved notes into `data/notes/<story id>.json` (status `open`), turn each
worth keeping into a `discussion` entry or another edit of the story by hand, mark it `folded` or `dropped`, then
run `check` and `build` again.

