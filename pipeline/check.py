"""Keep the data honest.

    uv run python -m pipeline.check [--root DIR]
    uv run python -m pipeline.check --fixture

Every story has at least one telling; every episode, document, person, era, place and related
story id resolves; every quote with an episode is a verbatim substring of that episode's caption
text (time codes stripped, whitespace collapsed, otherwise exact); kinds and relations are from the
schema; `score` is absent, null or numeric; every alias belongs to one story and is no story's id; `plain`, when present, is a non-empty string
and `plain_by` is absent or "hand" beside a `plain`;
every candidate `link` names a story or an alias; every telling a `same` link added carries a
`link_reason`, and so does every telling with a `difference`; every target of
data/person-aliases.json has a person file or is the id of a name a candidate gives (merge creates
it), is no alias itself, and no alias is the id of a different person; every `discussion` entry has
a known `kind`, a `by` and a `text`, a `source` that is an http(s) URL or an `episode` in
data/episodes with an h:mm:ss `time`, and only the schema's fields (role and date from their lists
and formats); every data/notes/<id>.json names a story or an alias and holds entries with `by`,
`date`, `text` and a `status` of open, folded or dropped; every image sidecar under data/images is
well formed, its owner a story, an alias or a person, its kind fitting the owner, no headshot fair
use, its file the JPEG or PNG it names under site/ within the size its licence allows, and every file
under site/images has a sidecar (`images.problems`); data/clips.json, when present, is well formed
(`clips.ledger_problems`), and a telling that carries `replay_of` or `teller_was` is exactly what the
ledger makes of it (`replay_of` an episode in data/episodes or `{"outside": true}`, inside an
occurrence of a `clip` group, `teller_was` a person). A telling without either mark is not held to
the ledger, so the check passes between judging and applying. Every document telling has its
text file under sources/documents, its quote a verbatim substring of it (inside the passage its
`page` names when the file holds passages), every document's `status` and `text_url` are well
formed and every text file there is a document's and in its format: a full text only for a
public-domain document with a text_url, [locator] passages for every other (`sources.problems`).
The page's own `DISCUSSION_KINDS` in site/js/model.js equals common.DISCUSSION_KINDS. Prints every problem, naming the
story and the entry, and exits 1 when there is one. Then it lists, as warnings that never fail the
check, the pairs of person ids of eight letters or more (hyphens dropped) within two edits of each
other ("greg-malatzi" and "greg-malazzi"): usually one person under two spellings, to fold by hand
through data/person-aliases.json.

--fixture copies tests/fixtures/ to a temporary directory and runs the chain with the prepared
answers, no `claude -p` (`explain.json` stands in for the explain stage): the episodes without a `links/<id>.json` are extracted and merged unlinked
(the corpus as it stood before linking), `link --existing` folds and relates their stories with
`links/existing.json`, then the episodes with a links file are extracted, linked in one run (so
one can join a story another creates; each episode's candidates in groups of ten, one prepared
answer per group) and merged; clips (judged with `clips.json`), sources (`sources/manifest.json`, its
text served from `sources/served/`), score, explain (every story without a hand-written `plain`) and build follow. It checks the result and that every prepared link and clips answer was asked for, then
runs both link modes, merge, clips, sources, score and explain again and verifies that nothing was asked and nothing
changed. Last it checks `tests/fixtures/expect.json`: the time codes given candidates must have
(the nearest of two occurrences, quotes across a `>>` or a bracketed tag), the people that must not
exist (a spelling the person aliases fold), the host and guests `captions.host_and_guests` must take
from each title, that `captions --refill` fills only host and guests, and that the extraction
prompt carries the episode's title and date lines; then every story the chain made, with its tier,
`contradicted` flag and attestation (and for some its years, aliases, episodes, the tellings that
carry a `difference` and a telling's `as_told`), every story's `discussion` length and `notes_open`
in site/data.json (0 when expect.json gives none), that site/plain.json carries for every story in
site/data.json the `plain` telling `explain.json` gives it, or its own hand-written one (the stories `plain_by_hand`
lists, which keep `plain_by`), that `link.fold` appends a folded story's
discussion to the survivor's in order, that a group call of `link` resolves `#n` to the story an
earlier telling of the group ends in, asks a refused group once more with a note, stops on a
second refusal and resumes after a killed run, the candidates `link` downgraded, and one name
resolved against the fixture's person aliases and the repo's, which must differ. For the clips
stage: the ledger's verdicts (`clips`), the tellings that must carry `replay_of` and `teller_was`
(`replays`) and a story's independent tellers (`tellers`); that a hand-marked `not-a-clip` restores
the teller and a second apply puts it back; and, with a fake model, that a refused clips answer is
asked once more with a note and a second refusal stops the run; that a first-hand replay never
lifts a speaker whose own telling is second-hand; and which person ids the near-duplicate warning pairs. For the sources stage: the documents,
text files, tellings, source notes and images manifest under `sources`, the lines explain sends
the model, and on a copy of the root the passages path, the slug rule and every refusal
(`source_ingest_problems`).
"""
from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

import json

from . import clips, images, sources
from .common import (DATE, DISCUSSION_KEYS, DISCUSSION_KINDS, DISCUSSION_ROLES, HTTP, NOTE_KEYS, REPO, RELATIONS,
                     STORY_KINDS, TELLING_KINDS, Captions, Root, load_json, norm_ws, person_aliases, person_id, rel, save_json, seconds, text_field)

FIXTURES = REPO / "tests" / "fixtures"


MODEL_JS = REPO / "site" / "js" / "model.js"


def page_kinds_problems() -> list[str]:
    """The page's own list of discussion kinds (site/js/model.js `DISCUSSION_KINDS`) equals
    common.DISCUSSION_KINDS, or the page refuses a story whose entry the data allows."""
    m = re.search(r"const DISCUSSION_KINDS = \[([^\]]*)\];", MODEL_JS.read_text(encoding="utf-8"))
    if m is None:
        return [f"{rel(MODEL_JS, REPO)}: no `const DISCUSSION_KINDS = [...];` to compare with common.DISCUSSION_KINDS"]
    page = tuple(json.loads(f"[{m.group(1)}]"))
    if page != DISCUSSION_KINDS:
        return [f"{rel(MODEL_JS, REPO)}: DISCUSSION_KINDS is {list(page)}, common.DISCUSSION_KINDS is {list(DISCUSSION_KINDS)}"]
    return []


def discussion_problems(where: str, entries, episodes: dict) -> list[str]:
    """A story's `discussion`: a list of entries with kind, by and text, and a source URL or an episode with a time."""
    if not isinstance(entries, list):
        return [f"{where}: discussion must be a list"]
    out: list[str] = []
    for i, e in enumerate(entries):
        ew = f"{where} discussion entry {i + 1}"
        if not isinstance(e, dict):
            out.append(f"{ew}: must be an object")
            continue
        for k in sorted(set(e) - set(DISCUSSION_KEYS)):
            out.append(f"{ew}: unknown field {k!r} (the fields are {', '.join(DISCUSSION_KEYS)})")
        if e.get("kind") not in DISCUSSION_KINDS:
            out.append(f"{ew}: kind {e.get('kind')!r} is not one of {', '.join(DISCUSSION_KINDS)}")
        for k in ("by", "text"):
            if not text_field(e.get(k)):
                out.append(f"{ew}: {k} must be a non-empty string")
        if "role" in e and e["role"] not in DISCUSSION_ROLES:
            out.append(f"{ew}: role {e['role']!r} is not one of {', '.join(DISCUSSION_ROLES)}")
        if "date" in e and not (isinstance(e["date"], str) and DATE.fullmatch(e["date"])):
            out.append(f"{ew}: date {e['date']!r} is not YYYY, YYYY-MM or YYYY-MM-DD")
        if "source" in e and not (isinstance(e["source"], str) and HTTP.fullmatch(e["source"])):
            out.append(f"{ew}: source {e['source']!r} is not an http(s) URL")
        if ("episode" in e) != ("time" in e):
            out.append(f"{ew}: episode and time come together")
        if "episode" in e and e["episode"] not in episodes:
            out.append(f"{ew}: episode {e['episode']!r} is not in data/episodes")
        if "time" in e:
            try:
                seconds(e["time"])
            except SystemExit as x:
                out.append(f"{ew}: {x}")
        if "source" not in e and not ("episode" in e and "time" in e):
            out.append(f"{ew}: needs a source, or an episode and a time")
    return out


