"""Fold person ids that are one person under several spellings into one id.

    uv run python -m pipeline.people --fold [--root DIR]

data/person-folds.json is `{ "groups", "distinct" }` (schema.md, Person folds). `groups` is a list
of groups, each `{ "canonical", "name", "members", "reason" }`: the members are ids of one person
under other spellings ("warner-von-braun" beside "wernher-von-braun"), the canonical the id they
become (one of the corpus's or a new one), `name` the name as the page shows it, `reason` the
evidence. Captions spell a name several ways and merge makes one id per spelling, so one teller
counts as two independent tellers until folded. `distinct` is a list of `{ "pair", "reason" }`: two
person ids judged to be two people although their spellings are close ("scott-kelly" beside
"scott-pelley"), which check.py then no longer warns about; an id in a pair is a person (a person
file, or a canonical the fold creates) and a member of no group, refused by name otherwise. The
fold itself never reads `distinct`.

`--fold` applies every group: in the stories a telling's `teller`, `teller_was` and `cites` take the
canonical id (cites deduplicated, a cite of the telling's own teller dropped, the teller as extracted,
which is `teller_was` on a replay, and a telling the clips
stage marked is put back as data/clips.json makes it, so a `teller_was` that became its own speaker
goes); in data/clips.json a group's `speaker` (its `speaker_name` the group's name) and `also_heard`
(deduplicated, the speaker left out); in data/episodes a `host` or guest given as a member id; in
the image sidecars the `person` of a person picture; a member's headshot directory
(data/images/<member>/ and site/images/<member>/) moves under the canonical at its next free numbers,
a picture whose `image_url` the canonical already holds dropped. The member person files are merged
into the canonical's (created when absent): `name` from the group, `roles` and `links` the union in
order, `affiliation` and `note` the canonical's when set, else the first member's that is set, and
`aliases` the union of its own, the member ids and the members' own aliases; the member files are deleted. Each member's name
(and the member id itself when its name's key is another) is added to data/person-aliases.json
pointing at the canonical, so the next merge maps the spelling at once, and an alias that pointed at
a member points at the canonical. Every group is checked before anything is written: it fails on a
malformed group, a member in two groups, a member that is another group's canonical, a canonical
that an earlier fold made an alias of another person, a member an earlier fold put into a person
outside the group, a member with no person file and no reference anywhere that no earlier fold
absorbed, and a member headshot whose file is missing under site/. Idempotent: a second run changes
nothing. Runs after clips and before score (the profile's tellers are recomputed there).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import clips, images
from .common import REPO, Root, load_json, name_key, raw_person_aliases, rel, save_json

FILE_KEYS = ("groups", "distinct")
FOLD_KEYS = ("canonical", "name", "members", "reason")
DISTINCT_KEYS = ("pair", "reason")
PERSON_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")
PERSON_ORDER = ("id", "name", "roles", "affiliation", "links", "note", "aliases")


def folds_path(root: Root) -> Path:
    return root.data / "person-folds.json"


def group_problems(groups, where: str = "data/person-folds.json") -> list[str]:
    """The file's shape and the rules across groups; [] when it is sound. Needs no other data."""
    if not isinstance(groups, list):
        return [f"{where}: must be a list of groups"]
    out: list[str] = []
    member_of: dict[str, int] = {}
    canonical_of: dict[str, int] = {}
    for i, g in enumerate(groups, 1):
        gw = f"{where} group {i}"
        if not isinstance(g, dict) or set(g) != set(FOLD_KEYS):
            out.append(f"{gw}: must be an object with exactly {', '.join(FOLD_KEYS)}")
            continue
        c, members = g["canonical"], g["members"]
        if not (isinstance(c, str) and PERSON_ID.fullmatch(c)):
            out.append(f"{gw}: canonical {c!r} is not a person id (a lowercase slug)")
            continue
        gw = f"{where} group {i} ({c})"
        if not (isinstance(g["name"], str) and g["name"].strip()):
            out.append(f"{gw}: name must be a non-empty string")
        if not (isinstance(g["reason"], str) and g["reason"].strip()):
            out.append(f"{gw}: reason must be a non-empty string")
        if not (isinstance(members, list) and members and all(isinstance(m, str) and PERSON_ID.fullmatch(m) for m in members)):
            out.append(f"{gw}: members must be a non-empty list of person ids")
            continue
        if len(set(members)) != len(members):
            out.append(f"{gw}: a member is listed twice")
        if c in members:
            out.append(f"{gw}: the canonical is also one of its members")
        if c in canonical_of:
            out.append(f"{gw}: canonical {c!r} is also the canonical of group {canonical_of[c]}; make them one group")
        canonical_of.setdefault(c, i)
        for m in members:
            if m in member_of and member_of[m] != i:
                out.append(f"{gw}: member {m!r} is also a member of group {member_of[m]}")
            member_of.setdefault(m, i)
    for m, i in sorted(member_of.items()):
        if m in canonical_of and canonical_of[m] != i:
            out.append(f"{where} group {i}: member {m!r} is the canonical of group {canonical_of[m]}; fold the chain into one group")
    return out


