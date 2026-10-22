# The data shapes

Every file is JSON, UTF-8, pretty-printed, one object per file, the file name equal to the object's `id`. Dates are ISO (`2023-07-26`); a year alone is allowed where that is all a story gives (`"1947"`). Unknown is `null`, never a guess.

## Story (`data/stories/<id>.json`)

```json
{
  "id": "roswell-1947",
  "title": "A craft and bodies recovered near Roswell",
  "plain": "A plain telling for a reader new to the subject: who the people are by role, what they say happened, where and when, what every programme and document named is, in the reported voice.",
  "plain_by": "hand",
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
- `cites`: the ids of the people the teller credits for the story; independence is computed from this. A telling never cites its own teller (on a replay, the teller it was: `teller_was`). A document telling (`"document": id`, the source's own words) cites nobody: its `cites` is empty or absent, and `check.py` refuses one that names anyone, since the score drops every cite of a source's author (`scoring.md`, "Tellers and independence") and a cite from the author back to a citer would make the author the repetition. In `site/data.json` each telling also carries `repeats`: for a teller the score counts as a repetition, the cites that are edges of the citation graph (`score.cite_edges`), which the page shows as "repeats" and the rest of `cites` as "cites"; empty for an independent teller.
- `documents` on a telling: the ids of the documents the teller credits (the prompt's `documents` titles, slugged); a document cited this way adds 0.25 to the attestation, a document that is itself a telling (`"document": id`) adds 0.5.
- `place_text`: the place as the extractor gave it in words; `merge.py` resolves it to `place` through `data/place-aliases.json` or a contained place name, and leaves `place` null when nothing matches (the page then groups the story with the others of the same text).
- `replay_of` and `teller_was` on a telling: written by `pipeline/clips.py` when the telling lies inside a clip a host cut into the episode (a recording aired in more than one episode, `data/clips.json`). `replay_of` is the occurrence the recording belongs to, `{ "episode", "from_s" }`, or `{ "outside": true }` when every occurrence in the corpus replays a recording from outside it (a news interview, a documentary); a telling inside the origin occurrence itself has no `replay_of`. When the extractor credited the clip's words to someone who is neither the clip's speaker nor one of the other voices heard in it (usually the episode's guest), `teller` is the clip's speaker and `teller_was` keeps the teller the extractor gave, for the record. Both are kept only while the ledger says so: a telling the ledger no longer covers gets its `teller_was` back as `teller` and loses both fields.
- `difference` and `link_reason` on a telling: present when `link.py` joined the telling to a story told by others (a `same` link, or a story folded into this one by `link --existing`). `link_reason` is the model's reason for calling it the same story; `difference` is what this telling adds or says differently (dates, numbers, who did what, a stronger or weaker claim), empty when nothing differs. Every telling with either field has a non-empty `link_reason`. `as_told` on such a telling is the framing it came with, `{ "title", "years", "place_text", "story_kind" }` (from the candidate, or from the story a fold absorbed), present when any of the four differs from the story's own; it stays in the story file (`build.py` leaves it and `link_reason` out of the telling block the page reads, which keeps `difference`).
- `discussion` (optional): the back and forth about the story, each side a telling of its own, in the order the page shows them (chronological by `date` where dates exist). `kind` is `debunk` (the story is staged, mistaken or explained), `rebunk` (the debunk is wrong, or the thing stays unexplained) or `note` (anything else: context, a correction to the story's framing, a viewer's note folded in). Every entry has `kind`, `by` (the person or outlet) and `text` (one to three sentences in the reported voice, "X says ..."), and a `source` (an http(s) URL) or an `episode` with a `time` (`h:mm:ss`) or both; `role` (`witness`, `participant`, `official`, `researcher`, `journalist`, `host`, `viewer`) and `date` (`YYYY`, `YYYY-MM` or `YYYY-MM-DD`) are optional, and no other field is allowed. Written by hand (except the `source` entries, below), never by any other stage: `merge.py` and `link.py` keep it, a fold under `link --existing` appends the folded story's entries to the survivor's, `build.py` passes it through (an empty list when absent, and an entry with an `episode` gains the YouTube `url` at its `time`), and nothing here scores it. Recording a debunk asserts nothing about who is right.
- A `source` entry in `discussion` is written by `pipeline/sources.py` when the manifest says a source the story names reads otherwise than the tellers tell it: `{ "kind": "source", "by": the document's title, "date": the document's date (when it is YYYY, YYYY-MM or YYYY-MM-DD), "source": the document's url (else its text_url), "text": what the source says against what the tellers say }`, appended once (an entry with the same text is not added again). Recording it asserts nothing about the story, only what the source's own words are. A note-only entry (a disputed or anonymous document, quoted beside the story and counted as no telling) writes the same entry with `text` the document's `provenance` (a period added when it has no end punctuation) followed by the manifest's `differs`. `site/data.json` passes the entry through as written; the document whose url or text_url its `source` is (`sources.note_documents`) is in the story's `documents` block with its `provenance`.
- A document telling added by `pipeline/sources.py` is `{ "document", "page", "teller", "quote", "kind", "cites": [], "documents": [] }`: `page` the locator of the quote (a page, chapter or section, as text), `teller` the author's person id (an institution as author is the document's `issuer` as a person of role `official`, and its tellings are then of kind `official` whatever the manifest says), `kind` `firsthand` (the author's own account or text), `official` (a government record), `journalist` (a news report) or `researcher` (a book summarising others). Its `quote` is a verbatim substring of `sources/documents/<document id>.txt` (see Document), and a story holds one telling per (document, quote).
- `plain` (optional until the stage has run): the plain-language telling for a reader who has never heard of the subject, written ground up in the reported voice (people by role before name, every programme, acronym and document explained, what the tellers say happened and why it is told, no verdict), two to three sentences for a `told-once` story, three to five for `told-by-several`, a short paragraph for `well-attested`. Written by `pipeline/explain.py` from the story's tellings and kept by `merge.py` and `link.py`. `plain_by: "hand"` marks a telling a person wrote or edited, which the stage never overwrites; `build.py` passes `plain` through (null when absent) and the page shows it first, under the title.
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
- `kind`: for a story owner `object` (a related object), `place-then` (the place at the time, preferred) or `place-now` (the place today, the last resort) or `person` (a photograph showing someone the story is about, free-licensed only, with `person` naming them); for a person owner `headshot`. A real person's face is never put next to one other person's claim about them: a `person` picture is allowed only when the story's profile in `data/scores.json` counts two or more independent tellers or lists the person shown among its tellers, and a headshot appears on the page only beside that person's own tellings.
- `caption`: one sentence saying what the photograph shows and when, with no claim that any story is true.
- `source`: the http(s) page the image came from; `image_url`: the file that was downloaded (`images.py` keeps an image whose `image_url` the owner already holds).
- `licence`: the licence exactly as the source states it. `licence_kind`: `free` (public domain, CC0, CC BY, CC BY-SA, US government works) or `fair-use` (news photos, book covers, press images, credited and kept at thumbnail size); a headshot is `free` only, never fair use.
- `credit`: the author or holder as the source states it. `date` (optional): when the photograph was taken, `YYYY`, `YYYY-MM` or `YYYY-MM-DD`. `person` (a `person` picture only, and required there): who it shows, their person id when they are in `data/people`, else their name. `fetched`: the day it was downloaded, `YYYY-MM-DD`. No other field.

`check.py` refuses a sidecar with a missing or unknown field, an owner that is no story, alias or person, a kind that does not fit the owner, a fair-use headshot, a `file` that is not the JPEG or PNG at its own path, is a PNG without transparency or is larger than its licence allows, an `image_url` a story already holds under its id or an alias, and any file under `site/images/` no sidecar claims. `build.py` gives each story `images` (its own and its aliases' sidecars as `{ file, kind, caption, credit, licence, licence_kind, source, date }`, an empty list when none) and each person `image` (the first headshot's block, or null).

The manifest `images.py` reads is a JSON list of `{ "owner", "kind", "image_url", "source", "licence", "licence_kind", "credit", "caption", "date"? }`, the fields as above; the whole manifest is checked before anything is downloaded, and an image lands under the story id an alias resolves to. With `--from <scratch root>` an entry whose `image_url` a sidecar under `<scratch root>/data/images/` holds is copied from there instead of downloaded: the file's bytes as they are, the sidecar written from the entry with the scratch sidecar's `fetched`, under the owner's next free `n` in the destination; every copy is checked (file present, format, licence size, `fetched`) before anything is written, and an entry with no match is downloaded.

## Candidates (`data/candidates/<video id>.json`)

What `extract.py` pulled from one episode before merging: `{ "episode", "captions", "model", "chunks", "candidates": [...], "dropped": [...] }`. A candidate carries the prompt's answer as given (`title`, `story_kind`, `years_text`, `place_text`, `teller` and `cites` as names, `documents` as titles, `kind`, `quote`) plus the parsed `years` and the `from_s` and `to_s` located in the cues. `dropped` lists the answers whose quote was not verbatim, with the reason. Generated; `merge.py` reads it, nobody edits it.

`link` on a candidate is written by `link.py`: `{ "decision": "same" | "variant" | "new", "story": id or null, "grain": "same" | "broader" | "narrower", "reason", "difference", "against": [ids] }`, plus `id` on `new` and `variant`. `same` names the story the telling joins, `variant` the story the new one is a variant of (a `variant` relation both ways, the reason as the note), `new` none; `grain` is whether the telling's scope matches the story, is wider or is narrower; `id` is the id the new story gets (a later candidate of the same link run may be `same` as it, and merge fails when it would give another); `against` lists the stories offered to the model in the call that decided it: the union of its group's nearest stories and the stories its group's earlier tellings end in, so a `same` or `variant` always names a story in it (empty when nothing scored and no call was made). `link.py` asks about ten candidates per call, and a candidate may be `same` as, or a `variant` of, an earlier candidate of its group: the model names it `#n` and `link` stores the story id it resolves to (the story the earlier candidate joins, or its `id`), so `#n` never appears in a stored link. A `same` at a grain other than `same`, or a `same` joining a `program` to a story of another kind, is stored as `new` with the model's reason and `downgraded`: `{ "from": "same", "story", "why" }`. A candidate without `link` merges by the slug-or-teller rule (same title slug, or same teller with the same years, place and kind).

`data/links.json` is the ledger of `link --existing` and of every downgrade: `{ "seen": [ids], "decisions": { story id: [ { "decision", "story", "grain", "reason", "difference", "against" } ] }, "downgraded": [ { "key", "episode", "grain", "reason", "from", "story", "why" } ] }`, `seen` being the story ids the corpus held when the runs began, `downgraded` one entry per refused `same` (`key` the candidate title or the story id, `episode` null for `--existing`). A story already decided is asked again only about stories outside `seen`. Generated.

## Clips (`data/clips.json`)

The ledger of the passages two or more episodes share word for word, as `pipeline/clips.py` finds and judges them: `{ "params", "groups": [...] }`, `params` the detection's settings (shingle length, minimum run, boilerplate cut-off, the joins and the 4 s slack a telling may stick out of an occurrence).

```json
{ "id": "09KP8XVf5nY-9288", "text": "you have uncovered collaboration between nola tesla and ...",
  "occurrences": [ { "episode": "09KP8XVf5nY", "from_s": 9288.0, "to_s": 9315.0, "words": 57 },
                   { "episode": "areO7Mej44E", "from_s": 4651.0, "to_s": 4682.0, "words": 57 } ],
  "verdict": "clip", "speaker": "harold-malmgren", "speaker_name": "Harold Malmgren", "also_heard": ["jesse-michels"],
  "origin": { "episode": "09KP8XVf5nY", "from_s": 9288.0 },
  "reason": "In the Greer episode the host introduces Malmgren's tweets and the passage breaks into the conversation; in Malmgren's own episode it answers the host's question.",
  "model": "opus" }
```

- `id`: the first occurrence's episode and second, kept for the group's life. `text`: the shared words of the first occurrence, lowercased (at most 400 characters). `occurrences`: two or more, by episode id; `from_s` the start of the first cue the run touches, `to_s` the start of the cue after the last, `words` the run's length.
- `verdict`: `clip` (one recording aired more than once), `not-a-clip` (the words coincide but each episode's own speaker says them: a sponsor read, a scripted narration, two people reading one document), `unclear`, or null while unjudged. A `clip` has `speaker` (a person id; the person whose account the passage carries, in an exchange the one interviewed), `speaker_name` (the name a person file is created with when the id has none), `also_heard` (the ids of the other voices in the passage, such as the interviewer) and `origin` (`{ "episode", "from_s" }` of one of its occurrences, or `"outside"`); any other verdict has them null and empty. `reason` and `model` say why and who judged.
- `"by": "hand"` marks a group a person wrote or corrected: the stage keeps it exactly as written, never asks about it, and drops any detected group that overlaps it. Without it, a group keeps its verdict while detection finds the same occurrences, and is judged again when they change.

## Person (`data/people/<id>.json`)

```json
{ "id": "jesse-michels", "name": "Jesse Michels", "roles": ["host"], "affiliation": "American Alchemy (YouTube)", "links": ["https://www.youtube.com/@AmericanAlchemy"], "note": "", "aliases": [] }
```

A person's headshot is not in this file: it is a sidecar under `data/images/<person id>/` (see Images). `aliases` (optional, written by `pipeline/people.py`): the ids folded into this person, none of them a person file of its own and none an alias of another person; `build.py` passes it through on each person (an empty list when absent).

## Person folds (`data/person-folds.json`)

The decided folds of one person under several spellings (`groups`) and the close ids judged to be two people (`distinct`), an object with exactly these two lists, hand-correctable:

```json
{ "groups": [ { "canonical": "wernher-von-braun", "name": "Wernher von Braun", "members": ["warner-von-braun"],
                "reason": "The captions spell the rocket engineer's first name as they hear it; the tellings are about the same man." } ],
  "distinct": [ { "pair": ["scott-kelly", "scott-pelley"],
                  "reason": "Scott Kelly is the astronaut who tells his own stories; Scott Pelley is the 60 Minutes journalist." } ] }
```

- `canonical`: the id the members become, a person id the corpus holds or a new one (the stage creates its file). `name`: the name as the page shows it. `members`: one or more other ids of the same person, spellings that chain ("andre-puharic", "andy-puharich") in one group. `reason`: the evidence, one or two sentences, saying why the ids are one person; a reason that begins "different" or "not the same" (case-insensitive, after whitespace) is refused, and so is a `distinct` reason that begins "same". No other field.
- A member is in one group only, is never a canonical, and is a person file or an id the data names; the canonical is in no group's members and is not an alias of another person.
- `distinct`: each entry `{ "pair", "reason" }`, `pair` two different person ids, `reason` the evidence that they are two people. A pair is listed once (in either order); each id is a person (a person file, or a canonical the fold creates) and a member of no group. `people.py` and `check.py` refuse a pair that breaks this, naming it; `check.py` no longer lists the pair among its near-duplicate warnings. The fold itself never reads it.
- `pipeline/people.py --fold` applies the groups (CLAUDE.md, Layout), a member's headshot dropped when the canonical already holds the same `image_url`: afterwards no member id has a person file or stands where a person id goes (a telling's `teller`, `teller_was` or `cites`, a story's profile, an episode's `host` or `guests`, a clip's `speaker` or `also_heard`, an image directory or a person picture's `person`, a target in `data/person-aliases.json`), and `check.py` refuses one that does.

## Document folds (`data/document-folds.json`)

The decided folds of one document under several titles, a list of groups, hand-correctable:

```json
[ { "canonical": "twining-memo", "title": "AMC Opinion Concerning \"Flying Discs\" (the Twining memo)",
    "members": ["twining-memo-1947", "twining-memorandum"],
    "reason": "One memo, Nathan Twining's of 23 September 1947; the sources stage holds its text under twining-memo." } ]
```

- `canonical`: the id the members become, a document id the corpus holds or a new one (the stage creates its file). `title`: the title as the page shows it, replacing the canonical's. `members`: one or more other ids of the same document (one text, one issuer, one date), titles that chain in one group. `reason`: the evidence, one or two sentences. No other field; every id a lowercase slug.
- A member is in one group only, is never a canonical, agrees with the canonical and the other members on every field both set (`date`, `url`, `issuer` and the rest; a disagreement is settled by hand in the document files before folding), and is a document file or an id a telling or a manifest names; the canonical is in no group's members and is not an alias of another document.
- `pipeline/documents.py --fold` applies the groups (CLAUDE.md, Layout): afterwards no member id has a document file or stands where a document id goes (a telling's `document` or `documents`, a source manifest's `document.id`), the member's evidence text is part of the canonical's, and `check.py` refuses a member id left anywhere, a canonical without its file or without a member in its `aliases`, and a member held as an alias by another document.

## Episode (`data/episodes/<video id>.json`)

```json
{ "id": "dQw4w9WgXcQ", "show": "American Alchemy", "title": "...", "host": "jesse-michels", "guests": ["..."], "published": "2024-03-01", "url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "duration_s": 7420, "captions": "sources/captions/dQw4w9WgXcQ.en.vtt", "language": "en", "auto_captions": true }
```

An episode whose captions came from the Gemini fallback (`pipeline/gemini_captions.py`, for a video YouTube will not serve captions for) has `"captions": "sources/captions/<id>.en.txt"` (there is no .vtt), `"auto_captions": false`, `"captions_source": "gemini"` and `"timestamps_approximate"`: `true` when Gemini's time stamps overshot the duration and were rescaled to fit, so a time code may be some seconds off. Without `captions_source` the captions are YouTube's own.

## Document (`data/documents/<id>.json`)

```json
{ "id": "odni-uap-preliminary-2021", "title": "Preliminary Assessment: Unidentified Aerial Phenomena", "issuer": "Office of the Director of National Intelligence", "date": "2021-06-25", "url": "https://...", "kind": "official", "attests": ["144 reports examined, 143 unexplained"], "aliases": [] }
```

- `aliases` (optional, written by `pipeline/documents.py`): the ids folded into this document and the slugs of the fold's title and of every old title, none of them the document's own id, a document file of its own and none an alias of another document. `merge.py` and `sources.py` map a title slug or an id that is an alias to this document (`common.document_aliases`), so a folded id never comes back.

- `provenance` (optional): one sentence on where the document comes from and what is disputed about it ("An unsigned typescript left at the Nowhere Gazette in 1990; nobody has said who wrote it"), a non-empty string when present. Required on every document a story quotes only in a `source` note, with no telling of the story naming it (a note-only entry); `check.py` fails such a document without one. Filled by `pipeline/sources.py` from the manifest's `document.provenance`, never overwritten; `site/data.json` carries it in each story's `documents` block, which holds the documents a story's `source` notes quote beside those its tellings name or credit, so a document quoted note-only is in the block of the story it was quoted for; such a document makes no shared-document link between stories, which come from tellings only. `check.py` also fails a source note whose url names documents of different provenances.
- `status` (optional): `public-domain`, `in-copyright` or `unknown`, as the hosting site states it. `text_url` (optional): where the full text is read online. Both are filled by `pipeline/sources.py` when missing, never overwritten; `kind` gets the source's telling kind when null, and stays null for a document quoted only by note-only entries. The `title` is the one field the stage replaces: a title `merge.py` wrote from a teller's words (a stub such as "Einstein 1921 ether paper") gives way to the manifest's, and the stage prints each replacement.
- `sources/documents/<document id>.txt` is the document's evidence, the way a caption file is an episode's: for a document of status `public-domain` with a `text_url` the full text as fetched (plain text, a bracketed line such as `[Illustration]` part of the text), for every other document (in copyright, `unknown`, or with no status) only the quoted passages, one paragraph each after a line `[<locator>]`, no text before the first. The document's status and `text_url` decide which, never the file's lines. A document telling's `quote` must be a verbatim substring of it (`common.norm_quote` on both sides: whitespace collapsed, case and punctuation exact); in a passages file the quote lies inside the passage under its telling's `page`. `check.py` fails a document telling without the file, a file no document has and a file not in its document's format.

The manifest `pipeline/sources.py` reads (the scouts' findings) is a JSON list, one entry per story: `{ "story", "document": { "id" (an existing id or null), "title", "author", "issuer", "date", "url", "text_url", "status", "provenance" (optional) }, "text": { "url" (a plain-text URL the stage fetches, or null), "passages": [ { "locator", "text" } ] }, "quotes": [ { "quote", "locator" } ], "teller" (the author's name, or null for the document's author or issuer), "kind", "differs" (the source note's text, or null), "images": [ images.py manifest entries, the owner the story id or the teller's person id ], "note_only" (optional, `true`) }`. A note-only entry quotes a disputed or anonymous document beside the story without counting it as a telling: its `teller` and `kind` are null (the `kind` key still present), its `differs` is non-empty, and its document has a `provenance`, held already or given in the entry; the stage tests every entry before the first is ingested, so a manifest holding an entry without one is refused with nothing written. Its quotes are checked and its text file written as for any entry; it adds no telling and makes no person, so the story's attestation does not move, and its images are the story's only. `text` takes exactly one of a url or passages: a url only for a `public-domain` document with a `text_url`, passages for every other. A null `id` becomes the slug of the title, plus `-<year>` when that slug is another document (one with another url or year); a document with the same `url` or `text_url` is the same document.

## Eras and places

`data/eras.json` is a list of `{ "id", "name", "from", "to" }` with years; `data/places.json` a list of `{ "id", "name", "lat", "lon", "region" }`, with `"source": "lead to verify"` on a place whose coordinates or identity were set from memory and not yet checked. `data/place-aliases.json` is an object of alias text to place id (`"USS Nimitz": "pacific-nimitz"`); matching is case-insensitive on the whole text, else on the longest alias or place name the text contains as whole words. A story may name an era and a place by id, or carry its own `years` and `coordinates`; the page places a story by its era and place ids and by its raw years and coordinates where it has them.