def notes_problems(root: Root, stories: dict, owner: dict[str, str]) -> list[str]:
    """data/notes/<story id>.json: `Root.load_notes` checks the shape and the status; here the story (or an alias of
    one) exists and every entry has by, date and text."""
    try:
        notes = root.load_notes()
    except SystemExit as e:
        return [str(e)]
    out: list[str] = []
    for key, entries in sorted(notes.items()):
        where = f"data/notes/{key}.json"
        if key not in stories and key not in owner:
            out.append(f"{where}: {key!r} is no story id or alias")
        for i, e in enumerate(entries):
            ew = f"{where} entry {i + 1}"
            for k in sorted(set(e) - set(NOTE_KEYS)):
                out.append(f"{ew}: unknown field {k!r} (the fields are {', '.join(NOTE_KEYS)})")
            for k in ("by", "text"):
                if not text_field(e.get(k)):
                    out.append(f"{ew}: {k} must be a non-empty string")
            if not (isinstance(e.get("date"), str) and DATE.fullmatch(e["date"])):
                out.append(f"{ew}: date {e.get('date')!r} is not YYYY, YYYY-MM or YYYY-MM-DD")
    return out


def problems(root: Root) -> list[str]:
    out: list[str] = []
    try:
        stories, people, episodes, documents = (root.load_dir(d) for d in (root.stories, root.people, root.episodes, root.documents))
        eras, places = root.eras(), root.places()
    except SystemExit as e:
        return [str(e)]
    era_ids = {e["id"] for e in eras}
    place_ids = {p["id"] for p in places}
    caps: dict[str, Captions] = {}
    try:
        owner = root.story_aliases(stories)
    except SystemExit as e:
        return [str(e)]
    try:
        aliases = person_aliases(root.path)
    except SystemExit as e:
        out.append(str(e))
        aliases = {}
    clip_groups: list = []
    if (root.data / "clips.json").exists():
        try:
            ledger = load_json(root.data / "clips.json")
            bad = clips.ledger_problems(ledger, episodes)
            out += bad
            if not bad:
                clip_groups = ledger["groups"]
        except SystemExit as e:
            out.append(str(e))
    named: set[str] = set()  # the person ids the candidates' names resolve to (merge creates each)
    for f in sorted(root.candidates.glob("*.json")) if root.candidates.exists() else []:
        try:
            batch = load_json(f)
        except SystemExit as e:
            out.append(str(e))
            continue
        for c in batch.get("candidates", []):
            for n in [c.get("teller")] + list(c.get("cites") or []):
                if isinstance(n, str) and n.strip():
                    named.add(person_id(n, aliases))
        for c in batch.get("candidates", []):
            link = c.get("link")
            if link is None:
                continue
            where = f"{rel(f, root.path)}: {c.get('title')!r}"
            if link.get("decision") not in ("same", "variant", "new"):
                out.append(f"{where}: link decision {link.get('decision')!r} is not same, variant or new")
                continue
            if link["decision"] == "new":
                continue
            target = link.get("story") if link.get("story") in stories else owner.get(link.get("story"))
            if target is None:
                out.append(f"{where}: linked {link['decision']} to {link.get('story')!r}, which is no story or alias")
                continue
            if link["decision"] == "same":
                for t in stories[target]["tellings"]:
                    if t.get("episode") == batch.get("episode") and norm_ws(t.get("quote") or "") == norm_ws(c.get("quote") or "") \
                            and not (t.get("link_reason") or "").strip():
                        out.append(f"{where}: the telling its same link added to {target} has no link_reason")
    out += alias_problems(aliases, people, named)
    for sid, s in sorted(stories.items()):
        where = f"story {sid}"
        for key in ("id", "title", "summary", "tellings", "related"):
            if key not in s:
                out.append(f"{where}: missing {key}")
        if not s.get("tellings"):
            out.append(f"{where}: no telling (a story without a quote is a note, not a story)")
        if s.get("era") is not None and s["era"] not in era_ids:
            out.append(f"{where}: era {s['era']!r} is not in eras.json")
        if s.get("place") is not None and s["place"] not in place_ids:
            out.append(f"{where}: place {s['place']!r} is not in places.json")
        if s.get("place_text") is not None and not isinstance(s["place_text"], str):
            out.append(f"{where}: place_text must be a string or null")
        if s.get("kind") is not None and s["kind"] not in STORY_KINDS:
            out.append(f"{where}: kind {s['kind']!r} is not a story kind")
        y = s.get("years")
        if y is not None:
            if not isinstance(y, dict) or not all(isinstance(y.get(k), int) for k in ("from", "to")):
                out.append(f"{where}: years must be {{from, to}} integers or null")
            elif y["from"] > y["to"]:
                out.append(f"{where}: years from {y['from']} is after to {y['to']}")
            elif s.get("era") is not None:
                era = next(e for e in eras if e["id"] == s["era"]) if s["era"] in era_ids else None
                if era and not (era["from"] <= y["from"] <= era["to"]):
                    out.append(f"{where}: era {s['era']} does not hold {y['from']}")
        if "score" in s and s["score"] is not None and (isinstance(s["score"], bool) or not isinstance(s["score"], (int, float))):
            out.append(f"{where}: score must be absent, null or numeric")
        if "plain" in s and (not isinstance(s["plain"], str) or not s["plain"].strip()):
            out.append(f"{where}: plain must be a non-empty string when present")
        if "plain_by" in s:
            if s["plain_by"] != "hand":
                out.append(f"{where}: plain_by must be \"hand\" when present, got {s['plain_by']!r}")
            if "plain" not in s:
                out.append(f"{where}: plain_by without a plain telling")
        for i, t in enumerate(s.get("tellings") or []):
            tw = f"{where} telling {i + 1}"
            ep, doc = t.get("episode"), t.get("document")
            if bool(ep) == bool(doc):
                out.append(f"{tw}: needs exactly one of episode or document")
            if t.get("teller") not in people:
                out.append(f"{tw}: teller {t.get('teller')!r} is not in data/people")
            if t.get("kind") not in TELLING_KINDS:
                out.append(f"{tw}: kind {t.get('kind')!r} is not a telling kind")
            for c in t.get("cites", []):
                if c not in people:
                    out.append(f"{tw}: cites {c!r}, not in data/people")
            for d in t.get("documents", []):
                if d not in documents:
                    out.append(f"{tw}: credits document {d!r}, not in data/documents")
            if doc and doc not in documents:
                out.append(f"{tw}: document {doc!r} is not in data/documents")
            if not (t.get("quote") or "").strip():
                out.append(f"{tw}: no quote")
            if "difference" in t and not (t.get("link_reason") or "").strip():
                out.append(f"{tw}: has a difference but no link_reason")
            if "replay_of" in t or "teller_was" in t:
                out += replay_problems(tw, t, episodes, people, clip_groups)
            if ep:
                if ep not in episodes:
                    out.append(f"{tw}: episode {ep!r} is not in data/episodes")
                    continue
                if not isinstance(t.get("from_s"), (int, float)):
                    out.append(f"{tw}: from_s must be seconds")
                if ep not in caps:
                    try:
                        caps[ep] = Captions(root.caption_text(episodes[ep]))
                    except SystemExit as e:
                        out.append(f"{tw}: {e}")
                        continue
                if t.get("quote") and not caps[ep].contains(t["quote"]):
                    out.append(f"{tw}: quote is not a verbatim substring of {ep}'s caption text: {t['quote'][:60]!r}")
        if "discussion" in s:
            out += discussion_problems(where, s["discussion"], episodes)
        for r in s.get("related") or []:
            if r.get("story") not in stories:
                out.append(f"{where}: related story {r.get('story')!r} does not exist")
            if r.get("relation") not in RELATIONS:
                out.append(f"{where}: relation {r.get('relation')!r} is not one of {RELATIONS}")
    out += notes_problems(root, stories, owner)
    out += images.problems(root, stories, owner, people)
    out += sources.problems(root, stories, documents)
    out += page_kinds_problems()
    for eid, e in episodes.items():
        if e.get("captions") and not (root.path / e["captions"]).exists():
            out.append(f"episode {eid}: captions file {e['captions']} is missing")
        if e.get("captions_source") not in (None, "gemini"):
            out.append(f"episode {eid}: captions_source {e['captions_source']!r} is not gemini or absent")
        if e.get("captions_source") == "gemini" and not isinstance(e.get("timestamps_approximate"), bool):
            out.append(f"episode {eid}: a gemini episode needs timestamps_approximate true or false")
    return out


def replay_problems(tw: str, t: dict, episodes: dict, people: dict, groups: list) -> list[str]:
    """A telling marked by the clips stage: `replay_of` names an episode (or is `{"outside": true}`),
    `teller_was` a person, and both are what data/clips.json makes of the telling."""
    if not t.get("episode"):
        return [f"{tw}: replay_of or teller_was on a telling without an episode"]
    out: list[str] = []
    r = t.get("replay_of")
    if "replay_of" in t and r != {"outside": True}:
        if not (isinstance(r, dict) and set(r) == {"episode", "from_s"} and isinstance(r["from_s"], (int, float))):
            out.append(f"{tw}: replay_of {r!r} must be {{episode, from_s}} or {{\"outside\": true}}")
        elif r["episode"] not in episodes:
            out.append(f"{tw}: replay_of episode {r['episode']!r} is not in data/episodes")
    if "teller_was" in t and t["teller_was"] not in people:
        out.append(f"{tw}: teller_was {t['teller_was']!r} is not in data/people")
    if not out and clips.corrected(t, groups) != t:
        out.append(f"{tw}: replay_of and teller_was are not what data/clips.json makes of this telling "
                   f"(no clip group covers it, or its speaker or origin differ): run pipeline.clips")
    return out


