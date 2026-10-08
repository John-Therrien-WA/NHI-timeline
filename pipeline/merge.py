"""Candidates into stories.

    uv run python -m pipeline.merge [--root DIR]

Reads every data/candidates/<episode>.json. Each candidate becomes a new story under data/stories/
unless an existing story has the same title slug, or shares a teller and has overlapping years, the
same place and the same kind: then a telling is added to that story. People are created under data/people/ as
they are met (tellers and the people a teller cites); documents a teller credits are created under
data/documents/ by title. After the pass, `related` gets a `same-event` link between two stories
that share years, place and kind and are not already related; every other relation is left for a
person to add by hand. Idempotent: a second run changes nothing. Hand edits are kept: a story is
only ever appended to.
"""
from __future__ import annotations

import argparse
import sys

from .common import REPO, Root, era_for, load_json, place_for, rel, save_json, slugify, story_id


def person_id(name: str) -> str:
    return slugify(name, 40)


def ensure_person(people: dict, name: str, role: str | None) -> str:
    """The person's id, creating the file's object when first met. An existing person is never changed."""
    pid = person_id(name)
    if pid not in people:
        people[pid] = {"id": pid, "name": name, "roles": [role] if role else [], "affiliation": None, "links": [], "note": "",
                       "_new": True}
    return pid


def ensure_document(documents: dict, title: str) -> str:
    did = slugify(title)
    if did not in documents:
        documents[did] = {"id": did, "title": title, "issuer": None, "date": None, "url": None, "kind": None,
                          "attests": [], "_new": True}
    return did


def years_overlap(a: dict | None, b: dict | None) -> bool:
    if not a or not b or a.get("from") is None or b.get("from") is None:
        return False
    return a["from"] <= b["to"] and b["from"] <= a["to"]


def find_story(stories: dict, cand: dict, sid: str, teller: str) -> dict | None:
    if sid in stories:
        return stories[sid]
    for s in stories.values():
        if any(t.get("teller") == teller for t in s["tellings"]) and years_overlap(s.get("years"), cand["years"]) \
                and s.get("place") is not None and s.get("place") == cand["place"] and s.get("kind") == cand["story_kind"]:
            return s
    return None


def role_for(kind: str) -> str:
    return {"firsthand": "witness", "official": "official", "journalist": "journalist", "secondhand": "witness",
            "researcher": "researcher", "host": "host"}[kind]


def summary_for(cand: dict, teller_name: str, place_name: str | None) -> str:
    when = cand["years_text"] if isinstance(cand["years_text"], str) and cand["years_text"].strip() else "an unknown time"
    where = place_name or (cand["place_text"] if isinstance(cand["place_text"], str) and cand["place_text"].strip() else "an unknown place")
    how = {"firsthand": "says they saw it or took part", "official": "reads it from an official document",
           "journalist": "reports it citing named sources", "secondhand": "relays what a named person told them",
           "researcher": "summarises it without a named source", "host": "frames it as the host"}[cand["kind"]]
    return f"{teller_name} tells of {cand['title']}, about {when} at {where}, and {how}. As told, not a fact."


def telling_from(cand: dict, episode_id: str, teller: str, cites: list[str], docs: list[str]) -> dict:
    return {"episode": episode_id, "from_s": cand["from_s"], "to_s": cand["to_s"], "teller": teller,
            "quote": cand["quote"], "kind": cand["kind"], "cites": cites, "documents": docs}


def same_telling(a: dict, b: dict) -> bool:
    return a.get("episode") == b.get("episode") and a.get("teller") == b.get("teller") and a.get("quote") == b.get("quote")


def run(root: Root) -> dict:
    eras, places = root.eras(), root.places()
    place_names = {p["id"]: p["name"] for p in places}
    stories = root.load_dir(root.stories)
    people = root.load_dir(root.people)
    documents = root.load_dir(root.documents)
    episodes = root.load_dir(root.episodes)
    for s in stories.values():
        if "tellings" not in s or "related" not in s:
            raise SystemExit(f"story {s['id']} lacks tellings or related")
    stats = {"stories": 0, "tellings": 0, "people": 0, "documents": 0, "same_event": 0}
    for f in sorted(root.candidates.glob("*.json")):
        batch = load_json(f)
        eid = batch.get("episode")
        if eid not in episodes:
            raise SystemExit(f"{rel(f, root.path)}: episode {eid!r} has no data/episodes file")
        for cand in batch["candidates"]:
            cand = dict(cand)
            cand["place"] = place_for(cand.get("place_text"), places)
            teller = ensure_person(people, cand["teller"], role_for(cand["kind"]))
            cites = [ensure_person(people, n, None) for n in cand["cites"]]
            cites = [c for c in dict.fromkeys(cites) if c != teller]
            docs = list(dict.fromkeys(ensure_document(documents, t) for t in cand["documents"]))
            sid = story_id(cand["title"], cand["years"])
            story = find_story(stories, cand, sid, teller)
            telling = telling_from(cand, eid, teller, cites, docs)
            if story is None:
                story = {
                    "id": sid, "title": cand["title"],
                    "summary": summary_for(cand, people[teller]["name"], place_names.get(cand["place"])),
                    "era": era_for(cand["years"], eras), "years": cand["years"], "place": cand["place"], "coordinates": None,
                    "kind": cand["story_kind"], "claims": [], "tellings": [telling], "related": [], "tags": [], "score": None,
                }
                stories[sid] = story
                stats["stories"] += 1
                stats["tellings"] += 1
            elif not any(same_telling(telling, t) for t in story["tellings"]):
                story["tellings"].append(telling)
                stats["tellings"] += 1
    # same-event links: shared years, place and kind, no relation yet in either direction
    ids = sorted(stories)
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            sa, sb = stories[a], stories[b]
            if sa.get("kind") is None or sa.get("kind") != sb.get("kind"):
                continue
            if sa.get("place") is None or sa.get("place") != sb.get("place") or not sa.get("years") or sa["years"] != sb.get("years"):
                continue
            if any(r.get("story") == b for r in sa["related"]) or any(r.get("story") == a for r in sb["related"]):
                continue
            sa["related"].append({"story": b, "relation": "same-event", "note": "same years, place and kind (merge)"})
            sb["related"].append({"story": a, "relation": "same-event", "note": "same years, place and kind (merge)"})
            stats["same_event"] += 1
    for s in stories.values():
        save_json(root.stories / f"{s['id']}.json", s)
    for p in people.values():
        if p.pop("_new", False):
            stats["people"] += 1
        save_json(root.people / f"{p['id']}.json", p)
    for d in documents.values():
        if d.pop("_new", False):
            stats["documents"] += 1
        save_json(root.documents / f"{d['id']}.json", d)
    print("merge: " + ", ".join(f"{v} new {k.replace('_', ' ')}" for k, v in stats.items()), file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=REPO)
    a = ap.parse_args(argv)
    run(Root(a.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
