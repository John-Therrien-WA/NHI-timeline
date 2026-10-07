# NHI-timeline

An interactive timeline of the stories told about non-human intelligence (NHI) and disclosure: which story is told about which era and which place, by whom, in which podcasts and documents, and how well each story is corroborated across the whole corpus. John's project (8 October 2026); it began inside `robot-release` (the Wild Animal album, where the dark side of the moon and the end of *Abend* touch the theme) and is its own repo because the material is larger than a song.

The timeline shows stories, not facts. A story is what someone said happened; the project records who said it, where, when, and who else says the same, and lets the corroboration do the ranking. Nothing here asserts that any story is true.

## Principles

- **Every story carries its tellings.** A story exists in the data only with at least one telling: an episode or document, a time code or page, and the quoted words. A story without a quote is a note, not a story.
- **Corroboration is counted, never judged by taste.** The score is a function of the tellings (how many independent tellers, of what kind, with what documents), normalised against the corpus, so a story's place on the timeline follows from the data and changes when the corpus grows.
- **Independence is explicit.** A teller who repeats another teller is not a second source; the data says whom a teller cites. The same person telling the same story on three podcasts is one teller.
- **Plain files are the database.** JSON for data, Markdown for notes, one file per thing, hand-correctable, diffable. No server, no binary store.
- **Fail loud.** Malformed data or a violated precondition raises with a clear message. A crash beats a quiet wrong score.
- **Living docs.** This file and the others describe the current state; git is the history. No changelogs, no dated narration in docs. No em dashes anywhere; commas, colons, periods, parentheses.
- **Sources stay reachable.** Transcripts are pulled from YouTube's own captions (`yt-dlp`), kept under `sources/` by video id, and cited by time code. Nothing is scraped that the platform does not publish.

## Layout

- `data/stories/<slug>.json`: one story each (`schema.md` gives the shape). The heart of the project.
- `data/people/<slug>.json`: the tellers: name, role (witness, participant, official, researcher, journalist, host), what they cite, public links.
- `data/episodes/<video id>.json`: one podcast episode or interview: show, host, guests, date, URL, duration, the caption file it was read from.
- `data/documents/<slug>.json`: public documents (reports, hearings, articles, FOIA releases): title, date, URL, what it attests.
- `data/eras.json`, `data/places.json`: the timeline's axes, hand-edited; a story names an era by id and a place by id, or gives its own years and coordinates.
- `sources/captions/<video id>.<lang>.vtt` and `.txt`: the captions as fetched and as plain text with time codes (git-tracked: they are the evidence; a few MB each at most).
- `pipeline/`: `captions.py` (yt-dlp captions in, text with time codes out), `extract.py` (an episode's text to story candidates through `claude -p` with `prompts/extract.md`), `merge.py` (candidates into stories, with the overlap links), `score.py` (the corroboration score, `scoring.md` is its specification), `build.py` (data to `site/data.json`), `check.py` (every story has a telling, every telling resolves, every quote is a verbatim substring of its caption text).
- `prompts/`: the prompts the pipeline sends, as files, never inline strings.
- `site/`: the timeline page, plain HTML, CSS and JS, no build step, reads `site/data.json`; opened locally or published as a private artifact.
- `notes/`: research notes and the seed timeline (the first one came from `robot-release/research/nhi-disclosure-narratives.md`).
- `schema.md`: the data shapes. `scoring.md`: how the score is computed and why.

## The score, in short

A story's attestation is the sum over its independent tellers of a weight by kind (first-hand witness or participant 1.0, an official document or sworn testimony 1.0, a journalist citing named sources 0.6, a second-hand account 0.4, a researcher's summary 0.25), plus 0.5 for each independent document, where two tellers are independent only if neither cites the other and they are not the same person. The corroboration score is the attestation divided by the corpus median attestation, so 1.0 means "as well attested as the typical story here" and the scale moves as the corpus grows. Two stories overlap when they share an event, a teller or a document, or when `merge.py` or a person has marked them `same-event`, `variant`, `corroborates` or `contradicts`; the page draws overlaps as links and `contradicts` in a different colour. `scoring.md` holds the full rule and its open questions.

## Working here

- Python 3.12, `uv`; `yt-dlp` on the path; `claude` on the path for the extraction pass. `uv run python -m pipeline.<stage>`.
- A story is edited by hand in its JSON when the pipeline gets it wrong; `check.py` keeps hand edits honest.
- Quotes are verbatim from the captions, with the video id and the time code. A paraphrase is marked as one.
- Git: commit after each piece of work; `origin` is `git@github-personal:John-Therrien-WA/NHI-timeline.git`; push at the end of a session; never force-push.
- Prior art and the hazard list (what must never be stated as fact, the platforms' labelling rules) live in `notes/` and are read before anything is published.