def alias_problems(aliases: dict[str, str], people: dict, named: set[str]) -> list[str]:
    out: list[str] = []
    for key, pid in sorted(aliases.items()):
        where = f"person-aliases.json: {key!r} -> {pid!r}"
        if pid not in people and pid not in named:
            out.append(f"{where}: the target has no person file and no candidate names it")
        if pid in aliases:
            out.append(f"{where}: the target is itself an alias (of {aliases[pid]!r}); point at the final id")
        if key in people and key != pid:
            out.append(f"{where}: the alias is the id of another person (data/people/{key}.json); fold that file into {pid}")
    return out


def expectations(root: Root) -> list[str]:
    """The fixture's expect.json against the chain's result and the extraction helpers."""
    from . import captions, extract
    f = root.path / "expect.json"
    if not f.exists():
        return [f"fixture has no {f.name}"]
    exp, out = load_json(f), []
    for e in exp.get("times", []):
        batch = load_json(root.candidates / f"{e['episode']}.json")
        hits = [c for c in batch["candidates"] if c["title"] == e["title"]]
        if not hits:
            out.append(f"expect: {e['episode']} {e['title']!r} was not kept (dropped: {[d['title'] for d in batch['dropped']]})")
        elif hits[0]["from_s"] != e["from_s"]:
            out.append(f"expect: {e['episode']} {e['title']!r} at {hits[0]['from_s']}s, expected {e['from_s']}s")
    for pid in exp.get("absent_people", []):
        if (root.people / f"{pid}.json").exists():
            out.append(f"expect: data/people/{pid}.json exists; the person aliases should have folded it")
    for e in exp.get("titles", []):
        got = captions.host_and_guests(e["show"], e["title"])
        if got != (e["host"], e["guests"]):
            out.append(f"expect: host_and_guests({e['show']!r}, {e['title']!r}) gave {got}, expected {(e['host'], e['guests'])}")
    eps = root.path / "refill-episodes"
    eps.mkdir()
    before = {"id": "FIXTUREREFL", "show": "American Alchemy", "title": "A made up title (Ft. Bo Fixture)",
              "host": None, "guests": [], "captions": "untouched", "published": "2026-01-04"}
    (eps / "FIXTUREREFL.json").write_text(json.dumps(before), encoding="utf-8")
    changed = captions.refill(eps)
    after = load_json(eps / "FIXTUREREFL.json")
    if len(changed) != 1 or after != {**before, "host": "jesse-michels", "guests": ["Bo Fixture"]}:
        out.append(f"expect: captions.refill changed {len(changed)} file(s) and wrote {after}")
    if captions.refill(eps):
        out.append("expect: a second captions.refill changed a file")
    stories = root.load_dir(root.stories)
    want = exp.get("stories", {})
    for sid in sorted(set(stories) ^ set(want)):
        out.append(f"expect: story {sid} {'exists but is not' if sid in stories else 'is missing, though it is'} in expect.json")
    for sid, e in sorted(want.items()):
        s = stories.get(sid)
        if s is None:
            continue
        got = {"tier": s.get("tier"), "contradicted": (s.get("profile") or {}).get("contradicted"), "attestation": s.get("attestation")}
        if got != {k: e[k] for k in got}:
            out.append(f"expect: story {sid} has {got}, expected {({k: e[k] for k in got})}")
        if "tellers" in e and (s.get("profile") or {}).get("tellers") != e["tellers"]:
            out.append(f"expect: story {sid} has independent tellers {(s.get('profile') or {}).get('tellers')}, expected {e['tellers']}")
        if "years" in e and s.get("years") != e["years"]:
            out.append(f"expect: story {sid} has years {s.get('years')}, expected {e['years']}")
        if "aliases" in e and sorted(s.get("aliases", [])) != sorted(e["aliases"]):
            out.append(f"expect: story {sid} has aliases {s.get('aliases', [])}, expected {e['aliases']}")
        told_in = sorted({t["episode"] for t in s["tellings"] if t.get("episode")})
        if "episodes" in e and told_in != e["episodes"]:
            out.append(f"expect: story {sid} is told in {told_in}, expected {e['episodes']}")
        if "difference_tellings" in e:
            idx = [i for i, t in enumerate(s["tellings"]) if (t.get("difference") or "").strip()]
            if idx != e["difference_tellings"]:
                out.append(f"expect: story {sid}: the tellings with a difference are {idx}, expected {e['difference_tellings']}")
        for eid, fields in e.get("as_told", {}).items():
            told = next((t.get("as_told") or {} for t in s["tellings"] if t.get("episode") == eid), {})
            for k, v in fields.items():
                if told.get(k) != v:
                    out.append(f"expect: story {sid}: the telling from {eid} has as_told {k} {told.get(k)!r}, expected {v!r}")
    built = {s["id"]: s for s in load_json(root.site / "data.json")["stories"]}
    for sid, e in sorted(want.items()):
        b = built.get(sid)
        if b is None:
            out.append(f"expect: story {sid} is not in site/data.json")
            continue
        if not isinstance(b.get("discussion"), list) or not isinstance(b.get("notes_open"), int):
            out.append(f"expect: story {sid} in site/data.json lacks a discussion list or a notes_open count")
            continue
        if len(b["discussion"]) != e.get("discussion", 0):
            out.append(f"expect: story {sid} has {len(b['discussion'])} discussion entries in site/data.json, expected {e.get('discussion', 0)}")
        if b["notes_open"] != e.get("notes_open", 0):
            out.append(f"expect: story {sid} has notes_open {b['notes_open']} in site/data.json, expected {e.get('notes_open', 0)}")
        files = [i.get("file") for i in b.get("images", [])] if isinstance(b.get("images"), list) else None
        if files != e.get("images", []):
            out.append(f"expect: story {sid} has images {files} in site/data.json, expected {e.get('images', [])}")
    prepared = load_json(root.path / "explain.json")
    plain = load_json(root.site / "plain.json")
    for sid in sorted(set(plain) - set(built)):
        out.append(f"expect: site/plain.json names {sid}, which is not a story in site/data.json")
    for sid, b in sorted(built.items()):
        if "plain" in b:
            out.append(f"expect: story {sid} carries plain in site/data.json; it belongs in site/plain.json")
        if not isinstance(plain.get(sid), str) or not plain[sid].strip():
            out.append(f"expect: story {sid} has no plain telling in site/plain.json")
            continue
        src = load_json(root.stories / f"{sid}.json")
        if src.get("plain_by") == "hand":
            if sid in prepared:
                out.append(f"expect: story {sid} is hand-written and must not be in explain.json")
            if plain[sid] != src["plain"]:
                out.append(f"expect: story {sid}: the hand-written plain telling did not reach site/plain.json unchanged")
        elif sid not in prepared:
            out.append(f"expect: story {sid} has a plain telling that explain.json did not give")
        elif plain[sid] != prepared[sid]:
            out.append(f"expect: story {sid}: plain in site/plain.json differs from explain.json")
    for sid in exp.get("plain_by_hand", []):
        src = load_json(root.stories / f"{sid}.json")
        if src.get("plain_by") != "hand":
            out.append(f"expect: story {sid} must still carry plain_by \"hand\" after the chain")
    people_built = load_json(root.site / "data.json")["people"]
    want_img = exp.get("people_images", {})
    for pid, pv in sorted(people_built.items()):
        got = (pv.get("image") or {}).get("file") if "image" in pv else "absent"
        if got != want_img.get(pid):
            out.append(f"expect: person {pid} has image {got!r} in site/data.json, expected {want_img.get(pid)!r}")
    out += image_refusal_problems(root)
    out += image_ingest_problems(root)
    flare = built.get("the-lantern-was-a-flare-1958", {}).get("discussion", [])
    if len(flare) < 2 or not str(flare[1].get("url", "")).endswith("t=27"):
        out.append(f"expect: the flare's second discussion entry has url {flare[1].get('url') if len(flare) > 1 else None!r}, expected one ending t=27")
    notes_file = root.notes / "the-lantern-was-a-flare-1958.json"
    kept = notes_file.read_text(encoding="utf-8")
    notes_file.write_text(json.dumps([{"by": "a", "date": "2026", "text": "t", "status": "Open"}]), encoding="utf-8")
    try:
        root.load_notes()
        out.append("expect: load_notes accepted a note with status 'Open'")
    except SystemExit:
        pass
    finally:
        notes_file.write_text(kept, encoding="utf-8")
    out += fold_discussion_problems()
    out += link_group_problems()
    out += clips_expectations(root, exp)
    out += clips_refusal_problems(root)
    out += replay_weight_problems()
    out += near_duplicate_problems()
    ledger = root.data / "links.json"
    got = [d["key"] for d in (load_json(ledger).get("downgraded", []) if ledger.exists() else [])]
    if got != exp.get("downgraded", []):
        out.append(f"expect: data/links.json downgraded {got}, expected {exp.get('downgraded', [])}")
    for e in exp.get("person_ids", []):
        got = (person_id(e["name"], person_aliases(root.path)), person_id(e["name"], person_aliases(REPO)))
        if got != (e["fixture"], e["repo"]):
            out.append(f"expect: {e['name']!r} resolves to {got} against the fixture and the repo root, expected {(e['fixture'], e['repo'])}")
    ep = load_json(root.episodes / "FIXTURE0001.json")
    template = (REPO / "prompts" / "extract.md").read_text(encoding="utf-8")
    prompt = extract.prompt_for(template, ep, "[0:00:00] words", "the host Ada Fixture")
    for line in (f"Title: {ep['title']}", f"Published: {ep['published']}"):
        if line not in prompt.splitlines():
            out.append(f"expect: the extraction prompt has no line {line!r}")
    if any(k in prompt for k in extract.PLACEHOLDERS):
        out.append("expect: the extraction prompt still holds a placeholder")
    return out