def distinct_problems(distinct, groups, where: str = "data/person-folds.json") -> list[str]:
    """The `distinct` list's shape, and no id in a pair a member of a group; [] when it is sound. `groups` may
    be malformed (group_problems names that); only its well-formed members are read."""
    if not isinstance(distinct, list):
        return [f"{where}: distinct must be a list of pairs"]
    member_of = {m: (i, g["canonical"]) for i, g in enumerate(groups if isinstance(groups, list) else [], 1)
                 if isinstance(g, dict) and isinstance(g.get("members"), list)
                 for m in g["members"] if isinstance(m, str)}
    out: list[str] = []
    seen: dict[frozenset, int] = {}
    for i, d in enumerate(distinct, 1):
        dw = f"{where} distinct pair {i}"
        if not isinstance(d, dict) or set(d) != set(DISTINCT_KEYS):
            out.append(f"{dw}: must be an object with exactly {', '.join(DISTINCT_KEYS)}")
            continue
        pair = d["pair"]
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, str) and PERSON_ID.fullmatch(x) for x in pair)
                and pair[0] != pair[1]):
            out.append(f"{dw}: pair must be two different person ids, got {pair!r}")
            continue
        dw = f"{dw} ({pair[0]}, {pair[1]})"
        if not (isinstance(d["reason"], str) and d["reason"].strip()):
            out.append(f"{dw}: reason must be a non-empty string")
        key = frozenset(pair)
        if key in seen:
            out.append(f"{dw}: the pair is also distinct pair {seen[key]}")
        seen.setdefault(key, i)
        for x in pair:
            if x in member_of:
                j, c = member_of[x]
                out.append(f"{dw}: {x!r} is a member of group {j} ({c}), which folds it; a folded id is not distinct")
    return out


def distinct_person_problems(distinct: list[dict], persons: set[str], where: str = "data/person-folds.json") -> list[str]:
    """Each id of a well-formed `distinct` list is one of `persons` (the person ids, plus the canonicals a fold
    about to run creates)."""
    return [f"{where} distinct pair {i} ({d['pair'][0]}, {d['pair'][1]}): {x!r} is no person (no data/people/{x}.json)"
            for i, d in enumerate(distinct, 1) for x in d["pair"] if x not in persons]


def fold_file_problems(doc, where: str = "data/person-folds.json") -> list[str]:
    """The whole file's shape: groups and distinct, and the rules across them; [] when it is sound."""
    if not isinstance(doc, dict) or set(doc) != set(FILE_KEYS):
        return [f"{where}: must be an object with exactly {', '.join(FILE_KEYS)}"]
    return group_problems(doc["groups"], where) + distinct_problems(doc["distinct"], doc["groups"], where)


