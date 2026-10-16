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
it), is no alias itself, and no alias is the id of a different person. Prints every problem and
exits 1 when there is one.

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
carry a `difference` and a telling's `as_told`), the candidates `link` downgraded, and one name
resolved against the fixture's person aliases and the repo's, which must differ.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

import json

from .common import (REPO, RELATIONS, STORY_KINDS, TELLING_KINDS, Captions, Root, load_json, norm_ws, person_aliases,
                     person_id, rel)

FIXTURES = REPO / "tests" / "fixtures"


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
    owner: dict[str, str] = {}
    for sid, s in sorted(stories.items()):
        for a in s.get("aliases", []):
            if a in stories:
                out.append(f"story {sid}: alias {a!r} is also a story id")
            elif a in owner:
                out.append(f"story {sid}: alias {a!r} is also an alias of {owner[a]}")
            else:
                owner[a] = sid
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
        for r in s.get("related") or []:
            if r.get("story") not in stories:
                out.append(f"{where}: related story {r.get('story')!r} does not exist")
            if r.get("relation") not in RELATIONS:
                out.append(f"{where}: relation {r.get('relation')!r} is not one of {RELATIONS}")
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