def _image_context(root: Root):
    stories, people = root.load_dir(root.stories), root.load_dir(root.people)
    return stories, root.story_aliases(stories), people


def image_refusal_problems(root: Root) -> list[str]:
    """`images.problems` refuses each kind of bad sidecar or file, written one at a time into the
    fixture root and removed again: the fixture's own images must pass, and each case must be named."""
    import struct
    stories, alias, people = _image_context(root)
    vault = "the-vault-beneath-mount-fictus-1971"
    good = load_json(root.data / "images" / "bo-fixture" / "1.json")
    png = (root.site / "images" / "bo-fixture" / "1.png").read_bytes()
    big = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 600, 40, 8, 2, 0, 0, 0)
    story_sc = {**good, "kind": "object", "caption": "A fictional crate."}
    opaque = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    alias_sc = load_json(root.data / "images" / vault / "1.json")
    alias_jpg = (root.site / "images" / vault / "1.jpg").read_bytes()
    survivor = alias[vault]  # the vault's directory is an alias; its survivor must not hold the same image_url
    lantern = "the-lantern-over-the-harbour-of-nowhere-1958"  # told by bo-fixture alone; survivor by two tellers
    person_sc = {**story_sc, "kind": "person", "person": "Someone Fixture"}
    cases = [  # (what, owner dir, n, sidecar or None, site file bytes or None, ext, the words the problem must carry, None when it must pass)
        ("a fair-use headshot", "bo-fixture", 2, {**good, "licence_kind": "fair-use"}, png, "png", "never fair use"),
        ("a headshot as a story's picture", vault, 2, {**good, "file": f"images/{vault}/2.png"}, png, "png", "does not fit a story owner"),
        ("an object owned by a person", "bo-fixture", 2, {**story_sc}, png, "png", "does not fit a person owner"),
        ("an owner that is nothing", "nobody-fixture", 1, {**good, "file": "images/nobody-fixture/1.png"}, png, "png", "is no story id, alias or person id"),
        ("an unknown field", "bo-fixture", 2, {**good, "photographer": "x"}, png, "png", "unknown field 'photographer'"),
        ("a missing licence", "bo-fixture", 2, {k: v for k, v in good.items() if k != "licence"}, png, "png", "missing licence"),
        ("a source that is not http(s)", "bo-fixture", 2, {**good, "source": "file:///x"}, png, "png", "is not an http(s) URL"),
        ("a missing file", "bo-fixture", 2, {**good}, None, "png", "does not exist"),
        ("a file that is no image", "bo-fixture", 2, {**good}, b"not an image at all", "png", "neither a JPEG nor a PNG"),
        ("a file at another path", "bo-fixture", 2, {**good, "file": "images/bo-fixture/7.png"}, png, "png", "must be images/bo-fixture/2.jpg"),
        ("a fair-use image above 480 px", vault, 2, {**story_sc, "licence_kind": "fair-use", "file": f"images/{vault}/2.png"}, big, "png", "larger than the 480 px"),
        ("a file no sidecar claims", "bo-fixture", 9, None, png, "png", "no sidecar under data/images claims it"),
        ("a PNG without transparency", "bo-fixture", 2, {**good}, opaque, "png", "without transparency"),
        ("an alias directory's image_url again under the survivor", survivor, 1, {**alias_sc, "file": f"images/{survivor}/1.jpg"}, alias_jpg, "jpg", "image_url is the same as"),
        ("a fair-use person picture", survivor, 2, {**person_sc, "licence_kind": "fair-use"}, png, "png", "never fair use"),
        ("a person picture naming no one", survivor, 2, {k: v for k, v in person_sc.items() if k != "person"}, png, "png", "names who it shows"),
        ("a person named on an object", survivor, 2, {**story_sc, "person": "Someone Fixture"}, png, "png", "belongs to a person picture only"),
        ("a person picture beside one other teller's story", lantern, 2, {**person_sc}, png, "png", "needs two or more independent tellers"),
        ("a person picture beside a story two tellers tell", survivor, 2, {**person_sc}, png, "png", None),
        ("a person picture beside the person's own story", lantern, 2, {**person_sc, "person": "bo-fixture"}, png, "png", None),
    ]
    out: list[str] = []
    for what, owner_dir, n, sc, data, ext, words in cases:
        sc_file = root.data / "images" / owner_dir / f"{n}.json"
        img = root.site / "images" / owner_dir / f"{n}.{ext}"
        made = []
        if sc is not None:
            sc ={**sc, "file": sc["file"] if sc.get("file") != good["file"] else f"images/{owner_dir}/{n}.{ext}"}
            sc_file.parent.mkdir(parents=True, exist_ok=True)
            sc_file.write_text(json.dumps(sc), encoding="utf-8")
            made.append(sc_file)
        if data is not None:
            img.parent.mkdir(parents=True, exist_ok=True)
            img.write_bytes(data)
            made.append(img)
        try:
            got = images.problems(root, stories, alias, people)
        finally:
            for f in made:
                f.unlink()
            for d in {f.parent for f in made}:
                if not any(d.iterdir()):
                    d.rmdir()
        if words is None:
            if got:
                out.append(f"expect: images.problems refused {what}: {got}")
        elif not any(words in g for g in got):
            out.append(f"expect: images.problems let {what} through (got {got})")
    left = images.problems(root, stories, alias, people)
    if left:
        out.append(f"expect: the fixture's own images have problems after the refusal cases: {left}")
    return out