def load_fold_file(root: Root) -> dict:
    """data/person-folds.json, checked; no groups and no distinct pairs when the file is absent."""
    f = folds_path(root)
    if not f.exists():
        return {"groups": [], "distinct": []}
    doc = load_json(f)
    bad = fold_file_problems(doc, rel(f, root.path))
    if bad:
        raise SystemExit("people: data/person-folds.json has problems:\n" + "\n".join(bad))
    return doc


def distinct_pairs(doc: dict) -> set[frozenset]:
    """The judged pairs of the file, each as a frozenset of its two ids."""
    return {frozenset(d["pair"]) for d in doc["distinct"]}


def fold_map(groups: list[dict]) -> dict[str, str]:
    """{member id: canonical id} of the groups."""
    return {m: g["canonical"] for g in groups for m in g["members"]}


def reference_sites(stories: dict, episodes: dict, clip_groups: list, sidecars: dict, aliases: dict):
    """Every place the data names a person id outside the person files, as (id, where): a telling's
    teller, teller_was and cites, a story's profile, an episode's host and guests, a clip's speaker and
    also_heard, an image directory and a person picture, an alias target. The id may be None or not a
    string; the caller filters. `people.run` and `check.py` both read this one list."""
    for sid, s in sorted(stories.items()):
        for i, t in enumerate(s.get("tellings") or []):
            for x in [t.get("teller"), t.get("teller_was")] + list(t.get("cites") or []):
                yield x, f"story {sid} telling {i + 1}"
        for x in (s.get("profile") or {}).get("tellers") or []:
            yield x, f"story {sid} profile (run pipeline.score)"
    for eid, e in sorted(episodes.items()):
        for x in [e.get("host")] + list(e.get("guests") or []):
            yield x, f"episode {eid}"
    for g in clip_groups:
        for x in [g.get("speaker")] + list(g.get("also_heard") or []):
            yield x, f"data/clips.json group {g.get('id')}"
    for owner, rows in sorted(sidecars.items()):
        yield owner, f"data/images/{owner}"
        for n, sc in rows:
            yield sc.get("person"), f"data/images/{owner}/{n}.json"
    for text, pid in sorted(aliases.items()):
        yield pid, f"person-aliases.json {text!r}"


def references(stories: dict, episodes: dict, clip_groups: list, sidecars: dict, aliases: dict) -> set[str]:
    """Every person id the data names outside the person files."""
    return {x for x, _ in reference_sites(stories, episodes, clip_groups, sidecars, aliases) if isinstance(x, str) and x}


def union(*lists) -> list:
    return list(dict.fromkeys(x for xs in lists for x in xs))


def merged_person(canonical: str, name: str, own: dict | None, members: list[dict]) -> dict:
    base = own or {"id": canonical, "roles": [], "affiliation": None, "links": [], "note": ""}
    p = dict(base)
    p["name"] = name
    p["roles"] = union(base.get("roles") or [], *[m.get("roles") or [] for m in members])
    p["links"] = union(base.get("links") or [], *[m.get("links") or [] for m in members])
    for k in ("affiliation", "note"):
        if not base.get(k):
            p[k] = next((m[k] for m in members if m.get(k)), base.get(k))
    p["aliases"] = union(base.get("aliases") or [], *[[m["id"], *(m.get("aliases") or [])] for m in members])
    ordered = {k: p[k] for k in PERSON_ORDER if k in p}
    return {**ordered, **{k: v for k, v in p.items() if k not in ordered}}


def fold_telling(t: dict, to: dict[str, str], groups: list[dict]) -> dict:
    new = dict(t)
    for k in ("teller", "teller_was"):
        if new.get(k) in to:
            new[k] = to[new[k]]
    if "cites" in new:
        own = new.get("teller_was") or new.get("teller")  # the cites are the extracted teller's credits
        new["cites"] = [c for c in union([to.get(c, c) for c in new["cites"]]) if c != own]
    if new.get("episode") and ("replay_of" in new or "teller_was" in new):
        new = clips.corrected(new, groups)
    return new


