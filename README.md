# NHI-timeline

An interactive timeline of the stories told about non-human intelligence and disclosure: which story is told about which era and place, by whom and in which podcasts and documents, and how well each is corroborated across the corpus. Stories, not facts: the data records who said what, and the corroboration does the ranking. `CLAUDE.md` is the working contract, `schema.md` the data shapes, `scoring.md` the score.

## Run

Python 3.12 and `uv`; `yt-dlp` and `claude` on the path for the first two steps. No dependencies
beyond the standard library.

```sh
uv run python -m pipeline.check --fixture               # the whole chain on the fictional fixtures, offline
uv run python -m pipeline.captions <video id or URL>    # captions in: sources/captions/<id>.en.txt, data/episodes/<id>.json
uv run python -m pipeline.extract <video id>            # claude -p over the captions: data/candidates/<id>.json
uv run python -m pipeline.merge                         # candidates into data/stories, data/people, data/documents
uv run python -m pipeline.score                         # score into each story, data/scores.json
uv run python -m pipeline.build                         # site/data.json and site/data.js
uv run python -m pipeline.check                         # every story has a telling, every id resolves, every quote is verbatim
open site/index.html                                    # or publish site/ as a private artifact
```

Run the first command once after any change to the pipeline; it must print `check: ok (fixture)`.
Every stage takes `--root DIR` to work on another data root (the fixture check uses a temporary
copy of `tests/fixtures/`). A story the pipeline got wrong is corrected by hand in its JSON and
`check` is run again; `merge` never changes an existing story or person: it appends tellings and fills a
null `place` or missing `place_text`, nothing else. A place the extractor names in words that
`data/place-aliases.json` does not know stays unresolved until an alias or a place is added; the next
`merge` then fills it.