def image_ingest_problems(root: Root) -> list[str]:
    """`images.ingest` offline, with a downloader that serves the fixture's own JPEG: a new object
    image lands under the story id as 1.jpg with its sidecar, an image_url the alias directory already
    holds is kept, a second run keeps everything, a failed download stops the run or, with keep_going,
    is listed while the rest goes on, and a bad manifest is refused before anything is fetched. The
    files it makes pass `images.problems` and are removed afterwards."""
    jpeg = (root.site / "images" / "the-vault-beneath-mount-fictus-1971" / "1.jpg").read_bytes()
    asked: list[str] = []

    def fetch(url: str) -> bytes:
        asked.append(url)
        if url.endswith("/gone.jpg"):
            raise SystemExit(f"download failed: {url}: HTTP 404 Not Found")
        if url.endswith("/slow.jpg"):  # the real downloader, its urlopen timing out
            with mock.patch.object(images.urllib.request, "urlopen", side_effect=TimeoutError("timed out")):
                return images.download(url)
        if url.endswith("/page.jpg"):
            return b"<html>"
        return jpeg

    def quiet(line: str) -> None:
        pass

    vault = "a-vault-under-mount-fictus-1971"
    entry = {"owner": vault, "kind": "object", "image_url": "https://example.org/fixture/crate.jpg",
             "source": "https://example.org/fixture/crate", "licence": "Public domain (fixture)", "licence_kind": "free",
             "credit": "Fixture Survey Office", "caption": "A fictional crate in a fictional vault.", "date": "1971-05"}
    held = {**entry, "owner": "the-vault-beneath-mount-fictus-1971", "image_url": "https://example.org/fixture/mount-fictus.jpg", "kind": "place-then"}
    out: list[str] = []
    made_dir = root.data / "images" / vault
    made_site = root.site / "images" / vault
    try:
        lines, failures = images.ingest(root, [entry, held], fetch=fetch, echo=quiet, today="2026-10-16")
        sc_file = made_dir / "1.json"
        if not sc_file.exists() or not (made_site / "1.jpg").exists():
            out.append(f"expect: images.ingest did not write {vault}/1.json and site/images/{vault}/1.jpg (printed {lines})")
        else:
            sc = load_json(sc_file)
            want = {"file": f"images/{vault}/1.jpg", **{k: entry[k] for k in ("kind", "caption", "source", "image_url", "licence", "licence_kind", "credit", "date")}, "fetched": "2026-10-16"}
            if sc != want or list(sc) != [k for k in images.SIDECAR_KEYS if k in sc]:
                out.append(f"expect: images.ingest wrote the sidecar {sc}, expected {want} in the schema's field order")
        if asked != [entry["image_url"]] or failures or not lines[1].startswith("kept"):
            out.append(f"expect: images.ingest fetched {asked} and printed {lines}, expected one fetch and the held image kept")
        asked.clear()
        lines, _ = images.ingest(root, [entry, held], fetch=fetch, echo=quiet)
        if asked or not all(l.startswith("kept") for l in lines):
            out.append(f"expect: a second images.ingest fetched {asked} and printed {lines}, expected everything kept")
        gone = {**entry, "image_url": "https://example.org/fixture/gone.jpg"}
        later = {**entry, "image_url": "https://example.org/fixture/lid.jpg", "licence_kind": "fair-use"}
        try:
            images.ingest(root, [gone, later], fetch=fetch, echo=quiet)
            out.append("expect: images.ingest went on after a failed download without keep_going")
        except SystemExit as x:
            if "HTTP 404" not in str(x) or "gone.jpg" not in str(x):
                out.append(f"expect: a failed download raised {x!s}, expected the URL and the HTTP status")
        lines, failures = images.ingest(root, [gone, later], fetch=fetch, echo=quiet, keep_going=True)
        if len(failures) != 1 or not (made_dir / "2.json").exists():
            out.append(f"expect: images.ingest with keep_going listed {failures} and wrote {sorted(p.name for p in made_dir.iterdir())}, expected one failure and 2.json")
        for what, url in (("a download that times out", "https://example.org/fixture/slow.jpg"),
                          ("a download that is no image", "https://example.org/fixture/page.jpg")):
            lines, failures = images.ingest(root, [{**entry, "image_url": url}], fetch=fetch, echo=quiet, keep_going=True)
            if len(failures) != 1 or url not in failures[0]:
                out.append(f"expect: images.ingest with keep_going listed {failures} for {what}, expected one failure naming {url}")
        stories, alias, people = _image_context(root)
        left = images.problems(root, stories, alias, people)
        if left:
            out.append(f"expect: the images ingest wrote fail the check: {left}")
        for what, bad in (("a fair-use headshot", {**entry, "owner": "bo-fixture", "kind": "headshot", "licence_kind": "fair-use"}),
                          ("an owner that is nothing", {**entry, "owner": "nobody-fixture"}),
                          ("a headshot for a story", {**entry, "kind": "headshot"}),
                          ("an object for a person", {**entry, "owner": "bo-fixture"}),
                          ("a file:// image_url", {**entry, "image_url": "file:///etc/hosts"}),
                          ("a missing credit", {k: v for k, v in entry.items() if k != "credit"})):
            asked.clear()
            try:
                images.ingest(root, [{**entry, "image_url": "https://example.org/fixture/first.jpg"}, bad], fetch=fetch, echo=quiet)
                out.append(f"expect: images.ingest accepted a manifest with {what}")
            except SystemExit:
                if asked:
                    out.append(f"expect: images.ingest fetched {asked} before refusing a manifest with {what}")
    finally:
        shutil.rmtree(made_dir, ignore_errors=True)
        shutil.rmtree(made_site, ignore_errors=True)
    return out


def link_group_problems() -> list[str]:
    """A group call of `link.run_candidates` on a tiny root, with a fake model: `#n` resolves to an
    earlier telling's provisional story or to the held story it joins, a `same` through `#n` at another
    grain is downgraded naming the real id, a refused answer is asked once more with a note, a second
    refusal stops the run, a run killed after one group resumes at the first unlinked candidate with the
    killed run's provisional stories offered again, every `same` or `variant` names a story in its
    `against`, and `--existing` refuses `--batch`."""
    from . import link, llm
    tmp = Path(tempfile.mkdtemp(prefix="nhi-link-group-"))
    out: list[str] = []
    try:
        root = Root(tmp)
        root.stories.mkdir(parents=True)
        root.candidates.mkdir(parents=True)
        vault = {"id": "a-vault-1971", "title": "A vault under Mount Fictus", "summary": "", "years": {"from": 1971, "to": 1971},
                 "place_text": "Mount Fictus", "kind": "program", "related": [],
                 "tellings": [{"episode": "G0", "from_s": 1, "teller": "cy-fixture", "quote": "We dug a vault under the mountain.",
                               "kind": "firsthand", "cites": [], "documents": []}]}
        save_json(root.stories / "a-vault-1971.json", vault)
        def cand(title, kind, year, n):
            return {"title": title, "story_kind": kind, "years_text": str(year), "years": {"from": year, "to": year},
                    "place_text": None, "teller": "Ida Fixture", "kind": "firsthand", "quote": f"quote {n}",
                    "from_s": n, "to_s": n + 1, "cites": [], "documents": []}
        cands = [cand("The ring in the ice", "sighting", 1980, 1), cand("A melted ring", "sighting", 1980, 2),
                 cand("Guarding the vault", "program", 1971, 3), cand("The vault again", "program", 1971, 4),
                 cand("A crate in the vault", "incident", 1971, 5)]
        plan = {"The ring in the ice": ("new", None, "same"), "A melted ring": ("same", "The ring in the ice", "same"),
                "Guarding the vault": ("same", "a-vault-1971", "same"), "The vault again": ("same", "Guarding the vault", "same"),
                "A crate in the vault": ("same", "Guarding the vault", "narrower")}
        joined = {"Guarding the vault": "a-vault-1971"}  # a target in an earlier group: the story it ended in
        prompts: list[str] = []
        def model(bad=(), dead_after=None, always=False):
            def complete(prompt, schema, *, model, timeout):
                prompts.append(prompt)
                if dead_after is not None and len(prompts) > dead_after:
                    raise llm.LlmUnavailable("usage limit (fake)")
                titles = re.findall(r'<telling number="\d+">\ntitle: (.*)', prompt)
                ds = []
                for n, t in enumerate(titles, 1):
                    dec, target, grain = plan[t]
                    if target in titles:
                        story = f"#{titles.index(target) + 1}"
                    else:  # the earlier telling went in another group: name the story it joined
                        story = joined.get(target, target)
                    if t in bad and (always or "previous answer was refused" not in prompt):
                        story = "no-such-story"
                    ds.append({"candidate": n, "reason": f"fake reason {n}", "story": story, "grain": grain,
                               "decision": dec, "difference": ""})
                return {"decisions": ds}
            return complete
        f = root.candidates / "G1.json"
        save_json(f, {"episode": "G1", "candidates": cands})
        asker = link.Asker(root, "fake", 1, None, complete=model(bad={"A melted ring"}))
        link.run_candidates(root, None, asker)
        got = {c["title"]: c["link"] for c in load_json(f)["candidates"]}
        if asker.calls != 1 or len(prompts) != 2 or "previous answer was refused" not in prompts[1]:
            out.append(f"expect: a refused group must be asked once more with a note (calls {asker.calls}, prompts {len(prompts)})")
        if got["A melted ring"].get("story") != got["The ring in the ice"].get("id") or got["A melted ring"]["decision"] != "same":
            out.append(f"expect: '#1' must resolve to the ring's provisional story, got {got['A melted ring']}")
        if got["The vault again"].get("story") != "a-vault-1971":
            out.append(f"expect: '#n' of a telling that joined a held story must resolve to it, got {got['The vault again']}")
        dg = got["A crate in the vault"]
        if dg["decision"] != "new" or dg.get("downgraded", {}).get("story") != "a-vault-1971" or "#" in dg["downgraded"]["why"]:
            out.append(f"expect: a narrower same through '#n' must be downgraded naming a-vault-1971, got {dg}")
        if got["The ring in the ice"]["against"] != ["a-vault-1971"]:
            out.append(f"expect: the ring's against must be what its group was offered, ['a-vault-1971'], got {got['The ring in the ice']['against']}")
        for t, ln in got.items():
            if ln["decision"] in ("same", "variant") and ln["story"] not in ln["against"]:
                out.append(f"expect: {t!r} is {ln['decision']} {ln['story']}, which must be in its against {ln['against']}")
        ledger = load_json(root.data / "links.json")
        if [d["key"] for d in ledger.get("downgraded", [])] != ["A crate in the vault"]:
            out.append(f"expect: data/links.json must list the crate's downgrade, got {ledger.get('downgraded')}")
        save_json(f, {"episode": "G1", "candidates": [dict(c) for c in cands]})
        prompts.clear()
        try:
            link.run_candidates(root, None, link.Asker(root, "fake", 1, None, complete=model(bad=set(plan), always=True)))
            out.append("expect: a group refused twice must stop the run")
        except SystemExit:
            pass
        prompts.clear()
        try:
            link.run_candidates(root, None, link.Asker(root, "fake", 1, None, complete=model(dead_after=1)), size=2)
            out.append("expect: an unavailable model must stop the run")
        except llm.LlmUnavailable:
            pass
        linked = [c["title"] for c in load_json(f)["candidates"] if "link" in c]
        if linked != ["The ring in the ice", "A melted ring"]:
            out.append(f"expect: a run killed after its first group of two must keep exactly that group's links, got {linked}")
        prompts.clear()
        ring = next(c["link"] for c in load_json(f)["candidates"] if c["title"] == "The ring in the ice")
        joined["The ring in the ice"] = ring["id"]
        plan["A crate in the vault"] = ("same", "The ring in the ice", "same")
        resumed = link.Asker(root, "fake", 1, None, complete=model())
        try:
            link.run_candidates(root, None, resumed, size=2)
        except SystemExit as e:
            out.append(f"expect: a resumed run must offer the ring the killed run created: {e}")
        told = [t for x in prompts for t in re.findall(r'<telling number="\d+">\ntitle: (.*)', x)]
        if resumed.calls != 2 or "The ring in the ice" in told:
            out.append(f"expect: a resumed run must ask only the unlinked candidates, in two groups (calls {resumed.calls})")
        after = {c["title"]: c.get("link") for c in load_json(f)["candidates"]}
        if not all(after.values()):
            out.append("expect: a resumed run must link every candidate")
        elif after["A crate in the vault"]["story"] != ring["id"]:
            out.append(f"expect: a resumed candidate same as the ring must join {ring['id']}, got {after['A crate in the vault']}")
        else:
            for t, ln in after.items():
                if ln["decision"] in ("same", "variant") and ln["story"] not in ln["against"]:
                    out.append(f"expect: resumed {t!r} is {ln['decision']} {ln['story']}, which must be in its against {ln['against']}")
        try:
            link.main(["--existing", "--batch", "5", "--root", str(tmp)])
            out.append("expect: link --existing --batch must fail loud")
        except SystemExit:
            pass
    finally:
        shutil.rmtree(tmp)
    return out


