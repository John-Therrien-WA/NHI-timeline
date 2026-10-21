"""Candidates into stories.

    uv run python -m pipeline.merge [--root DIR]

Reads every data/candidates/<episode>.json, in episode date order then file order (the order
link.py links in, so a story a candidate creates exists before a later candidate's `same` names
it). A candidate whose telling (the same quote from the same
episode) a story already holds changes nothing but a missing place. A candidate with a `link`
(pipeline/link.py) follows it: `same` appends the telling to the linked story (an id that a fold
made an alias resolves to the story that absorbed it; an id that resolves to nothing fails) with
the link's `difference` and its reason as `link_reason`, and the candidate's own title, years,
place text and story kind as `as_told` when any of them differs from the story's; `variant` creates the story and a
`variant` relation both ways with the reason as the note; `new` creates the story (under the
link's `id`, the id link.py gave its provisional story; a mismatch fails). A candidate
without `link` becomes a new story unless an existing story has the same title slug (or holds it
as an alias), or shares a teller and has overlapping years, the same place and the same kind: then
a telling is added to that story. A new story whose slug is taken gets a numbered suffix. People are created under data/people/ as they are met (tellers and
the people a teller cites; a name is normalised, so "Jesse Michels (host)" is `jesse-michels`);
documents a teller credits are created under data/documents/ by title. A candidate's free-text
place is resolved to a place id through data/place-aliases.json (alias text to id) or a place name
contained in the text; the text itself is kept on the story as `place_text`. After the pass,
`related` gets a `same-event` link between two stories that share years, place and kind and are
not already related; every other relation is left for a person to add by hand. Idempotent: a
second run changes nothing. Hand edits are kept: an existing story is only appended to (its
`discussion` and every other field a person wrote stay as they are), and its
`place` and `place_text` are filled when they are missing or null and a candidate gives them,
never overwritten.
"""
from __future__ import annotations

import argparse
import re
import sys

from .link import add_relation, alias_map, as_told, candidate_files, framing_of_candidate, fresh_id, resolve
from .common import (REPO, Root, era_for, load_json, norm_ws, person_aliases, person_id, person_name, rel, save_json, slugify,
                     story_id)

MIN_ALIAS = 3  # a contained alias or name shorter than this (as words, "us") matches too much


def ensure_person(people: dict, name: str, role: str | None, aliases: dict[str, str]) -> str:
    """The person's id, creating the file's object when first met. An existing person is never changed.
    `aliases` is `person_aliases` of the run's root."""
    pid = person_id(name, aliases)
    if pid not in people:
        people[pid] = {"id": pid, "name": person_name(name), "roles": [role] if role else [], "affiliation": None,
                       "links": [], "note": "", "_new": True}
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


