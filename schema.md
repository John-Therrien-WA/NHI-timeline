# The data shapes

Every file is JSON, UTF-8, pretty-printed, one object per file, the file name equal to the object's `id`. Dates are ISO (`2023-07-26`); a year alone is allowed where that is all a story gives (`"1947"`). Unknown is `null`, never a guess.

## Story (`data/stories/<id>.json`)

```json
{
  "id": "roswell-1947",
  "title": "A craft and bodies recovered near Roswell",
  "summary": "One paragraph, in the project's own words, saying what is claimed and by whom, with no judgement of truth.",
  "era": "cold-war-early",
  "years": { "from": 1947, "to": 1947 },
  "place": "roswell-nm",
  "place_text": "Roswell, New Mexico",
  "coordinates": null,
  "kind": "crash-retrieval",
  "claims": ["a craft of non-human origin was recovered", "bodies were recovered"],
  "tellings": [
    { "episode": "dQw4w9WgXcQ", "from_s": 1834.2, "to_s": 1901.0, "teller": "jesse-michels", "quote": "the words exactly as the captions give them", "kind": "secondhand", "cites": ["philip-corso"] },
    { "document": "corso-day-after-roswell-1997", "page": "12", "teller": "philip-corso", "quote": "...", "kind": "firsthand", "cites": [] }
  ],
  "related": [
    { "story": "roswell-weather-balloon-1947", "relation": "contradicts", "note": "the official account" }
  ],
  "tags": ["crash", "bodies", "cover-up"],
  "score": null
}
```

