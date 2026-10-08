"""Keep the data honest.

    uv run python -m pipeline.check [--root DIR]
    uv run python -m pipeline.check --fixture

Every story has at least one telling; every episode, document, person, era, place and related
story id resolves; every quote with an episode is a verbatim substring of that episode's caption
text (time codes stripped, whitespace collapsed, otherwise exact); kinds and relations are from the
schema; `score` is absent, null or numeric. Prints every problem and exits 1 when there is one.

--fixture copies tests/fixtures/ to a temporary directory, runs extract (with the prepared answers,
no `claude -p`), merge, score and build on it, checks the result, then runs merge and score again
and verifies that nothing changed.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import tempfile
from pathlib import Path

from .common import REPO, RELATIONS, STORY_KINDS, TELLING_KINDS, Captions, Root, rel

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
    return out


def snapshot(d: Path) -> dict[str, str]:
    return {rel(f, d): hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(d.rglob("*")) if f.is_file()}


def run_fixture() -> list[str]:
    from . import build, extract, merge, score
    if not FIXTURES.exists():
        raise SystemExit(f"no fixtures at {FIXTURES}")
    tmp = Path(tempfile.mkdtemp(prefix="nhi-fixture-"))
    shutil.copytree(FIXTURES, tmp, dirs_exist_ok=True)
    root = Root(tmp)
    answers = sorted((tmp / "answers").glob("*.json"))
    if not answers:
        raise SystemExit("fixture has no answers/*.json")
    for f in answers:
        extract.run(root, f.stem, model="fixture", chunk_words=12000, fixture=f, timeout=1)
    merge.run(root)
    score.run(root)
    build.run(root, root.site / "data.json")
    out = problems(root)
    before = snapshot(root.data)
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
