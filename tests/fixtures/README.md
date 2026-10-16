# Fixtures

Five tiny, entirely fictional episodes so the whole chain runs offline: `pipeline.check --fixture`
copies this folder to a temporary directory and runs extract (reading `answers/<id>.json` instead
of asking `claude -p`), merge, score, build and the checks on it. Nothing here is a real claim, a
real person, a real show or a real place; the video ids do not exist. `data/` holds the axes, the
five episodes, one document and one hand-written story (the one that contradicts a merged one);
`sources/captions/` the invented caption text; `answers/` the model answers as the prompt's schema
gives them, including one quote that is not verbatim and must be dropped, and one teller named with a role
("Bo Fixture (guest)") that must become the same person as "Bo Fixture".

`FIXTURE0001` and `FIXTURE0002` are the corpus as it stood before linking: they merge unlinked,
and `links/existing.json` holds the answers `link --existing` gets for their stories (Cy Fixture's
vault folds into Bo Fixture's as `same`, the harbour log's flare becomes a `variant` of the
lantern). `FIXTURE0003`, `FIXTURE0004` and `FIXTURE0005` arrive afterwards: each is extracted, then
all three are linked in one `link` run with the answers of `links/<id>.json` and merged. A links
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

The scored result covers every tier: the vault is `well-attested` (Cy and Eve, both firsthand, with
Bo's telling a repetition of Cy's), the plains hum is `told-by-several` (Dee as host and Eve as
researcher, no document and no firsthand), the rest are `told-once` (the ring with Gus Fixture's
telling a repetition of Fay Fixture's); the hand-written flare
`contradicts` the lantern, so both carry `contradicted: true`.

The hand-written flare also carries a two-entry `discussion` (a `debunk` by the fictional Nowhere
Gazette with a `source`, a `rebunk` by Bo Fixture with an `episode` and a `time`) and
`data/notes/the-lantern-was-a-flare-1958.json` holds one `open` and one `folded` viewer note:
`expect.json` asks for 2 discussion entries and `notes_open` 1 on that story in `site/data.json`,
and 0 and 0 on every other, so the discussion survives merge, `link --existing` and score and
reaches the page. A fold of two stories' discussions is checked in memory (`link.fold`). The group call is checked
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