- `kind` of a story: `sighting`, `encounter`, `crash-retrieval`, `reverse-engineering`, `program`, `document`, `testimony`, `theory`, `cosmology` (the frames such as "the control system" or "they are already here"), `place-lore` (the far side of the moon and the like).
- `kind` of a telling: `firsthand` (the teller saw or took part), `official` (a government document, sworn testimony, a court record), `journalist` (a reporter citing named sources), `secondhand` (the teller relays what a named other told them), `researcher` (a summary without a named source), `host` (the podcast host's framing).
- `cites`: the ids of the people the teller credits for the story; independence is computed from this.
- `documents` on a telling: the ids of the documents the teller credits (the prompt's `documents` titles, slugged); a document cited this way adds 0.25 to the attestation, a document that is itself a telling (`"document": id`) adds 0.5.
- `place_text`: the place as the extractor gave it in words; `merge.py` resolves it to `place` through `data/place-aliases.json` or a contained place name, and leaves `place` null when nothing matches (the page then groups the story with the others of the same text).
- `difference` and `link_reason` on a telling: present when `link.py` joined the telling to a story told by others (a `same` link, or a story folded into this one by `link --existing`). `link_reason` is the model's reason for calling it the same story; `difference` is what this telling adds or says differently (dates, numbers, who did what, a stronger or weaker claim), empty when nothing differs. Every telling with either field has a non-empty `link_reason`. `as_told` on such a telling is the framing it came with, `{ "title", "years", "place_text", "story_kind" }` (from the candidate, or from the story a fold absorbed), present when any of the four differs from the story's own; `build.py` passes it through in the telling block.
- `aliases`: the ids of the stories `link --existing` folded into this one; an alias is never also a story id, and `#story=<alias>` opens this story (`build.py` writes the alias map).
- `profile`, `attestation`, `score` and `tier` are written by `score.py` and never by hand (`scoring.md` is the rule). `profile` is the evidence: `independent_tellers`; the independent tellers counted by their strongest kind as `firsthand`, `official_records`, `official_conclusions`, `journalist`, `secondhand`, `researcher`, `host` (an `official` teller is a record unless every official telling of theirs carries `"official_kind": "conclusion"`, the one optional telling field the score reads); `documents` (documents that are tellings) and `credited_documents` (documents only credited by an independent teller); `repetitions` (dependent tellers); `contradicted` (true when a `contradicts` relation joins this story to another, in either direction); `strongest_kind`; `tellers` (the independent tellers' ids); `episodes` (the distinct episode ids). `attestation` is the profile's weighted sum at the default institutional trust, `score` the attestation over the corpus median, `tier` one of `well-attested`, `told-by-several`, `told-once`.

## Candidates (`data/candidates/<video id>.json`)

What `extract.py` pulled from one episode before merging: `{ "episode", "captions", "model", "chunks", "candidates": [...], "dropped": [...] }`. A candidate carries the prompt's answer as given (`title`, `story_kind`, `years_text`, `place_text`, `teller` and `cites` as names, `documents` as titles, `kind`, `quote`) plus the parsed `years` and the `from_s` and `to_s` located in the cues. `dropped` lists the answers whose quote was not verbatim, with the reason. Generated; `merge.py` reads it, nobody edits it.

`link` on a candidate is written by `link.py`: `{ "decision": "same" | "variant" | "new", "story": id or null, "grain": "same" | "broader" | "narrower", "reason", "difference", "against": [ids] }`, plus `id` on `new` and `variant`. `same` names the story the telling joins, `variant` the story the new one is a variant of (a `variant` relation both ways, the reason as the note), `new` none; `grain` is whether the telling's scope matches the story, is wider or is narrower; `id` is the id the new story gets (a later candidate of the same link run may be `same` as it, and merge fails when it would give another); `against` lists the stories offered to the model (empty when nothing scored and no call was made). A `same` at a grain other than `same`, or a `same` joining a `program` to a story of another kind, is stored as `new` with the model's reason and `downgraded`: `{ "from": "same", "story", "why" }`. A candidate without `link` merges by the slug-or-teller rule (same title slug, or same teller with the same years, place and kind).

`data/links.json` is the ledger of `link --existing` and of every downgrade: `{ "seen": [ids], "decisions": { story id: [ { "decision", "story", "grain", "reason", "difference", "against" } ] }, "downgraded": [ { "key", "episode", "grain", "reason", "from", "story", "why" } ] }`, `seen` being the story ids the corpus held when the runs began, `downgraded` one entry per refused `same` (`key` the candidate title or the story id, `episode` null for `--existing`). A story already decided is asked again only about stories outside `seen`. Generated.

## Person (`data/people/<id>.json`)

```json
{ "id": "jesse-michels", "name": "Jesse Michels", "roles": ["host"], "affiliation": "American Alchemy (YouTube)", "links": ["https://www.youtube.com/@AmericanAlchemy"], "note": "" }
```

## Episode (`data/episodes/<video id>.json`)

```json
{ "id": "dQw4w9WgXcQ", "show": "American Alchemy", "title": "...", "host": "jesse-michels", "guests": ["..."], "published": "2024-03-01", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "duration_s": 7420, "captions": "sources/captions/dQw4w9WgXcQ.en.vtt", "language": "en", "auto_captions": true }
```

An episode whose captions came from the Gemini fallback (`pipeline/gemini_captions.py`, for a video YouTube will not serve captions for) has `"captions": "sources/captions/<id>.en.txt"` (there is no .vtt), `"auto_captions": false`, `"captions_source": "gemini"` and `"timestamps_approximate"`: `true` when Gemini's time stamps overshot the duration and were rescaled to fit, so a time code may be some seconds off. Without `captions_source` the captions are YouTube's own.

## Document (`data/documents/<id>.json`)

```json
{ "id": "odni-uap-preliminary-2021", "title": "Preliminary Assessment: Unidentified Aerial Phenomena", "issuer": "Office of the Director of National Intelligence", "date": "2021-06-25", "url": "https://...", "kind": "official", "attests": ["144 reports examined, 143 unexplained"] }
```

## Eras and places

`data/eras.json` is a list of `{ "id", "name", "from", "to" }` with years; `data/places.json` a list of `{ "id", "name", "lat", "lon", "region" }`, with `"source": "lead to verify"` on a place whose coordinates or identity were set from memory and not yet checked. `data/place-aliases.json` is an object of alias text to place id (`"USS Nimitz": "pacific-nimitz"`); matching is case-insensitive on the whole text, else on the longest alias or place name the text contains as whole words. A story may name an era and a place by id, or carry its own `years` and `coordinates`; the page uses the ids for the grid and the raw values for the dot.
