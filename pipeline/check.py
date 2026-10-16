"""Keep the data honest.

    uv run python -m pipeline.check [--root DIR]
    uv run python -m pipeline.check --fixture

Every story has at least one telling; every episode, document, person, era, place and related
story id resolves; every quote with an episode is a verbatim substring of that episode's caption
text (time codes stripped, whitespace collapsed, otherwise exact); kinds and relations are from the
schema; `score` is absent, null or numeric; every alias belongs to one story and is no story's id;
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
under site/images has a sidecar (`images.problems`). Prints every problem, naming the story and the
entry, and exits 1 when there is one.

--fixture copies tests/fixtures/ to a temporary directory and runs the chain with the prepared
answers, no `claude -p`: the episodes without a `links/<id>.json` are extracted and merged unlinked
(the corpus as it stood before linking), `link --existing` folds and relates their stories with
`links/existing.json`, then the episodes with a links file are extracted, linked in one call (so
one can join a story another creates) and merged; score and build follow. It checks the result and that every prepared link answer was asked for, then
runs both link modes, merge and score again and verifies that nothing was asked and nothing
changed. Last it checks `tests/fixtures/expect.json`: the time codes given candidates must have
(the nearest of two occurrences, quotes across a `>>` or a bracketed tag), the people that must not
exist (a spelling the person aliases fold), the host and guests `captions.host_and_guests` must take
from each title, that `captions --refill` fills only host and guests, and that the extraction
prompt carries the episode's title and date lines; then every story the chain made, with its tier,
`contradicted` flag and attestation (and for some its years, aliases, episodes, the tellings that
carry a `difference` and a telling's `as_told`), every story's `discussion` length and `notes_open`
in site/data.json (0 when expect.json gives none), that `link.fold` appends a folded story's
discussion to the survivor's in order, the candidates `link` downgraded, and one name
resolved against the fixture's person aliases and the repo's, which must differ.
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

from . import images
from .common import (DISCUSSION_KEYS, DISCUSSION_KINDS, DISCUSSION_ROLES, NOTE_KEYS, REPO, RELATIONS,
                     STORY_KINDS, TELLING_KINDS, Captions, Root, load_json, norm_ws, person_aliases, person_id, rel, seconds)

FIXTURES = REPO / "tests" / "fixtures"
DATE = re.compile(r"\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?")
URL = re.compile(r"https?://\S+")


def text_field(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


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
        if "source" in e and not (isinstance(e["source"], str) and URL.fullmatch(e["source"])):
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
    for eid, e in episodes.items():
        if e.get("captions") and not (root.path / e["captions"]).exists():
            out.append(f"episode {eid}: captions file {e['captions']} is missing")
        if e.get("captions_source") not in (None, "gemini"):
            out.append(f"episode {eid}: captions_source {e['captions_source']!r} is not gemini or absent")
        if e.get("captions_source") == "gemini" and not isinstance(e.get("timestamps_approximate"), bool):
            out.append(f"episode {eid}: a gemini episode needs timestamps_approximate true or false")
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
    cases = [  # (what, owner dir, n, sidecar or None, site file bytes or None, ext, the words the problem must carry)
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
        if not any(words in g for g in got):
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
            if sc != want or list(sc) != list(images.SIDECAR_KEYS):
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


def snapshot(d: Path) -> dict[str, str]:
    return {rel(f, d): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.rglob("*")) if f.is_file()}


def run_fixture() -> list[str]:
    from . import build, extract, link, merge, score
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
    prepared: dict = {}
    for e in linked:
        extract.run(root, e, model="fixture", chunk_words=12000, fixture=tmp / "answers" / f"{e}.json", timeout=1)
        more = load_json(links / f"{e}.json")
        if set(more) & set(prepared):
            raise SystemExit(f"fixture: links/{e}.json repeats a candidate title of another links file: {sorted(set(more) & set(prepared))}")
        prepared.update(more)
    together = tmp / "links-together.json"  # one link call over every linked episode, so they can join each other
    together.write_text(json.dumps(prepared), encoding="utf-8")
    askers.append(link.Asker(root, "fixture", 1, together))
    link.run_candidates(root, linked, askers[-1])
    merge.run(root)
    for a in askers:
        unused = sorted(set(a.fixture) - set(a.used))
        if unused:
            out.append(f"link: prepared answers never asked for: {unused}")
    score.run(root)
    build.run(root, root.site / "data.json")
    out += problems(root)
    out += expectations(root)
    before = snapshot(root.data)
    again = link.Asker(root, "fixture", 1, None)
    link.run_existing(root, again)
    link.run_candidates(root, None, again)
    if again.calls:
        out.append(f"link is not idempotent: a second run asked {again.calls} question(s)")
    stats = merge.run(root)
    score.run(root)
    after = snapshot(root.data)
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
    label = "fixture" if a.fixture else str(a.root)
    if out:
        print(f"check: {len(out)} problem(s) in {label}")
        return 1
    print(f"check: ok ({label})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