def clips_expectations(root: Root, exp: dict) -> list[str]:
    """The clips ledger's verdicts and the tellings it marks, as expect.json gives them; then a hand-marked
    `not-a-clip` restores the replayed telling's teller, and putting the ledger back marks it again."""
    out: list[str] = []
    ledger_file = root.data / "clips.json"
    ledger = load_json(ledger_file)
    got = {g["id"]: {"verdict": g["verdict"], "speaker": g["speaker"], "origin": g["origin"],
                     "episodes": [o["episode"] for o in g["occurrences"]]} for g in ledger["groups"]}
    if got != exp.get("clips", {}):
        out.append(f"expect: data/clips.json holds {got}, expected {exp.get('clips', {})}")
    stories = root.load_dir(root.stories)
    marked = [{"story": sid, "episode": t["episode"], "teller": t["teller"], "teller_was": t.get("teller_was"),
               "replay_of": t.get("replay_of")} for sid, s in sorted(stories.items()) for t in s["tellings"]
              if "replay_of" in t or "teller_was" in t]
    if marked != exp.get("replays", []):
        out.append(f"expect: the tellings the clips stage marked are {marked}, expected {exp.get('replays', [])}")
    if not marked:
        return out
    sid = marked[0]["story"]
    story_file = root.stories / f"{sid}.json"
    kept_ledger, kept_story = ledger_file.read_text(encoding="utf-8"), story_file.read_text(encoding="utf-8")
    try:
        hand = load_json(ledger_file)
        for g in hand["groups"]:
            g.update({"verdict": "not-a-clip", "speaker": None, "speaker_name": None, "also_heard": [], "origin": None, "by": "hand"})
        save_json(ledger_file, hand)
        clips.apply(root, write=True)
        t = next(t for t in load_json(story_file)["tellings"] if t["episode"] == marked[0]["episode"])
        if t["teller"] != marked[0]["teller_was"] or "replay_of" in t or "teller_was" in t:
            out.append(f"expect: a hand not-a-clip must restore {sid}'s telling to {marked[0]['teller_was']} unmarked, got {t}")
        ledger_file.write_text(kept_ledger, encoding="utf-8")
        clips.apply(root, write=True)
        if story_file.read_text(encoding="utf-8") != kept_story:
            out.append(f"expect: applying the ledger again must mark {sid} exactly as before")
    finally:
        ledger_file.write_text(kept_ledger, encoding="utf-8")
        story_file.write_text(kept_story, encoding="utf-8")
    return out


def clips_refusal_problems(root: Root) -> list[str]:
    """`clips.Asker` with a fake model: a refused answer is asked once more with a note, a second refusal stops."""
    prompts: list[str] = []
    good = {"group": 1, "reason": "r", "verdict": "clip", "speaker": "fay-fixture", "also_heard": [], "origin": "#1"}

    def model(always: bool):
        def complete(prompt, schema, *, model, timeout):
            prompts.append(prompt)
            if always or "previous answer was refused" not in prompt:
                return {"groups": [{**good, "origin": "#9"}]}
            return {"groups": [good]}
        return complete

    out: list[str] = []
    got = clips.Asker(root, "fake", 1, None, complete=model(False)).ask("<group number=\"1\">", ["g"], [2])
    if len(prompts) != 2 or "previous answer was refused" not in prompts[1] or got[0]["origin"] != "#1":
        out.append(f"expect: a refused clips answer must be asked once more with a note (prompts {len(prompts)}, got {got})")
    prompts.clear()
    try:
        clips.Asker(root, "fake", 1, None, complete=model(True)).ask("<group number=\"1\">", ["g"], [2])
        out.append("expect: a clips answer refused twice must stop the run")
    except SystemExit:
        pass
    return out


def replay_weight_problems() -> list[str]:
    """`score.attest`: a replay labelled first-hand never lifts a speaker whose own telling is second-hand,
    and a speaker heard only in replays keeps the replay's kind."""
    from . import score
    own = {"episode": "A", "from_s": 1, "teller": "fay-fixture", "quote": "q", "kind": "secondhand", "cites": [], "documents": []}
    replay = {**own, "episode": "B", "kind": "firsthand", "teller_was": "hal-fixture", "replay_of": {"episode": "A", "from_s": 1}}
    out = []
    p = score.attest({"id": "r", "tellings": [own, replay]})["profile"]
    if (p["independent_tellers"], p["secondhand"], p["firsthand"]) != (1, 1, 0):
        out.append(f"expect: a first-hand replay beside a second-hand own telling must count one second-hand teller, got {p}")
    p = score.attest({"id": "r", "tellings": [replay]})["profile"]
    if (p["independent_tellers"], p["firsthand"]) != (1, 1):
        out.append(f"expect: a speaker heard only in a replay must count by the replay's kind, got {p}")
    return out


def within_edits(a: str, b: str, k: int) -> bool:
    """Levenshtein distance of a and b is at most k (stops early once every path exceeds k)."""
    if abs(len(a) - len(b)) > k:
        return False
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
        if min(cur) > k:
            return False
        prev = cur
    return prev[-1] <= k


def near_duplicate_people(ids) -> list[tuple[str, str]]:
    """Pairs of person ids of 8 letters or more (hyphens dropped) within two edits of each other."""
    keys = sorted((pid.replace("-", ""), pid) for pid in ids)
    by_len: dict[int, list[tuple[str, str]]] = {}
    for k, pid in keys:
        by_len.setdefault(len(k), []).append((k, pid))
    out = []
    for k, pid in keys:
        if len(k) < 8:
            continue
        for n in range(len(k), len(k) + 3):
            for k2, pid2 in by_len.get(n, []):
                if (n, k2) > (len(k), k) and within_edits(k, k2, 2):
                    out.append((pid, pid2))
    return out


def near_duplicate_problems() -> list[str]:
    """The near-duplicate warning pairs two spellings of one name and leaves short or distinct ids alone."""
    ids = ["greg", "greg-malatzi", "greg-malazzi", "james-fox", "james-woods", "bob-jameson", "robert-jameson", "donald-trump"]
    got = near_duplicate_people(ids)
    want = [("greg-malatzi", "greg-malazzi")]
    return [] if got == want else [f"expect: near-duplicate people {want}, got {got}"]


