# Fixtures

Six tiny, entirely fictional episodes so the whole chain runs offline: `pipeline.check --fixture`
copies this folder to a temporary directory and runs extract (reading `answers/<id>.json` instead
of asking `claude -p`), link, merge, clips (reading `clips.json`), sources (reading `sources/manifest.json`), documents (applying `data/document-folds.json`), people (applying `data/person-folds.json`), score, explain, build and the checks on it. Nothing here is a real claim, a
real person, a real show or a real place; the video ids do not exist. `data/` holds the axes, the
six episodes, two documents (one log under two titles, which the document fold makes one) and one hand-written story (the one that contradicts a merged one);
`sources/captions/` the invented caption text; `answers/` the model answers as the prompt's schema
gives them, including one quote that is not verbatim and must be dropped, and one teller named with a role
("Bo Fixture (guest)") that must become the same person as "Bo Fixture".

`FIXTURE0001` and `FIXTURE0002` are the corpus as it stood before linking: they merge unlinked,
and `links/existing.json` holds the answers `link --existing` gets for their stories (Cy Fixture's
vault folds into Bo Fixture's as `same`, the harbour log's flare becomes a `variant` of the
lantern). `FIXTURE0003` to `FIXTURE0006` arrive afterwards: each is extracted, then
all four are linked in one `link` run with the answers of `links/<id>.json` and merged. A links
file is a list of groups as one call at `--batch 10` sees them (`episode`, the `candidates` asked by
title in order, and `decisions`, one per candidate numbered from 1, every one with its `grain`);
each of these episodes has three candidates or fewer, so each is one group. `links/existing.json`
gives each story's answer as a group of one (`{"decisions": [...]}` by story id). FIXTURE0003 has two `same` and one `variant`; its
vault telling, dated 1972, joins the 1971 vault and keeps `as_told.years` 1972. FIXTURE0004 tells
a new story (the ring in the ice of Lake Placeholder) that FIXTURE0005 tells again in the same run,
`same` as the provisional story, so it ends as one story; it also tells one incident inside the
vault program, answered `same` at grain `narrower`, and a testimony about the vault crew, answered
`same` at grain `same` against the program: both are downgraded to `new` and listed under
`downgraded` in `data/links.json`. Every prepared answer must be asked for, and a second run must
ask nothing.