class PlaceResolver:
    """Free text to a place id: an exact alias or name, else the longest alias or place name that the
    text contains as whole words (case-insensitive); a tie between two places resolves to nothing."""

    def __init__(self, places: list[dict], aliases: dict[str, str]):
        ids = {p["id"] for p in places}
        self.exact: dict[str, str] = {}
        for p in places:
            self.exact[p["id"]] = p["id"]
            self.exact[norm_ws(p["name"]).lower()] = p["id"]
        for text, pid in aliases.items():
            if pid not in ids:
                raise SystemExit(f"place-aliases.json: {text!r} points at {pid!r}, which is not in places.json")
            key = norm_ws(text).lower()
            if not key:
                raise SystemExit("place-aliases.json: an empty alias")
            if self.exact.get(key, pid) != pid:
                raise SystemExit(f"place-aliases.json: {text!r} is already {self.exact[key]!r}")
            self.exact[key] = pid
        self.contained: list[tuple[re.Pattern, str, int]] = []
        keys = set(self.exact)
        for p in places:  # the part of a name before the comma (the town) also counts
            head = norm_ws(p["name"].split(",")[0]).lower()
            if head and head not in self.exact:
                keys.add(head)
                self.exact[head] = p["id"]
        for key in sorted(keys, key=len, reverse=True):
            if len(key) < MIN_ALIAS:
                continue
            self.contained.append((re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)"), self.exact[key], len(key)))

    def resolve(self, text) -> str | None:
        if not isinstance(text, str):
            return None
        t = norm_ws(text).lower()
        if not t:
            return None
        if t in self.exact:
            return self.exact[t]
        best, best_len, tie = None, 0, False
        for pat, pid, n in self.contained:
            if n < best_len:
                break
            if pat.search(t):
                if n > best_len:
                    best, best_len, tie = pid, n, False
                elif pid != best:
                    tie = True
        return None if tie else best


def load_aliases(root: Root) -> dict[str, str]:
    f = root.data / "place-aliases.json"
    if not f.exists():
        return {}
    data = load_json(f)
    if not isinstance(data, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in data.items()):
        raise SystemExit(f"{rel(f, root.path)}: must be an object of alias text to place id")
    return data


def find_story(stories: dict, aliases: dict, cand: dict, sid: str, teller: str) -> dict | None:
    if sid in stories:
        return stories[sid]
    if sid in aliases:
        return stories[aliases[sid]]
    for s in stories.values():
        if any(t.get("teller") == teller for t in s["tellings"]) and years_overlap(s.get("years"), cand["years"]) \
                and s.get("place") is not None and s.get("place") == cand["place"] and s.get("kind") == cand["story_kind"]:
            return s
    return None


def role_for(kind: str) -> str:
    return {"firsthand": "witness", "official": "official", "journalist": "journalist", "secondhand": "witness",
            "researcher": "researcher", "host": "host"}[kind]


def place_text_of(cand: dict) -> str | None:
    t = cand.get("place_text")
    return norm_ws(t) if isinstance(t, str) and t.strip() else None


def telling_from(cand: dict, episode_id: str, teller: str, cites: list[str], docs: list[str]) -> dict:
    return {"episode": episode_id, "from_s": cand["from_s"], "to_s": cand["to_s"], "teller": teller,
            "quote": cand["quote"], "kind": cand["kind"], "cites": cites, "documents": docs}


def same_telling(a: dict, b: dict) -> bool:
    """The same words from the same episode (or document) are one telling, whatever the teller was called."""
    return a.get("episode") == b.get("episode") and a.get("document") == b.get("document") \
        and norm_ws(a.get("quote") or "") == norm_ws(b.get("quote") or "")


def run(root: Root, episodes_only: list[str] | None = None) -> dict:
    """`episodes_only` restricts the pass to those candidate files (the rebuild links and merges one episode at a time)."""
    eras, places = root.eras(), root.places()
    resolver = PlaceResolver(places, load_aliases(root))
    stories = root.load_dir(root.stories)
    people = root.load_dir(root.people)
    documents = root.load_dir(root.documents)
    episodes = root.load_dir(root.episodes)
    names = person_aliases(root.path)
    for s in stories.values():
        if "tellings" not in s or "related" not in s:
            raise SystemExit(f"story {s['id']} lacks tellings or related")
    stats = {"stories": 0, "tellings": 0, "people": 0, "documents": 0, "places_filled": 0, "same_event": 0}
    work: list[tuple] = []  # (file, episode id, candidate) in episode date order
    for f in candidate_files(root, episodes_only):
        batch = load_json(f)
        eid = batch.get("episode")
        if eid not in episodes:
            raise SystemExit(f"{rel(f, root.path)}: episode {eid!r} has no data/episodes file")
        work.extend((f, eid, cand) for cand in batch["candidates"])
    # A resumed link run may join a candidate to a story that a later candidate of the pass creates (the
    # provisional story stood when the join was decided). Such a candidate waits for its story; one whose
    # story nothing in the pass creates still fails loudly.
    created_later = {c["link"]["id"] for _, _, c in work if c.get("link") and c["link"].get("id")}
    strict = False  # set when a pass deferred everything: the next pass takes the loud error instead of waiting
    while work:
        deferred: list[tuple] = []
        for f, eid, cand in work:
            cand = dict(cand)
            cand["place"] = resolver.resolve(cand.get("place_text"))
            teller = ensure_person(people, cand["teller"], role_for(cand["kind"]), names)
            cites = [ensure_person(people, n, None, names) for n in cand["cites"]]
            cites = [c for c in dict.fromkeys(cites) if c != teller]
            docs = list(dict.fromkeys(ensure_document(documents, t) for t in cand["documents"]))
            sid = story_id(cand["title"], cand["years"])
            telling = telling_from(cand, eid, teller, cites, docs)
            aliases = alias_map(stories)
            link = cand.get("link")
            held = next((s for s in stories.values() if any(same_telling(telling, t) for t in s["tellings"])), None)
            waits_for = link.get("story") if held is None and link and link["decision"] in ("same", "variant") else None
            if waits_for is not None and resolve(waits_for, stories, aliases) is None and waits_for in created_later and not strict:
                deferred.append((f, eid, cand))
                continue
            if held is not None:
                story = held
            elif link is None:
                story = find_story(stories, aliases, cand, sid, teller)
            elif link["decision"] == "same":
                target = resolve(link.get("story"), stories, aliases)
                if target is None:
                    raise SystemExit(f"{rel(f, root.path)}: {cand['title']!r} is linked same to {link.get('story')!r}, which is no story or alias")
                story = stories[target]
                telling["difference"] = link["difference"]
                telling["link_reason"] = link["reason"]
                told = as_told(framing_of_candidate(cand), story)
                if told:
                    telling["as_told"] = told
            elif link["decision"] in ("variant", "new"):
                story = None
                if link["decision"] == "variant" and resolve(link.get("story"), stories, aliases) is None:
                    raise SystemExit(f"{rel(f, root.path)}: {cand['title']!r} is linked variant to {link.get('story')!r}, which is no story or alias")
                sid = fresh_id(sid, stories, aliases)
                if link.get("id") not in (None, sid):
                    raise SystemExit(f"{rel(f, root.path)}: {cand['title']!r} was linked as story {link['id']!r} but would merge "
                                     f"as {sid!r}: link and merge saw different stories (link and merge the same episodes, in order)")
            else:
                raise SystemExit(f"{rel(f, root.path)}: {cand['title']!r}: link decision {link.get('decision')!r} is not same, variant or new")
            if story is None:
                story = {
                    "id": sid, "title": cand["title"],
                    "era": era_for(cand["years"], eras), "years": cand["years"],
                    "place": cand["place"], "place_text": place_text_of(cand), "coordinates": None,
                    "kind": cand["story_kind"], "claims": [], "tellings": [telling], "related": [], "tags": [], "score": None,
                }
                stories[sid] = story
                stats["stories"] += 1
                stats["tellings"] += 1
                if link is not None and link["decision"] == "variant":
                    other = stories[resolve(link["story"], stories, aliases)]
                    add_relation(story, other["id"], "variant", link["reason"])
                    add_relation(other, sid, "variant", link["reason"])
            else:
                if not any(same_telling(telling, t) for t in story["tellings"]):
                    story["tellings"].append(telling)
                    stats["tellings"] += 1
                if story.get("place_text") is None and place_text_of(cand):
                    story["place_text"] = place_text_of(cand)
                if story.get("place") is None and cand["place"] is not None:
                    story["place"] = cand["place"]
                    stats["places_filled"] += 1
        strict = len(deferred) == len(work)
        work = deferred
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
    print("merge: " + ", ".join(f"{v} {'new ' if k != 'places_filled' else ''}{k.replace('_', ' ')}" for k, v in stats.items()), file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episodes", nargs="*", help="candidate files to merge (default: every one)")
    ap.add_argument("--root", default=REPO)
    a = ap.parse_args(argv)
    run(Root(a.root), a.episodes or None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