def fold_discussion_problems() -> list[str]:
    """`link.fold` appends the folded story's discussion to the survivor's, in order, and drops none."""
    from . import link
    d1 = {"kind": "debunk", "by": "Ida Fixture", "source": "https://example.org/a", "text": "Ida Fixture says it was a lamp."}
    d2 = {"kind": "rebunk", "by": "Jo Fixture", "source": "https://example.org/b", "text": "Jo Fixture says the lamp was off."}
    d3 = {"kind": "note", "by": "Kit Fixture", "source": "https://example.org/c", "text": "Kit Fixture says the date is wrong."}
    base = {"title": "t", "years": None, "place_text": None, "kind": "sighting", "related": [], "tellings": []}
    stories = {"a": {**base, "id": "a", "discussion": [d1]}, "b": {**base, "id": "b", "discussion": [d2, d3]},
               "c": {**base, "id": "c"}, "d": {**base, "id": "d", "discussion": [d1]}}
    link.fold(stories, "b", "a", "r", "")
    link.fold(stories, "d", "c", "r", "")
    out = []
    if stories["a"].get("discussion") != [d1, d2, d3]:
        out.append(f"expect: fold left the survivor's discussion as {stories['a'].get('discussion')}, expected three entries in order")
    if stories["c"].get("discussion") != [d1]:
        out.append(f"expect: fold into a story without discussion left {stories['c'].get('discussion')}, expected the folded one's entry")
    return out


SOURCE_MANIFEST = Path("sources") / "manifest.json"


class SourceFetch:
    """The fixture's text downloader: a URL ending in /served/<name> is sources/served/<name> of the root;
    any other URL fails as a 404 would. Counts the calls."""

    def __init__(self, root: Root):
        self.root, self.calls = root, 0

    def __call__(self, url: str) -> str:
        self.calls += 1
        name = url.rsplit("/served/", 1)[-1] if "/served/" in url else None
        f = self.root.path / "sources" / "served" / name if name else None
        if f is None or not f.is_file():
            raise SystemExit(f"fetch failed: {url}: HTTP 404 Not Found")
        return f.read_text(encoding="utf-8")


def run_sources(root: Root, fetch) -> dict:
    return sources.run(root, load_json(root.path / SOURCE_MANIFEST), manifest=root.path / SOURCE_MANIFEST, fetch=fetch,
                       echo=lambda *_: None)


def source_expectations(root: Root, exp: dict) -> list[str]:
    """expect.json `sources`: the documents the stage made or filled, the text files, the tellings it added, the
    images manifest it wrote (which pipeline.images must accept), and what explain sends the model."""
    from . import explain
    want = exp.get("sources")
    if not want:
        return ["expect: expect.json has no sources section"]
    out: list[str] = []
    documents = root.load_dir(root.documents)
    for did, fields in want["documents"].items():
        d = documents.get(did)
        if d is None:
            out.append(f"expect: sources made no document {did}")
            continue
        for k, v in fields.items():
            if d.get(k) != v:
                out.append(f"expect: document {did} has {k} {d.get(k)!r}, expected {v!r}")
    texts = sorted(p.stem for p in sources.text_dir(root).glob("*.txt"))
    if texts != sorted(want["texts"]):
        out.append(f"expect: sources/documents holds {texts}, expected {sorted(want['texts'])}")
    stories = root.load_dir(root.stories)
    for sid, tellings in want["tellings"].items():
        got = [{k: t.get(k) for k in ("document", "page", "teller", "kind")} for t in stories[sid]["tellings"] if t.get("document")]
        if got != tellings:
            out.append(f"expect: story {sid} has the document tellings {got}, expected {tellings}")
        notes = [d for d in stories[sid].get("discussion", []) if d.get("kind") == "source"]
        if len(notes) != want["source_notes"].get(sid, 0):
            out.append(f"expect: story {sid} has {len(notes)} source notes, expected {want['source_notes'].get(sid, 0)}")
        text = explain.story_text(stories[sid], stories, root.load_dir(root.people), root.load_dir(root.episodes), documents, {})
        for line in want["explain_lines"].get(sid, []):
            if line not in text:
                out.append(f"expect: explain's text for {sid} lacks {line!r}")
    ims = sources.images_manifest_path(root.path / SOURCE_MANIFEST)
    entries = load_json(ims) if ims.exists() else []
    if len(entries) != want["images"]:
        out.append(f"expect: {rel(ims, root.path)} holds {len(entries)} images, expected {want['images']}")
    stories_now, people = root.load_dir(root.stories), root.load_dir(root.people)
    out += [f"expect: pipeline.images refuses the sources' images manifest: {p}" for p in
            images.manifest_problems(entries, stories_now, root.story_aliases(stories_now), people, images.load_profiles(root))]
    return out