def fold_clip(g: dict, to: dict[str, str], names: dict[str, str]) -> dict:
    new = dict(g)
    if new.get("speaker") in to:
        new["speaker"] = to[new["speaker"]]
        new["speaker_name"] = names[new["speaker"]]
    if new.get("also_heard"):
        new["also_heard"] = [p for p in union([to.get(p, p) for p in new["also_heard"]]) if p != new.get("speaker")]
    return new


def plan_aliases(raw: dict, to: dict[str, str], groups: list[dict], people: dict, where: str) -> dict:
    """data/person-aliases.json after the fold: targets that were members repointed, each member's name
    (and its id, when the name's key is another) and the group's name pointing at the canonical."""
    out = {text: to.get(pid, pid) for text, pid in raw.items()}
    keys = {name_key(text): pid for text, pid in out.items()}
    for g in groups:
        c = g["canonical"]
        texts = [g["name"]]
        for m in g["members"]:
            if m in people:
                texts.append(people[m]["name"])
            texts.append(m)
        for text in texts:
            k = name_key(text)
            if k == c:
                continue  # the canonical's own spelling needs no alias, and an alias may not be a target
            if k in keys:
                if keys[k] != c:
                    raise SystemExit(f"people: {where}: {text!r} already points at {keys[k]!r}, not {c!r}; "
                                     "correct the alias or the group")
                continue
            out[text] = c
            keys[k] = c
    return out


