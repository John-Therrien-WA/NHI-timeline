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
  "discussion": [
    { "kind": "debunk", "by": "Charles Moore", "role": "participant", "date": "1995", "source": "https://...", "text": "Charles Moore says the debris was a Project Mogul balloon train he helped launch." },
    { "kind": "rebunk", "by": "Jesse Marcel Jr.", "role": "witness", "episode": "dQw4w9WgXcQ", "time": "0:41:10", "text": "Jesse Marcel Jr. says the material his father brought home matched no balloon." }
  ],
  "score": null
}
```

- `kind` of a story: `sighting`, `encounter`, `crash-retrieval`, `reverse-engineering`, `program`, `document`, `testimony`, `theory`, `cosmology` (the frames such as "the control system" or "they are already here"), `place-lore` (the far side of the moon and the like).
- `kind` of a telling: `firsthand` (the teller saw or took part), `official` (a government document, sworn testimony, a court record), `journalist` (a reporter citing named sources), `secondhand` (the teller relays what a named other told them), `researcher` (a summary without a named source), `host` (the podcast host's framing).
- `cites`: the ids of the people the teller credits for the story; independence is computed from this.
- `documents` on a telling: the ids of the documents the teller credits (the prompt's `documents` titles, slugged); a document cited this way adds 0.25 to the attestation, a document that is itself a telling (`"document": id`) adds 0.5.
- `place_text`: the place as the extractor gave it in words; `merge.py` resolves it to `place` through `data/place-aliases.json` or a contained place name, and leaves `place` null when nothing matches (the page then groups the story with the others of the same text).
- `difference` and `link_reason` on a telling: present when `link.py` joined the telling to a story told by others (a `same` link, or a story folded into this one by `link --existing`). `link_reason` is the model's reason for calling it the same story; `difference` is what this telling adds or says differently (dates, numbers, who did what, a stronger or weaker claim), empty when nothing differs. Every telling with either field has a non-empty `link_reason`. `as_told` on such a telling is the framing it came with, `{ "title", "years", "place_text", "story_kind" }` (from the candidate, or from the story a fold absorbed), present when any of the four differs from the story's own; `build.py` passes it through in the telling block.
- `discussion` (optional): the back and forth about the story, each side a telling of its own, in the order the page shows them (chronological by `date` where dates exist). `kind` is `debunk` (the story is staged, mistaken or explained), `rebunk` (the debunk is wrong, or the thing stays unexplained) or `note` (anything else: context, a correction to the story's framing, a viewer's note folded in). Every entry has `kind`, `by` (the person or outlet) and `text` (one to three sentences in the reported voice, "X says ..."), and a `source` (an http(s) URL) or an `episode` with a `time` (`h:mm:ss`) or both; `role` (`witness`, `participant`, `official`, `researcher`, `journalist`, `host`, `viewer`) and `date` (`YYYY`, `YYYY-MM` or `YYYY-MM-DD`) are optional, and no other field is allowed. Written by hand, never by the pipeline: `merge.py` and `link.py` keep it, a fold under `link --existing` appends the folded story's entries to the survivor's, `build.py` passes it through (an empty list when absent, and an entry with an `episode` gains the YouTube `url` at its `time`), and nothing here scores it. Recording a debunk asserts nothing about who is right.
- `aliases`: the ids of the stories `link --existing` folded into this one; an alias is never also a story id, and `#story=<alias>` opens this story (`build.py` writes the alias map).
- `profile`, `attestation`, `score` and `tier` are written by `score.py` and never by hand (`scoring.md` is the rule). `profile` is the evidence: `independent_tellers`; the independent tellers counted by their strongest kind as `firsthand`, `official_records`, `official_conclusions`, `journalist`, `secondhand`, `researcher`, `host` (an `official` teller is a record unless every official telling of theirs carries `"official_kind": "conclusion"`, the one optional telling field the score reads); `documents` (documents that are tellings) and `credited_documents` (documents only credited by an independent teller); `repetitions` (dependent tellers); `contradicted` (true when a `contradicts` relation joins this story to another, in either direction); `strongest_kind`; `tellers` (the independent tellers' ids); `episodes` (the distinct episode ids). `attestation` is the profile's weighted sum at the default institutional trust, `score` the attestation over the corpus median, `tier` one of `well-attested`, `told-by-several`, `told-once`.

## Viewer notes (`data/notes/<story id>.json`)

The inbox of notes viewers left on a story, kept out of the story file until a person folds them in: a list of `{ "by", "date", "text", "status" }`, `date` as `YYYY`, `YYYY-MM` or `YYYY-MM-DD`, `status` one of `open` (not yet read into the data), `folded` (made into a `discussion` entry or another edit of the story) and `dropped` (read and left out). The file name is a story id or an alias of one. The page saves notes to its artifact database; a session pulls them into these files by hand and marks each as it folds or drops it. `Root.load_notes` refuses a file that is not a list of objects or an entry whose `status` is not one of the three, `check.py` validates the rest; `build.py` counts the open entries (those of the story's aliases too) as the story's `notes_open`; nothing else reads them.

## Images (`data/images/<owner>/<n>.json`, `site/images/<owner>/<n>.jpg`)

One sidecar per photograph, beside the file it describes. The owner is a story id (or an alias of one) or a person id; `n` is 1, 2, ... per owner. `pipeline/images.py` writes both from a manifest (the scouts' findings), and a person may correct a sidecar by hand.

```json
{
  "file": "images/roswell-1947/1.jpg",
  "kind": "place-then",
  "caption": "The Foster ranch debris field near Corona, New Mexico, photographed in 1947.",
  "source": "https://commons.wikimedia.org/wiki/File:...",
  "image_url": "https://upload.wikimedia.org/wikipedia/commons/...",
  "licence": "Public domain (US government work)",
  "licence_kind": "free",
  "credit": "US Army Air Forces",
  "date": "1947-07",
  "fetched": "2026-10-16"
}
```

- `file`: the image path relative to `site/`, always `images/<owner>/<n>.jpg`, or `.png` when the source is a PNG with transparency. Free images are at most 1200 px on the long side, fair-use ones at most 480 px.
- `kind`: for a story owner `object` (a related object), `place-then` (the place at the time, preferred) or `place-now` (the place today, the last resort); for a person owner `headshot`. A story's pictures are objects and places only: a real person's face is never put next to a claim they did not make, so a headshot appears on the page only beside that person's own tellings.
- `caption`: one sentence saying what the photograph shows and when, with no claim that any story is true.
- `source`: the http(s) page the image came from; `image_url`: the file that was downloaded (`images.py` keeps an image whose `image_url` the owner already holds).
- `licence`: the licence exactly as the source states it. `licence_kind`: `free` (public domain, CC0, CC BY, CC BY-SA, US government works) or `fair-use` (news photos, book covers, press images, credited and kept at thumbnail size); a headshot is `free` only, never fair use and never a frame from an episode.
- `credit`: the author or holder as the source states it. `date` (optional): when the photograph was taken, `YYYY`, `YYYY-MM` or `YYYY-MM-DD`. `fetched`: the day it was downloaded, `YYYY-MM-DD`. No other field.

`check.py` refuses a sidecar with a missing or unknown field, an owner that is no story, alias or person, a kind that does not fit the owner, a fair-use headshot, a `file` that is not the JPEG or PNG at its own path, is a PNG without transparency or is larger than its licence allows, an `image_url` a story already holds under its id or an alias, and any file under `site/images/` no sidecar claims. `build.py` gives each story `images` (its own and its aliases' sidecars as `{ file, kind, caption, credit, licence, licence_kind, source, date }`, an empty list when none) and each person `image` (the first headshot's block, or null).

The manifest `images.py` reads is a JSON list of `{ "owner", "kind", "image_url", "source", "licence", "licence_kind", "credit", "caption", "date"? }`, the fields as above; the whole manifest is checked before anything is downloaded, and an image lands under the story id an alias resolves to.

## Candidates (`data/candidates/<video id>.json`)

What `extract.py` pulled from one episode before merging: `{ "episode", "captions", "model", "chunks", "candidates": [...], "dropped": [...] }`. A candidate carries the prompt's answer as given (`title`, `story_kind`, `years_text`, `place_text`, `teller` and `cites` as names, `documents` as titles, `kind`, `quote`) plus the parsed `years` and the `from_s` and `to_s` located in the cues. `dropped` lists the answers whose quote was not verbatim, with the reason. Generated; `merge.py` reads it, nobody edits it.

`link` on a candidate is written by `link.py`: `{ "decision": "same" | "variant" | "new", "story": id or null, "grain": "same" | "broader" | "narrower", "reason", "difference", "against": [ids] }`, plus `id` on `new` and `variant`. `same` names the story the telling joins, `variant` the story the new one is a variant of (a `variant` relation both ways, the reason as the note), `new` none; `grain` is whether the telling's scope matches the story, is wider or is narrower; `id` is the id the new story gets (a later candidate of the same link run may be `same` as it, and merge fails when it would give another); `against` lists the stories offered to the model in the call that decided it: the union of its group's nearest stories and the stories its group's earlier tellings end in, so a `same` or `variant` always names a story in it (empty when nothing scored and no call was made). `link.py` asks about ten candidates per call, and a candidate may be `same` as, or a `variant` of, an earlier candidate of its group: the model names it `#n` and `link` stores the story id it resolves to (the story the earlier candidate joins, or its `id`), so `#n` never appears in a stored link. A `same` at a grain other than `same`, or a `same` joining a `program` to a story of another kind, is stored as `new` with the model's reason and `downgraded`: `{ "from": "same", "story", "why" }`. A candidate without `link` merges by the slug-or-teller rule (same title slug, or same teller with the same years, place and kind).

`data/links.json` is the ledger of `link --existing` and of every downgrade: `{ "seen": [ids], "decisions": { story id: [ { "decision", "story", "grain", "reason", "difference", "against" } ] }, "downgraded": [ { "key", "episode", "grain", "reason", "from", "story", "why" } ] }`, `seen` being the story ids the corpus held when the runs began, `downgraded` one entry per refused `same` (`key` the candidate title or the story id, `episode` null for `--existing`). A story already decided is asked again only about stories outside `seen`. Generated.

## Person (`data/people/<id>.json`)

```json
{ "id": "jesse-michels", "name": "Jesse Michels", "roles": ["host"], "affiliation": "American Alchemy (YouTube)", "links": ["https://www.youtube.com/@AmericanAlchemy"], "note": "" }
```

A person's headshot is not in this file: it is a sidecar under `data/images/<person id>/` (see Images).

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

`data/eras.json` is a list of `{ "id", "name", "from", "to" }` with years; `data/places.json` a list of `{ "id", "name", "lat", "lon", "region" }`, with `"source": "lead to verify"` on a place whose coordinates or identity were set from memory and not yet checked. `data/place-aliases.json` is an object of alias text to place id (`"USS Nimitz": "pacific-nimitz"`); matching is case-insensitive on the whole text, else on the longest alias or place name the text contains as whole words. A story may name an era and a place by id, or carry its own `years` and `coordinates`; the page places a story by its era and place ids and by its raw years and coordinates where it has them.