def source_ingest_problems(root: Root) -> list[str]:
    """The stage's other paths, on a copy of the finished fixture root: passages of a book in copyright under
    their locators (appended by a second entry), a slug taken by another document, a wrong locator, a quote
    that is not verbatim, a failed fetch of a public-domain text (stopping the run, or listed under keep_going),
    a full text for a document of unknown status and for one in copyright, an issuer standing in as teller (its
    tellings `official` whatever the entry's kind) on a document whose stub title the manifest's replaces, and
    the check's refusals of a missing text file, a wrong page, a stray text file and a full text kept for a
    document that is not public domain."""
    tmp = Path(tempfile.mkdtemp(prefix="nhi-sources-"))
    shutil.copytree(root.path, tmp, dirs_exist_ok=True)
    r = Root(tmp)
    out: list[str] = []
    sid = "the-harbour-light-was-a-weather-balloon-1958"
    book = {"id": None, "title": "Balloons Over Nowhere", "author": "Lu Fixture", "issuer": None, "date": "2001",
            "url": "https://example.org/balloons", "text_url": None, "status": "in-copyright"}

    def entry(passages, quotes, **kw):
        return {"story": sid, "document": {**book, **kw.pop("document", {})}, "text": {"url": kw.pop("url", None), "passages": passages},
                "quotes": quotes, "teller": None, "kind": "researcher", "differs": None, "images": [], **kw}

    p2 = {"locator": "chapter 2", "text": "The fishermen of Nowhere launched weather balloons from the mole every summer evening."}
    p5 = {"locator": "chapter 5", "text": "A balloon caught in the harbour wind could hang over the water for an hour."}
    q2 = {"quote": "launched weather balloons from the mole every summer evening", "locator": "chapter 2"}
    q5 = {"quote": "could hang over the water for an hour", "locator": "chapter 5"}
    fetch = SourceFetch(r)
    quiet = lambda *_: None
    sources.run(r, [entry([p2], [q2])], fetch=fetch, echo=quiet)
    sources.run(r, [entry([p5], [q5])], fetch=fetch, echo=quiet)
    did = "balloons-over-nowhere"
    text = (sources.text_path(r, did)).read_text(encoding="utf-8") if sources.text_path(r, did).exists() else ""
    if text != f"[chapter 2]\n{p2['text']}\n\n[chapter 5]\n{p5['text']}\n":
        out.append(f"expect: the passages file of {did} is {text!r}")
    told = [(t.get("page"), t.get("teller")) for t in load_json(r.stories / f"{sid}.json")["tellings"] if t.get("document") == did]
    if told != [("chapter 2", "lu-fixture"), ("chapter 5", "lu-fixture")]:
        out.append(f"expect: the book's tellings are {told}, expected chapter 2 and chapter 5 by lu-fixture")
    if fetch.calls:
        out.append(f"expect: a passages entry fetched {fetch.calls} time(s)")
    other = entry([p2], [q2], document={"url": "https://example.org/balloons-again", "date": "2010"})
    sources.run(r, [other], fetch=fetch, echo=quiet)
    if not (r.documents / f"{did}-2010.json").exists():
        out.append(f"expect: a second document titled like {did} with another url and year did not become {did}-2010")
    out += [f"expect: after the passages entries, {p}" for p in problems(r)]
    refused = [
        ("a wrong locator", entry([p2], [{**q2, "locator": "chapter 3"}])),
        ("a quote that is not verbatim", entry([p2], [{**q2, "quote": "launched balloons from the mole"}])),
        ("a failed fetch", entry([], [q2], url="https://example.org/nowhere.txt",
                                 document={"id": "fetched-nowhere", "status": "public-domain", "text_url": "https://example.org/nowhere.txt"})),
        ("a full text for a document of unknown status", entry([], [q2], url="https://example.org/served/lanterns-of-nowhere.txt",
                                                               document={"id": "unknown-full", "status": "unknown",
                                                                         "text_url": "https://example.org/served/lanterns-of-nowhere.txt"})),
    ]
    for what, e in refused:
        before = snapshot(r.path)
        try:
            sources.run(r, [e], fetch=fetch, echo=quiet)
            out.append(f"expect: sources accepted {what}")
        except SystemExit as x:
            if what.startswith("a full text") and "public-domain" not in str(x):
                out.append(f"expect: {what} was refused for another reason: {x}")
        if snapshot(r.path) != before:
            out.append(f"expect: sources wrote files for an entry refused for {what}")
    res = sources.run(r, [refused[2][1], entry([p2], [q2])], fetch=fetch, keep_going=True, echo=quiet)
    if len(res["failures"]) != 1 or "404" not in res["failures"][0]:
        out.append(f"expect: keep_going listed {res['failures']}, expected the one failed fetch")
    try:
        sources.run(r, [entry([], [q2], url="https://example.org/served/lanterns-of-nowhere.txt")], fetch=fetch, echo=quiet)
        out.append("expect: sources accepted a fetched full text for a document in copyright")
    except SystemExit as x:
        if "refused" not in str(x):
            out.append(f"expect: a full text for a document in copyright was refused only at ingest: {x}")
    stub = {"id": "harbour-board-balloon-notice", "title": "harbour board balloon notice", "issuer": None, "date": None,
            "url": None, "kind": None, "attests": []}
    save_json(r.documents / f"{stub['id']}.json", stub)
    notice = {"id": stub["id"], "title": "Notice to Mariners No. 7", "author": None, "issuer": "Harbour Board of Nowhere",
              "date": "1958", "url": "https://example.org/notice-7", "text_url": None, "status": "unknown"}
    pn = {"locator": "p. 1", "text": "Weather balloons are released from the mole at dusk and may show a light."}
    said: list[str] = []
    sources.run(r, [entry([pn], [{"quote": "may show a light", "locator": "p. 1"}], document=notice)], fetch=fetch, echo=said.append)
    told = [t for t in load_json(r.stories / f"{sid}.json")["tellings"] if t.get("document") == stub["id"]]
    if [(t["teller"], t["kind"]) for t in told] != [("harbour-board-of-nowhere", "official")]:
        out.append(f"expect: an issuer standing in as teller of a `researcher` entry told {[(t['teller'], t['kind']) for t in told]}, "
                   "expected harbour-board-of-nowhere as official")
    if load_json(r.people / "harbour-board-of-nowhere.json").get("roles") != ["official"]:
        out.append("expect: the issuer standing in as teller is not a person of role official")
    if load_json(r.documents / f"{stub['id']}.json")["title"] != notice["title"]:
        out.append("expect: a document's stub title was not replaced by the manifest's title")
    if not any(line.startswith("title ") and notice["title"] in line for line in said):
        out.append(f"expect: the title replacement was not reported; the stage said {said}")
    f = sources.text_path(r, did)
    kept = f.read_text(encoding="utf-8")
    f.unlink()
    if not any("has no text file" in p for p in problems(r)):
        out.append("expect: check passed a document telling without a text file")
    f.write_text(kept.replace("[chapter 5]", "[chapter 6]"), encoding="utf-8")
    if not any("not [chapter 5]" in p for p in problems(r)):
        out.append("expect: check passed an in-copyright quote under another locator than its page")
    f.write_text(kept, encoding="utf-8")
    (sources.text_dir(r) / "stray.txt").write_text("words\n", encoding="utf-8")
    if not any("stray.txt" in p for p in problems(r)):
        out.append("expect: check passed a text file no document has")
    (sources.text_dir(r) / "stray.txt").unlink()
    lanterns = load_json(r.documents / "the-lanterns-of-nowhere.json")
    save_json(r.documents / "the-lanterns-of-nowhere.json", {**lanterns, "status": "unknown"})
    if not any("text before the first [locator]" in p for p in problems(r)):
        out.append("expect: check passed a full text kept for a document that is not public domain")
    save_json(r.documents / "the-lanterns-of-nowhere.json", lanterns)
    if not out:
        shutil.rmtree(tmp)
    else:
        out.append(f"expect: the sources copy is left in {tmp}")
    return out


def snapshot(d: Path) -> dict[str, str]:
    return {rel(f, d): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.rglob("*")) if f.is_file()}


def run_fixture() -> list[str]:
    from . import build, explain, extract, link, merge, score
    if not FIXTURES.exists():
        raise SystemExit(f"no fixtures at {FIXTURES}")
    tmp = Path(tempfile.mkdtemp(prefix="nhi-fixture-"))
    shutil.copytree(FIXTURES, tmp, dirs_exist_ok=True)
    root = Root(tmp)
    answers = sorted((tmp / "answers").glob("*.json"))
    if not answers:
        raise SystemExit("fixture has no answers/*.json")
    links = tmp / "links"
    existing = links / "existing.json"
    out: list[str] = []
    for f in answers:
        if not (links / f.name).exists():
            extract.run(root, f.stem, model="fixture", chunk_words=12000, fixture=f, timeout=1)
    merge.run(root)
    askers = [link.Asker(root, "fixture", 1, existing)]
    link.run_existing(root, askers[0])
    linked = [f.stem for f in answers if (links / f.name).exists()]
    prepared: list = []
    for e in linked:
        extract.run(root, e, model="fixture", chunk_words=12000, fixture=tmp / "answers" / f"{e}.json", timeout=1)
        more = load_json(links / f"{e}.json")
        if not isinstance(more, list) or any(g.get("episode") != e for g in more):
            raise SystemExit(f"fixture: links/{e}.json must be a list of groups of episode {e}")
        prepared += more
    together = tmp / "links-together.json"  # one link call over every linked episode, so they can join each other
    together.write_text(json.dumps(prepared), encoding="utf-8")
    askers.append(link.Asker(root, "fixture", 1, together))
    link.run_candidates(root, linked, askers[-1])
    merge.run(root)
    for a in askers:
        unused = sorted(set(a.fixture) - set(a.used))
        if unused:
            out.append(f"link: prepared answers never asked for: {unused}")
    clip_asker = clips.Asker(root, "fixture", 1, tmp / "clips.json")
    clips.run(root, clip_asker)
    unused = sorted(set(clip_asker.fixture) - clip_asker.used)
    if unused:
        out.append(f"clips: prepared answers never asked for: {unused}")
    run_sources(root, SourceFetch(root))
    score.run(root)
    explain.run(root, explain.Asker(root, "fixture", 1, tmp / "explain.json"))
    build.run(root, root.site / "data.json")
    out += problems(root)
    out += expectations(root)
    out += source_expectations(root, load_json(root.path / "expect.json"))
    out += source_ingest_problems(root)
    before = {**snapshot(root.data), **{f"sources/{k}": v for k, v in snapshot(root.path / "sources").items()}}
    again = link.Asker(root, "fixture", 1, None)
    link.run_existing(root, again)
    link.run_candidates(root, None, again)
    if again.calls:
        out.append(f"link is not idempotent: a second run asked {again.calls} question(s)")
    stats = merge.run(root)
    clip_again = clips.Asker(root, "fixture", 1, tmp / "clips.json")
    clips.run(root, clip_again)
    if clip_again.calls:
        out.append(f"clips is not idempotent: a second run asked {clip_again.calls} question(s)")
    src_again = SourceFetch(root)
    if run_sources(root, src_again)["changed"] or src_again.calls:
        out.append(f"sources is not idempotent: a second run changed stories or fetched {src_again.calls} time(s)")
    score.run(root)
    explained = explain.Asker(root, "fixture", 1, tmp / "explain.json")
    explain.run(root, explained)
    if explained.calls:
        out.append(f"explain is not idempotent: a second run asked {explained.calls} question(s)")
    after = {**snapshot(root.data), **{f"sources/{k}": v for k, v in snapshot(root.path / "sources").items()}}
    if before != after:
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        out.append(f"merge is not idempotent: a second run changed {changed}")
    if any(v for k, v in stats.items()):
        out.append(f"merge is not idempotent: a second run reported {stats}")
    if out:
        print(f"check: fixture chain left in {tmp} for inspection", file=sys.stderr)
    else:
        shutil.rmtree(tmp)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--fixture", action="store_true")
    a = ap.parse_args(argv)
    out = run_fixture() if a.fixture else problems(Root(a.root))
    for p in out:
        print(p)
    if not a.fixture:
        pairs = near_duplicate_people(f.stem for f in Root(a.root).people.glob("*.json"))
        for x, y in pairs:
            print(f"warning: people {x} and {y} may be one person; fold one through data/person-aliases.json")
        if pairs:
            print(f"check: {len(pairs)} near-duplicate person pair(s), warnings only")
    label = "fixture" if a.fixture else str(a.root)
    if out:
        print(f"check: {len(out)} problem(s) in {label}")
        return 1
    print(f"check: ok ({label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