def run(root: Root) -> dict:
    doc = load_fold_file(root)
    groups = doc["groups"]
    stats = {"groups": len(groups), "people_folded": 0, "people_created": 0, "tellings": 0, "clips": 0,
             "episodes": 0, "sidecars": 0, "headshots_moved": 0, "headshots_dropped": 0, "aliases_added": 0}
    people = root.load_dir(root.people)
    bad = distinct_person_problems(doc["distinct"], set(people) | {g["canonical"] for g in groups},
                                   rel(folds_path(root), root.path))
    if bad:
        raise SystemExit("people: data/person-folds.json does not fit the data:\n" + "\n".join(bad))
    if not groups:
        print("people: no data/person-folds.json groups, nothing to fold", file=sys.stderr)
        return stats
    to = fold_map(groups)
    names = {g["canonical"]: g["name"] for g in groups}
    stories = root.load_dir(root.stories)
    episodes = root.load_dir(root.episodes)
    ledger = clips.load_ledger(root)
    sidecars = images.load_sidecars(root)
    aliases_file = root.data / "person-aliases.json"
    raw_aliases = raw_person_aliases(root.path)

    # Every check before any write.
    absorbed = {a: pid for pid, p in people.items() for a in p.get("aliases", [])}
    named = references(stories, episodes, ledger.get("groups", []), sidecars, raw_aliases)
    bad: list[str] = []
    for g in groups:
        c = g["canonical"]
        own = {c, *g["members"]}  # an earlier fold into the canonical or into another member of the group
        if c in absorbed:
            bad.append(f"group {c}: the canonical was folded into {absorbed[c]!r} earlier (it is in that person's aliases)")
        for m in g["members"]:
            if m in absorbed and absorbed[m] not in own:
                bad.append(f"group {c}: member {m!r} was folded into {absorbed[m]!r} earlier")
            elif m not in people and m not in named and m not in absorbed:
                bad.append(f"group {c}: member {m!r} has no person file and no reference anywhere (no telling, cite, clip, "
                           "episode, image or alias names it)")
        for owner in (m for m in g["members"] if m in sidecars):
            for n, sc in sidecars[owner]:
                f = sc.get("file")
                if not (isinstance(f, str) and (root.site / f).exists()):
                    bad.append(f"group {c}: member headshot data/images/{owner}/{n}.json: its file {f!r} is missing under site/")
    if bad:
        raise SystemExit("people: data/person-folds.json does not fit the data:\n" + "\n".join(bad))
    new_aliases = plan_aliases(raw_aliases, to, groups, people, rel(aliases_file, root.path))

    # Stories.
    clip_groups = [fold_clip(g, to, names) for g in ledger.get("groups", [])]
    for sid, s in sorted(stories.items()):
        tellings = [fold_telling(t, to, clip_groups) for t in s["tellings"]]
        changed = sum(a != b for a, b in zip(tellings, s["tellings"]))
        if changed:
            s["tellings"] = tellings
            save_json(root.stories / f"{sid}.json", s)
            stats["tellings"] += changed

    # The clips ledger.
    if ledger.get("groups"):
        stats["clips"] = sum(a != b for a, b in zip(clip_groups, ledger["groups"]))
        if stats["clips"]:
            save_json(clips.ledger_path(root), {**ledger, "groups": clip_groups})

    # Episodes: a host or guest given as a member id.
    for eid, e in sorted(episodes.items()):
        host = to.get(e.get("host"), e.get("host"))
        guests = union([to.get(x, x) for x in e.get("guests") or []])
        if host != e.get("host") or guests != (e.get("guests") or []):
            e["host"] = host
            if "guests" in e:
                e["guests"] = guests
            save_json(root.episodes / f"{eid}.json", e)
            stats["episodes"] += 1

    # Image sidecars: a person picture's `person`, then the members' headshot directories.
    data_dir, site_dir = images.images_dir(root), images.site_images_dir(root)
    for owner, rows in sorted(sidecars.items()):
        for n, sc in rows:
            if sc.get("person") in to:
                sc["person"] = to[sc["person"]]
                save_json(data_dir / owner / f"{n}.json", sc)
                stats["sidecars"] += 1
    for owner in sorted(o for o in sidecars if o in to):
        c = to[owner]
        held = {sc.get("image_url") for _, sc in sidecars.get(c, [])}
        nxt = max((n for n, _ in sidecars.get(c, [])), default=0) + 1
        for n, sc in sidecars[owner]:
            src_json = data_dir / owner / f"{n}.json"
            src_file = root.site / sc["file"]  # checked before any write
            if sc.get("image_url") in held:
                src_json.unlink()
                src_file.unlink()
                stats["headshots_dropped"] += 1
                continue
            new = {**sc, "file": f"images/{c}/{nxt}{src_file.suffix}"}
            dst_file = root.site / new["file"]
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            src_file.rename(dst_file)
            save_json(data_dir / c / f"{nxt}.json", new)
            src_json.unlink()
            sidecars.setdefault(c, []).append((nxt, new))
            held.add(sc.get("image_url"))
            nxt += 1
            stats["headshots_moved"] += 1
        for d in (data_dir / owner, site_dir / owner):
            if d.exists() and not any(x for x in d.iterdir() if not x.name.startswith(".")):
                for x in d.iterdir():
                    x.unlink()
                d.rmdir()

    # Person files, then the aliases.
    for g in groups:
        c = g["canonical"]
        members = [people[m] for m in g["members"] if m in people]
        merged = merged_person(c, g["name"], people.get(c), members)
        if c not in people:
            stats["people_created"] += 1
        save_json(root.people / f"{c}.json", merged)
        people[c] = merged
        for m in members:
            (root.people / f"{m['id']}.json").unlink()
            del people[m["id"]]
            stats["people_folded"] += 1
    stats["aliases_added"] = len(set(new_aliases) - set(raw_aliases))
    if new_aliases != raw_aliases:
        save_json(aliases_file, new_aliases)
    print("people: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in stats.items()), file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fold", action="store_true", help="apply data/person-folds.json")
    ap.add_argument("--root", default=REPO)
    a = ap.parse_args(argv)
    if not a.fold:
        ap.error("say what to do: --fold")
    run(Root(a.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
