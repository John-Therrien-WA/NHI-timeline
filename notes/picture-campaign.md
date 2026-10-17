# Picture campaign

The aim: every story carries at least one photograph, a well-attested story several, so the page can show a picture as the story's card instead of a bare sphere. The campaign runs as waves of `scout` agents, each given a batch of stories and this brief, each returning a manifest that `pipeline/images.py` ingests. The rules below are the project's (`CLAUDE.md` Principles, `schema.md` Images); the brief restates them for an agent that has read neither.

## Scout brief

You find photographs for a batch of stories about non-human intelligence and disclosure. The stories are what someone said happened; nothing you return may assert that a story is true. You cannot write files: your whole answer is the manifest text and a short list of the stories you found nothing for.

**Read first**: the batch file named in your prompt. Each entry has `id`, `title`, `kind`, `years`, `place_text`, `claims`, `summary` and often `plain` (a plain-language telling). The `plain` text tells you what the story is about; the title alone often does not.

**What a picture may be**: an object or a place, never a person's face.
- `object`: a thing the story is about or that stands for it: a document's cover or first page, an aircraft or ship type named in the story, a building, a craft model, an instrument, a map, a newspaper page, a book cover (a book cover or press image is fair use).
- `place-then`: the place at the time of the story (preferred): an airfield in the 1950s for a 1952 story, a base as it was built, a town in that decade.
- `place-now`: the place today, the last resort, only when nothing closer exists.
A photograph of a person, a crowd close enough to show faces, or a frame from a video or podcast is refused. A picture that would put a real person's face next to a claim they did not make is the one thing the project forbids.

**Licence**: `free` is preferred: public domain, CC0, CC BY, CC BY-SA, a US government work (US Air Force, Navy, NASA, NARA, Library of Congress, ODNI, Congress). Wikimedia Commons is the first place to look; Flickr Commons, NASA, NARA, the Library of Congress and government sites are others. `fair-use` is allowed for a news photo, a book cover, a document scan or a press image when nothing free exists: it is kept at thumbnail size and flagged; give the holder as credit and the page it is on as source. Copy the licence text as the source states it (a Commons file page states it under "Licensing"). Never guess a licence: a file whose licence you cannot see is not returned.

**How to search**: Wikimedia Commons first, through its own pages, which WebFetch reads:
- search: `https://commons.wikimedia.org/w/index.php?search=<words>&ns6=1` (file namespace), or the API `https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch=<words>&srnamespace=6&srlimit=20&format=json`
- a file's licence, author and date: `https://commons.wikimedia.org/w/api.php?action=query&prop=imageinfo&iiprop=extmetadata|url|mime&titles=File:<name>&format=json` (the `extmetadata` fields `LicenseShortName`, `License`, `Artist`, `DateTimeOriginal`, `ImageDescription`)
- the English Wikipedia article on the event, place, base, ship, document or programme: its images are Commons files, named in the page.
WebSearch is a shared, limited resource: use it at most six times for the whole batch, for a story whose subject you cannot name without it. A story set at a named base, town, ship, aircraft, agency or document nearly always has a free Commons picture of that base, town, ship, aircraft type, building or document; look for the specific first, then the type (a B-52 for a story about one, the Pentagon for a Pentagon office), then the place.

**Manifest**: a JSON list, one entry per picture, exactly these fields:
```json
[
  {
    "owner": "<story id from the batch>",
    "kind": "object" | "place-then" | "place-now",
    "image_url": "https://commons.wikimedia.org/wiki/Special:FilePath/<File name without the File: prefix, spaces as underscores>?width=1200",
    "source": "https://commons.wikimedia.org/wiki/File:<File name>",
    "licence": "<the licence as the source states it>",
    "licence_kind": "free" | "fair-use",
    "credit": "<author or holder as the source states it>",
    "caption": "<one sentence: what the photograph shows and when, and how it relates to the story, with no claim that the story is true>",
    "date": "<YYYY, YYYY-MM or YYYY-MM-DD when the source gives it; omit the field otherwise>"
  }
]
```
For a Commons file, `image_url` is always the `Special:FilePath/...?width=1200` form (`?width=480` for fair use), and `source` the `File:` page. For another host, `image_url` is the direct JPEG or PNG and `source` the page it is on. A file that is not a JPEG or PNG (a PDF, a TIFF, an SVG) is not returned. The caption is in the project's voice: plain, factual, the year named, "the 1967 account is told from a facility of this kind" rather than "where the UFO disabled the missiles".

**How many**: for a well-attested story up to three pictures (an object and a place-then are the best pair), for any other story one, two when both are strong. Quality over count: a story whose subject has no picture (a theory, a conversation, a claim with no place or object) is listed under "nothing found" with a short reason, not given a generic picture of the sky. A picture of a named object or place from another decade is fine when the caption says so.

**Answer**: the manifest as one fenced JSON block, then "Nothing found:" with the ids and one line each, then "Searches used: N" (WebSearch calls). No other text.

## State

Written by the lead only. Each wave: the batches, the agents, what came back, what the ingest kept, the commit.

- Wave 1 (pilot, 17 October 2026, 23:45 CEST): the 100 well-attested stories without pictures, five batches of twenty by score, five scouts in parallel. The scouts returned 125 entries for 77 of the 100 stories; 23 found nothing usable. Ingest kept 124 (123 free, 1 fair-use, the Condon Report cover); Homestead AAF 1943 for the Nixon and Gleason story still hit a Wikimedia 429 and is left out. A visual pass over contact sheets found no faces; the figures in the Oberth museum picture are mannequins. Pace: about 5 minutes and 90k tokens per batch of 20. Ingest lessons: Wikimedia answers a burst of full-size `Special:FilePath` downloads with 429 and asks for its standard thumbnail widths, so a manifest names `?width=1280` (sips still caps at 1200), and `images.py` waits a 429 out (30, 90, 180 s) before it fails a download. Each ingest runs sandboxed first (the checks and most downloads), then once hatched for what the sandbox truncates and for sips; the stage is idempotent, so the re-run only adds the missing. After this wave the run stops for John: expected coverage and pace reported, his yes starts the told-by-several wave (77 stories, four batches) and the told-once waves (2885 stories, 116 batches of 25).
