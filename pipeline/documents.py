"""Fold document ids that are one document under several titles into one id.

    uv run python -m pipeline.documents --fold [--root DIR]

data/document-folds.json is a list of groups, each `{ "canonical", "title", "members", "reason" }`
(schema.md, Document folds): the members are ids of one document (one text, one issuer, one date)
under other titles ("twining-memorandum" beside "twining-memo"), the canonical the id they become (one
of the corpus's or a new one), `title` the title as the page shows it, `reason` the evidence. merge
makes one document per title a teller gives, so one source counts as two credited documents, the
overlap rule (two stories that share a document) misses the stories that name it differently, and the
sources stage checks it under one id and leaves the others unsourced until folded.

`--fold` applies every group: in the stories a telling's `document` and every id in its `documents` take
the canonical id (`documents` deduplicated, so a telling that credited two members credits the canonical
once); in sources/manifests/*.json (not the `.images.json` beside them) an entry's `document.id`. The
member document files merge into the canonical's (created when absent): `title` from the group,
`attests` the union in order, every other field the one value the canonical and the members set (the
canonical's own, else a member's), and `aliases` the union of its own, the member ids, the members' own
aliases and the slugs of the group's title and of every old title (the canonical's id left out); the
member files are deleted. `common.document_aliases` reads those aliases, so merge maps a title whose
slug is an alias, and the sources stage a manifest id or title slug that is one, to the canonical, and a
later credit under any of the titles cannot bring a folded document back. The evidence files
sources/documents/<id>.txt follow: a member's file is renamed to the canonical's when the canonical has
none and it is the only one; files of one format are merged into one (passages appended under their
locators after the canonical's, a passage already held dropped; full texts kept when they read the same
and refused when they differ). Every group is checked before anything is written: it fails on a
malformed group, a member in two groups, a canonical in two groups, a member that is another group's
canonical, a canonical that an earlier fold made an alias of another document, a member an earlier fold
put into a document outside the group, two set values of one field (`date`, `url`, `issuer` and the
rest) among the canonical and the members (a person settles them by hand in the document files first),
an alias the fold would add that is a document outside the group, another document's alias, another
group's member or canonical, or another group's alias, a member with no document file and no reference
anywhere that no earlier fold absorbed, text files of two formats (a full text and passages) or of a
format the folded document does not keep (`sources.full_text`), two full texts that differ, and a story
that would hold the same (document, quote) twice. Idempotent: a second run changes nothing. Runs after
sources and beside `people --fold`, before score (the profile's documents are recomputed there).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import sources
from .common import REPO, SLUG_LIMIT, Root, is_document_id, load_json, rel, save_json, slugify
from .merge import same_telling

FOLD_KEYS = ("canonical", "title", "members", "reason")
EMPTY = (None, "", [])


def folds_path(root: Root) -> Path:
    return root.data / "document-folds.json"


def manifests_dir(root: Root) -> Path:
    return root.path / "sources" / "manifests"


def manifest_files(root: Root) -> list[Path]:
    """The source manifests the sources stage ingested, without the images manifests it writes beside them."""
    d = manifests_dir(root)
    return sorted(f for f in d.glob("*.json") if not f.name.endswith(".images.json")) if d.exists() else []


def group_problems(groups, where: str = "data/document-folds.json") -> list[str]:
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
        if not is_document_id(c):
            out.append(f"{gw}: canonical {c!r} is not a document id (a lowercase slug of at most {SLUG_LIMIT} characters)")
            continue
        gw = f"{where} group {i} ({c})"
        if not (isinstance(g["title"], str) and g["title"].strip()):
            out.append(f"{gw}: title must be a non-empty string")
        if not (isinstance(g["reason"], str) and g["reason"].strip()):
            out.append(f"{gw}: reason must be a non-empty string")
        if not (isinstance(members, list) and members and all(is_document_id(m) for m in members)):
            out.append(f"{gw}: members must be a non-empty list of document ids")
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


def load_folds(root: Root) -> list[dict]:
    """The groups of data/document-folds.json, checked; [] when the file is absent."""
    f = folds_path(root)
    if not f.exists():
        return []
    groups = load_json(f)
    bad = group_problems(groups, rel(f, root.path))
    if bad:
        raise SystemExit("documents: data/document-folds.json has problems:\n" + "\n".join(bad))
    return groups


def fold_map(groups: list[dict]) -> dict[str, str]:
    """{member id: canonical id} of the groups."""
    return {m: g["canonical"] for g in groups for m in g["members"]}


def load_manifests(root: Root) -> dict[Path, list]:
    out: dict[Path, list] = {}
    for f in manifest_files(root):
        entries = load_json(f)
        if not isinstance(entries, list):
            raise SystemExit(f"documents: {rel(f, root.path)} is not a list of manifest entries")
        out[f] = entries
    return out


def reference_sites(stories: dict, manifests: dict[Path, list], root: Path):
    """Every place the data names a document id outside the document files, as (id, where): a telling's
    `document` and `documents`, a manifest entry's `document.id`. The id may be None or not a string; the
    caller filters. `documents.run` and `check.py` both read this one list."""
    for sid, s in sorted(stories.items()):
        for i, t in enumerate(s.get("tellings") or []):
            for x in [t.get("document")] + list(t.get("documents") or []):
                yield x, f"story {sid} telling {i + 1}"
    for f, entries in manifests.items():
        for i, e in enumerate(entries):
            d = e.get("document") if isinstance(e, dict) else None
            if isinstance(d, dict):
                yield d.get("id"), f"{rel(f, root)} entry {i + 1}"


def references(stories: dict, manifests: dict[Path, list], root: Path) -> set[str]:
    return {x for x, _ in reference_sites(stories, manifests, root) if isinstance(x, str) and x}


def union(*lists) -> list:
    return list(dict.fromkeys(x for xs in lists for x in xs))


def merged_document(canonical: str, title: str, own: dict | None, members: list[dict]) -> tuple[dict, list[str]]:
    """(the canonical's document after the fold, the fields on which its sources disagree). A field is the first
    set value of the canonical then the members; two different set values are a conflict for a person to settle
    in the document files before folding. `aliases` gains the member ids, their aliases and the slugs of the
    group's title and of every old title, so merge maps any of those titles to the canonical."""
    base = own or {"id": canonical, "title": title, "issuer": None, "date": None, "url": None, "kind": None, "attests": []}
    docs = [base, *members]
    d = dict(base)
    d["title"] = title
    conflicts = []
    for k in union(*[list(x) for x in docs]):
        if k in ("id", "title", "aliases", "attests"):
            continue
        held = [(x["id"], x[k]) for x in docs if x.get(k) not in EMPTY]
        if len({repr(v) for _, v in held}) > 1:
            conflicts.append(f"{k} differs: " + ", ".join(f"{i} {v!r}" for i, v in held))
        if held:
            d[k] = held[0][1]
    d["attests"] = union(base.get("attests") or [], *[m.get("attests") or [] for m in members])
    titles = [slugify(t) for t in (title, *([own["title"]] if own else []), *[m["title"] for m in members])]
    aliases = union(base.get("aliases") or [], *[[m["id"], *(m.get("aliases") or [])] for m in members], titles)
    return {k: v for k, v in d.items() if k != "aliases"} | {"aliases": [a for a in aliases if a != canonical]}, conflicts


def fold_telling(t: dict, to: dict[str, str]) -> dict:
    new = dict(t)
    if new.get("document") in to:
        new["document"] = to[new["document"]]
    if "documents" in new:
        new["documents"] = union([to.get(d, d) for d in new["documents"]])
    return new


def text_plan(root: Root, c: str, merged: dict, ids: list[str], documents: dict) -> tuple[str | None, list[Path], str | None]:
    """(the canonical's text after the fold or None to leave it, the member files to remove, the refusal
    or None). `ids` are the canonical then the members; a member already folded has no file left."""
    files = [(i, sources.text_path(root, i)) for i in ids if sources.text_path(root, i).exists()]
    if not files:
        return None, [], None
    full = {}
    for i, f in files:
        if i not in documents and i != c:
            return None, [], f"{rel(f, root.path)} has no document in data/documents"
        full[i] = sources.full_text(documents.get(i) or merged)
    if len(set(full.values())) > 1:
        kinds = ", ".join(f"{i} {'full text' if v else 'passages'}" for i, v in full.items())
        return None, [], f"the text files are of two formats ({kinds}); a document keeps one"
    keeps_full = sources.full_text(merged)
    if next(iter(full.values())) != keeps_full:
        return None, [], (f"the text files hold {'a full text' if not keeps_full else 'passages'}, but the folded document keeps "
                          f"{'a full text' if keeps_full else 'passages'} (sources.full_text); correct its status or text_url")
    members = [f for i, f in files if i != c]
    if not members:
        return None, [], None
    texts = [sources.DocumentText.read(f, root.path, not keeps_full) for _, f in files]
    if keeps_full:
        if len({x.norm for x in texts}) > 1:
            return None, [], "two full texts that differ: " + ", ".join(rel(f, root.path) for _, f in files)
        body = files[0][1].read_text(encoding="utf-8")
    else:
        held = texts[0]
        for x in texts[1:]:
            held = sources.DocumentText(sources.passages_text(
                sources.merged_passages(held, [{"locator": loc, "text": p} for loc, p in x.passages])), True)
        body = sources.passages_text(held.passages)
    return body, members, None


def run(root: Root, echo=print) -> dict:
    groups = load_folds(root)
    stats = {"groups": len(groups), "documents_folded": 0, "documents_created": 0, "tellings": 0, "stories": 0,
             "manifest_entries": 0, "texts_moved": 0, "texts_merged": 0}
    if not groups:
        print("documents: no data/document-folds.json groups, nothing to fold", file=sys.stderr)
        return stats
    to = fold_map(groups)
    stories = root.load_dir(root.stories)
    documents = root.load_dir(root.documents)
    manifests = load_manifests(root)
    lines: list[str] = []

    # Every check before any write.
    absorbed = {a: did for did, d in documents.items() for a in d.get("aliases", [])}
    named = references(stories, manifests, root.path)
    bad: list[str] = []
    plans: dict[str, tuple] = {}
    canonicals = {g["canonical"] for g in groups}
    claimed: dict[str, str] = {}  # alias: the canonical a group gives it
    for g in groups:
        c = g["canonical"]
        own = {c, *g["members"]}  # an earlier fold into the canonical or into another member of the group
        if c in absorbed:
            bad.append(f"group {c}: the canonical was folded into {absorbed[c]!r} earlier (it is in that document's aliases)")
        for m in g["members"]:
            if m in absorbed and absorbed[m] not in own:
                bad.append(f"group {c}: member {m!r} was folded into {absorbed[m]!r} earlier")
            elif m not in documents and m not in named and m not in absorbed:
                bad.append(f"group {c}: member {m!r} has no document file and no reference anywhere (no telling or manifest names it)")
        members = [documents[m] for m in g["members"] if m in documents]
        merged, conflicts = merged_document(c, g["title"], documents.get(c), members)
        for x in conflicts:
            bad.append(f"group {c}: {x}; settle it by hand in data/documents before folding")
        for a in merged["aliases"]:
            if a in documents and a not in own:
                bad.append(f"group {c}: alias {a!r} is the document {a}, outside the group (from a title's slug); "
                           "make it a member or give the group another title")
            elif a in absorbed and absorbed[a] not in own:
                bad.append(f"group {c}: alias {a!r} is already an alias of {absorbed[a]!r}")
            elif to.get(a, c) != c or (a in canonicals and a != c):
                bad.append(f"group {c}: alias {a!r} is a member or the canonical of another group")
            elif claimed.setdefault(a, c) != c:
                bad.append(f"group {c}: alias {a!r} is also an alias group {claimed[a]} gives its canonical")
        body, gone, why = text_plan(root, c, merged, [c, *g["members"]], documents)
        if why:
            bad.append(f"group {c}: {why}")
        plans[c] = (members, merged, body, gone)
    folded: dict[str, list[dict]] = {}
    for sid, s in sorted(stories.items()):
        tellings = [fold_telling(t, to) for t in s["tellings"]]
        for i, a in enumerate(tellings):
            for j in range(i):
                if a.get("document") and same_telling(a, tellings[j]) and not same_telling(s["tellings"][i], s["tellings"][j]):
                    bad.append(f"story {sid}: tellings {j + 1} and {i + 1} would become the same telling of {a['document']} "
                               "(one quote, one document); drop one by hand first")
        folded[sid] = tellings
    if bad:
        raise SystemExit("documents: data/document-folds.json does not fit the data:\n" + "\n".join(bad))

    # Stories.
    for sid, s in sorted(stories.items()):
        changed = sum(a != b for a, b in zip(folded[sid], s["tellings"]))
        if changed:
            s["tellings"] = folded[sid]
            save_json(root.stories / f"{sid}.json", s)
            stats["tellings"] += changed
            stats["stories"] += 1

    # The source manifests.
    for f, entries in manifests.items():
        n = 0
        for e in entries:
            d = e.get("document") if isinstance(e, dict) else None
            if isinstance(d, dict) and d.get("id") in to:
                d["id"] = to[d["id"]]
                n += 1
        if n:
            save_json(f, entries)
            stats["manifest_entries"] += n

    # Document files and their texts.
    for g in groups:
        c = g["canonical"]
        members, merged, body, gone = plans[c]
        if c not in documents:
            stats["documents_created"] += 1
        if documents.get(c, {}).get("title") not in (None, merged["title"]):
            lines.append(f"title    {c}  {documents[c]['title']!r} becomes {merged['title']!r}")
        save_json(root.documents / f"{c}.json", merged)
        documents[c] = merged
        if body is not None:
            target = sources.text_path(root, c)
            if not target.exists() and len(gone) == 1:
                gone[0].rename(target)
                stats["texts_moved"] += 1
                lines.append(f"text     {c}  {rel(gone[0], root.path)} renamed")
            else:
                target.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
                for f in gone:
                    f.unlink()
                stats["texts_merged"] += 1
                lines.append(f"text     {c}  merged from {', '.join(rel(f, root.path) for f in gone)}")
        for m in members:
            (root.documents / f"{m['id']}.json").unlink()
            del documents[m["id"]]
            stats["documents_folded"] += 1
    for line in lines:
        echo(line)
    print("documents: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in stats.items()), file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fold", action="store_true", help="apply data/document-folds.json")
    ap.add_argument("--root", default=REPO)
    a = ap.parse_args(argv)
    if not a.fold:
        ap.error("say what to do: --fold")
    run(Root(a.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