`FIXTURE0006` is the replayed clip. Its host plays a clip of Fay Fixture from `FIXTURE0004` (the
ring in the ice, a `>>` before and after it, introduced as "here is what fay fixture told this
show") to her guest Hal Fixture, and the prepared extraction credits the clip's words to Hal; `link` joins it to the
ring as `same`. Before the clips stage the ring would have two independent first-hand tellers and
be `well-attested`. `clips` finds the 16 shared words as one group (`FIXTURE0004-8`), `clips.json`
answers it `clip`, spoken by `fay-fixture`, origin `#1` (FIXTURE0004), and the stage gives Hal's
telling `replay_of` FIXTURE0004 at 8 s, `teller` `fay-fixture` and `teller_was` `hal-fixture`; the
ring ends with one independent teller (`tellers` in expect.json), `told-once`. `expect.json` names
the ledger's verdict under `clips` and the marked telling under `replays`. The check also marks the
group `not-a-clip` by hand and applies (Hal's telling must come back unmarked), puts the ledger back
and applies again (the story must be byte for byte as before). `check.clips_refusal_problems` runs
`clips.Asker` with a fake model whose origin `#9` names no occurrence: the refused answer is asked
once more with a note naming the refusal and the second answer is taken, and a model that refuses
twice stops the run. `check.replay_weight_problems` scores, in memory with `score.attest`, a
first-hand replay beside the speaker's own second-hand telling, which must count one second-hand
teller and no first-hand one, and the replay alone, whose speaker must then count as one first-hand
teller by the replay's kind.

The scored result covers every tier: the vault is `well-attested` (Cy and Eve, both firsthand, with
Bo's telling a repetition of Cy's), and so is the mirror once its source is read (below), the plains hum is `told-by-several` (Dee as host and Eve as
researcher, no document and no firsthand), the rest are `told-once` (the ring with Gus Fixture's
telling a repetition of Fay Fixture's and the replayed clip hers); the hand-written flare
`contradicts` the lantern, so both carry `contradicted: true`.

The hand-written flare also carries a two-entry `discussion` (a `debunk` by the fictional Nowhere
Gazette with a `source`, a `rebunk` by Bo Fixture with an `episode` and a `time`) and
`data/notes/the-lantern-was-a-flare-1958.json` holds one `open` and one `folded` viewer note:
`expect.json` asks for 2 discussion entries and `notes_open` 1 on that story in `site/data.json`,
and 0 and 0 on every other, so the discussion survives merge, `link --existing` and score and
reaches the page. `check.fold_discussion_problems` folds stories in memory with `link.fold`: a
folded story's two entries are appended after the survivor's one, in order and none dropped, and a
survivor without a discussion takes the folded story's entry. The group call is checked
on a tiny root of its own with a fake model (`check.link_group_problems`), since the fixture's
decisions name no earlier candidate: `#1` resolves to an earlier candidate's provisional story, `#n`
of a candidate that joined a held story resolves to that story, a `narrower` `same` through `#n` is
downgraded naming the real id, a refused answer is asked once more with a note, a second refusal
stops the run, and a run killed after its first group resumes with the rest.

The captions also carry the shapes real auto-captions have: FIXTURE0001 opens on a trailer that
repeats a line of the body (the quote must take the body's time code, the one nearest the answer's
`from_s`), FIXTURE0002 has a `[laughter]` and a `>>` inside quotes the answers leave out, and
FIXTURE0003 has both inside a quote the answer copies with them. `data/person-aliases.json` folds
the answer's "Beau Fixture" into `bo-fixture`. `expect.json` holds what the chain must produce for
these (time codes, people that must not exist; under `stories` every story's tier, `contradicted`
flag and attestation, and for the vault its aliases, the tellings that carry a `difference` and the
`as_told` years; the downgraded candidates; "Beau Fixture" resolving to `bo-fixture` against this
root and to `beau-fixture` against the repo's), and the host and guests `captions.host_and_guests`
must take from a set of invented titles.

Two images ride along, both drawn stand-ins a few hundred bytes to a kilobyte in size: a
`place-then` photograph of Mount Fictus filed under the vault's alias id
(`data/images/the-vault-beneath-mount-fictus-1971/1.json`, `site/images/.../1.jpg`), which
`site/data.json` must show on the surviving vault story, and a free `headshot` of Bo Fixture
(`data/images/bo-fixture/1.json`, a PNG with transparency), which must be Bo Fixture's `image` while
every other person's is null. The fixture has no `bad/` folder, so the refusals are written into the
temporary copy one at a time and removed again (`check.image_refusal_problems`): a fair-use
headshot, a headshot as a story's picture, an object owned by a person, an owner that is nothing, an
unknown field, a missing licence, a source that is not http(s), a missing file, a file that is no
image, a file at another path, a fair-use image above 480 px and a file no sidecar claims must each
be named. `check.image_ingest_problems` runs `images.ingest` offline with a downloader that serves
the fixture's JPEG: a new image lands under the story id with its sidecar, an image URL the alias
directory holds is kept, a second run fetches nothing, a failed download stops the run or is listed
under `keep_going`, and a bad manifest is refused before anything is fetched.

`sources/` holds the primary-source case. Bo Fixture tells the lanterns as a mirror in his own
words; `sources/manifest.json` is a scout's entry for it: the fictional public-domain pamphlet *The
Lanterns of Nowhere* (1956) by Ivo Fixture, its plain text served from `sources/served/` by a
downloader that reads the file (`check.SourceFetch`; its `[Illustration]` line is plain text, since a
public-domain document with a text_url keeps its full text and is never read as passages), one quote under the locator `I`, a note that
the pamphlet already had the idea, and two pictures (the title page, Ivo's headshot). The stage runs
after clips and before the person fold: the mirror gains Ivo's first-hand document telling, a `source` note and the document,
so it ends `well-attested` with two independent tellers. Bo's prepared answer `cites` "Ivo Fixture": this is the
cited-source case, an expectation in `expect.json` (the mirror's tier, attestation and `tellers`, Bo and Ivo)
rather than a `*_problems` function, and it proves that citing a source is not repeating it: Ivo tells the mirror
only through the document telling, so Bo's cite is no edge and Bo stays independent (read as a repetition, the
mirror would be `told-once` with Ivo alone). The vault is the other half: Bo cites Cy, who tells the vault in an
episode, so Bo stays a repetition there and the vault's attestation stays 2.0 (Cy and Eve). The page shows the
same split: `repeats` in expect.json is each telling's `repeats` in site/data.json, Cy on Bo's vault telling and
nobody on the mirror, where Bo's cite of Ivo is shown as a cite. `check.cite_edges_problems` proves, in memory,
that the edges score and build share (`score.cite_edges`) keep a host's cite of an episode teller and drop the
same host's cite of a source's author, so the host repeats the witness alone. `check.document_telling_cites_problems`
proves that check reports a document telling with `cites` (the source's own words cite nobody; a cite there
would make the author the repetition of the citer) and passes one with empty or absent cites. `sources/documents/` gains the pamphlet's
text beside the harbour log's (the flare's document telling, which check holds to it), and
`sources/manifest.images.json` the two pictures, which `images.manifest_problems` must accept.
`expect.json` names all of it under `sources`, with the lines explain sends the model for the mirror
(the document with its locator, the source note). A second run must fetch nothing and change
nothing. `check.source_ingest_problems` works on a copy of the finished root: a book in copyright as
passages under `[chapter 2]` and, from a second entry, `[chapter 5]`, told by its author as
researcher; a second book of the same title with another url and year, which becomes `-2010`; a
wrong locator, a quote that is not verbatim, a failed fetch of a public-domain text and a full text
for a document of unknown status, each refused with nothing written; `keep_going` listing the failed
fetch; a fetched full text for a book in copyright refused with the manifest; a notice whose author
is null, told by its issuer (the Harbour Board, a person of role official) in tellings of kind
`official` although the entry says `researcher`, on a document whose stub title the manifest's
replaces with a `title` line printed; and the check naming a missing text file, a quote under another
chapter than its page, a text file no document has and the pamphlet's full text once its status is
`unknown`.

The person fold is one fictional guest under three spellings across two episodes. In FIXTURE0004
the extraction credits the vault-crew telling to "Faye Fixture", citing "Fay Fixture"; in FIXTURE0005
Gus Fixture cites her as "Fae Fixture"; `clips.json` names the replayed clip's speaker "Faye Fixture"
with "Fay Fixture" also heard; and her headshot is filed under `faye-fixture`
(`data/images/faye-fixture/1.json`, `site/images/faye-fixture/1.png`). Unfolded, the ring would have
three independent tellers and be `well-attested`. `data/person-folds.json` folds `faye-fixture` and
`fae-fixture` into `fay-fixture`: the crew telling's self-cite goes (its `cites` in expect.json),
Gus's telling becomes a repetition, the clip's speaker is `fay-fixture` with nobody else heard, the
headshot is `images/fay-fixture/1.png`, both member files are gone (`absent_people`), `fay-fixture`
carries both as `aliases` in its file and in site/data.json (`people_fold`), and "Faye Fixture" and
"fae-fixture" resolve to `fay-fixture` against this root (`person_ids`). A second fold changes
nothing. The refusals run on a tiny root of their own (`check.person_fold_refusal_problems`): a
file that is a bare list of groups, a malformed group, a member in two groups, a member that is
another group's canonical, a member named nowhere, a malformed `distinct` pair, a distinct id that a
group folds and a distinct id that is no person are each named before anything is written, and a
fold into a new canonical creates it (a `distinct` pair may name it), merges roles, links and
affiliation, drops a self-cite, moves a headshot to the next free number, drops one whose image URL
the canonical holds, and maps a member's old alias, name and id. `data/person-folds.json` also lists
`bo-fixture` and `fay-fixture` as `distinct`, so the chain's check validates a pair against the
people the fold leaves.

The document fold is one fictional log under two titles. The harbour log is held as
`harbour-log-of-nowhere-1958` (page 3 in its passages) and as `nowhere-harbour-log`
(`data/documents/nowhere-harbour-log.json` with a url of its own and the same date, page 4 in
`sources/documents/nowhere-harbour-log.txt`): the flare quotes one page under each id, and the lantern's
extraction credits both titles in one telling. Unfolded, the lantern counts two credited documents and
the flare two document tellings, both above their `attestation` in expect.json. `data/document-folds.json`
folds the short id into the full one, which runs after sources and before the person fold: under
`documents_fold` in expect.json the member's file and text are gone, the canonical keeps its date, takes the
member's url and attests and carries it as an alias, its text holds both passages under `[3]` and `[4]`, and
both stories name only the canonical (no telling credits it twice); merge, run again in the second pass, must
not bring the member back, and a second fold changes nothing. `check.document_fold_problems` (inside the check
of every root) fails a member id left anywhere, a canonical without its file or without a member in its aliases,
an alias that is a document or claimed twice, and a member held as an alias by a document other than its canonical. The refusals run on a tiny root of their own (`check.document_fold_refusal_problems`): a
malformed group, a canonical of 61 characters, a canonical in two groups, a member in two groups, a member that is
another group's canonical, a member named nowhere, two members that give different dates, a group title whose slug is
another document, a canonical or a member an earlier fold put into another document, text files of two formats, two full texts
that differ, a passages text beside a member that makes the document a public-domain full text, and two
tellings that would become one are each named before anything is written; a fold then merges two passages
texts and drops the passage they share, renames a lone member's text to a new canonical, rewrites a manifest's
document id and leaves its images manifest alone, credits a telling's members once, and merge and sources
resolve a folded title, the group's own title or an id to the canonical; with a member taken out of its canonical's
aliases the whole-root check names it.

`check.near_duplicate_problems` runs the near-duplicate warning on a fixed list of ids: of `greg`,
`greg-malatzi`, `greg-malazzi`, `james-fox`, `james-woods`, `bob-jameson`, `robert-jameson` and
`donald-trump` it must pair only `greg-malatzi` with `greg-malazzi`, the two spellings of one name,
and leave the short id and the distinct names alone; with `scott-kelly`, `scott-pelley`, `shane-ryan`
and `shawn-ryan` added, a group folding the Greg spellings and a `distinct` pair given in the other
order, `check.warned_pairs` must leave only `shane-ryan` with `shawn-ryan`.

`explain.json` stands in for the explain stage: the plain telling for each of the eight stories the
chain makes, keyed by story id. The flare story carries a hand-written `plain` with `plain_by:
"hand"` and is in no answer: the chain must never ask for it or change it. Every story in
site/data.json must carry the `plain` the file gives it, or its own hand-written one, and a second
explain run must ask nothing. `check.explain_answer_problems` proves, with a fake model, that an answered id that spells out the asked
id's truncated last word or drops its `-<year>` suffix is saved under the asked id, that an id none or two
asked ids begin is refused and asked once more with a note, and that a second refusal stops the run.
`check.explain_shard_problems` proves `explain --shard`: on a copy with
the stage's plain tellings removed, `--shard 1/2` then `--shard 2/2` in groups of two explain the
untold stories among every other one of the ordered list, from the first and from the second, the
two sets disjoint and together giving every story the telling the full run gave it, and a malformed
shard (`0/2`, `3/2`, `1`, `a/b`) is refused. `check.retired_summary_problems` proves that check
refuses, by name, a story file that still carries the retired `summary` field, and
`check.stale_build_problems` that it refuses a story in site/data.json whose keys are not the set
`build.STORY_KEYS` names (a stale build still carrying `summary`).
