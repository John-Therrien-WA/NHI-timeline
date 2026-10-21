"""Data to site/data.json (and site/data.js, the same object for a page opened from disk), and the
plain tellings to site/plain.json and site/plain.js.

    uv run python -m pipeline.build [--root DIR] [--out site/data.json]

The plain file is an object of story id to its plain telling (a story without one, before
pipeline.explain has run, is absent), written beside the data file as `plain.json` and `plain.js`
(`window.NHI_PLAIN`), whatever the data file's name; the page loads it after its first draw. The
data file holds stories with era, place (and the free place text for the unresolved), years, score, attestation, tier, evidence profile and the
repetition count, tellings with quotes and time codes and the YouTube URL at that second, the
documents, the alias map (an old id a fold retired to the story that absorbed it, so `#story=<old
id>` still resolves), the links between stories (shared document and every `related` relation, in the
top-level `links` list only: a story's own `related` list is not repeated), the count of
other stories told by each of a story's tellers (`shared_teller`, by teller and in all: a count,
never a link, since one host telling fifty stories would link every story to every other), the
story's `discussion` (the debunk, rebunk and note entries, an empty list when it has none; an
entry with an episode also gets the YouTube `url` at its `time`) and `notes_open` (the open entries of data/notes/<id>.json and of the notes files of its
aliases, 0 when there are none), the story's `images` (the object and place photographs of
data/images/<id> and of its aliases' directories, an empty list when it has none), each person's
`aliases` (the ids `pipeline.people --fold` folded into them, an empty list when none) and `image` (the
first headshot, or null), the
axes, the corpus date (the latest episode published), and beside the stories the scoring block
(weights, the institutional-trust knob, the median floor and median, the tier counts) so the page
can recompute each story's attestation from its `profile` at another knob value. A telling carries
what the page shows (the episode id, the time codes and URL, the teller, the quote, the kind, what it
cites and the `difference`); the episode's show, title and date come from the `episodes` map, and the
link's `link_reason` and `as_told` stay in the story file. All four files are written compact, with no
indentation, so the whole corpus fits the 16 MB a published artifact allows a file. Fails when a story
has no score, profile or tier: run pipeline.score first.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import images
from .common import REPO, Root, rel, seconds
from .score import attest


def url_at(episode: dict, from_s: float | None) -> str | None:
    url = episode.get("url")
    if not url:
        return None
    if from_s is None:
        return url
    return f"{url}{'&' if '?' in url else '?'}t={int(from_s)}"


def run(root: Root, out: Path) -> dict:
    stories = root.load_dir(root.stories)
    people = root.load_dir(root.people)
    episodes = root.load_dir(root.episodes)
    documents = root.load_dir(root.documents)
    if not stories:
        raise SystemExit("build: no stories under data/stories")
    scores = root.data / "scores.json"
    if not scores.exists():
        raise SystemExit("build: data/scores.json is missing: run pipeline.score first")
    summary = json.loads(scores.read_text(encoding="utf-8"))
    owner = root.story_aliases(stories)
    notes_open: dict[str, int] = {}
    for key, entries in root.load_notes().items():
        sid = key if key in stories else owner.get(key)
        if sid is None:
            raise SystemExit(f"build: data/notes/{key}.json names no story or alias")
        notes_open[sid] = notes_open.get(sid, 0) + sum(e["status"] == "open" for e in entries)
    story_images, headshots = images.blocks(root, stories, owner, people)
    stories_of: dict[str, set[str]] = {}
    for sid, s in stories.items():
        for t in s["tellings"]:
            stories_of.setdefault(t["teller"], set()).add(sid)
    out_stories, links, seen = [], [], set()
    for sid, s in sorted(stories.items()):
        if not isinstance(s.get("score"), (int, float)) or not s.get("profile") or not s.get("tier"):
            raise SystemExit(f"build: story {sid} has no score, profile or tier: run pipeline.score first")
        d = attest(s)
        tellings = []
        for t in s["tellings"]:
            ep = episodes.get(t["episode"]) if t.get("episode") else None
            tellings.append({
                "episode": t.get("episode"), "document": t.get("document"), "page": t.get("page"),
                "from_s": t.get("from_s"), "to_s": t.get("to_s"),
                "url": url_at(ep, t.get("from_s")) if ep else (documents.get(t["document"], {}).get("url") if t.get("document") else None),
                "teller": t["teller"], "teller_name": people[t["teller"]]["name"], "quote": t.get("quote"),
                "kind": t["kind"], "cites": t.get("cites", []), "documents": t.get("documents", []),
                "repetition": t["teller"] in d["repetitions"],
                "difference": t.get("difference"),
            })
        docs = sorted({x for t in s["tellings"] for x in t.get("documents", [])} | {t["document"] for t in s["tellings"] if t.get("document")})
        tellers = sorted({t["teller"] for t in s["tellings"]})
        shared_by = {p: len(stories_of[p]) - 1 for p in tellers}
        out_stories.append({
            "id": sid, "title": s["title"], "summary": s["summary"], "era": s.get("era"), "years": s.get("years"),
            "place": s.get("place"), "place_text": s.get("place_text"), "coordinates": s.get("coordinates"),
            "kind": s.get("kind"), "claims": s.get("claims", []),
            "tags": s.get("tags", []), "score": s["score"], "attestation": s["attestation"], "tier": s["tier"],
            "profile": s["profile"],
            "independent": d["independent"], "repetitions": d["repetitions"], "tellings": tellings,
            "shared_teller": len(set().union(*(stories_of[p] for p in tellers)) - {sid}) if tellers else 0,
            "shared_teller_by": shared_by,
            "documents": [{"id": x, "title": documents[x]["title"], "url": documents[x].get("url"), "date": documents[x].get("date")} for x in docs],
            "aliases": s.get("aliases", []),
            "discussion": [{**e, "url": url_at(episodes[e["episode"]], seconds(e["time"]))} if e.get("episode") else e
                           for e in s.get("discussion", [])],
            "notes_open": notes_open.get(sid, 0),
            "images": story_images.get(sid, []),
        })
        for r in s.get("related", []):
            key = tuple(sorted((sid, r["story"]))) + (r["relation"],)
            if key not in seen:
                seen.add(key)
                links.append({"a": key[0], "b": key[1], "relation": r["relation"], "note": r.get("note")})
    ids = sorted(stories)
    for i, a in enumerate(ids):
        da = {x for t in stories[a]["tellings"] for x in t.get("documents", [])} | {t["document"] for t in stories[a]["tellings"] if t.get("document")}
        for b in ids[i + 1:]:
            db = {x for t in stories[b]["tellings"] for x in t.get("documents", [])} | {t["document"] for t in stories[b]["tellings"] if t.get("document")}
            if da & db and (a, b, "shares-document") not in seen:
                seen.add((a, b, "shares-document"))
                links.append({"a": a, "b": b, "relation": "shares-document", "note": ", ".join(sorted(da & db))})
    dates = [e["published"] for e in episodes.values() if e.get("published")]
    data = {
        "built": dt.date.today().isoformat(),
        "corpus_date": max(dates) if dates else None,
        "median_attestation": summary["median_attestation"],
        "scoring": {k: summary[k] for k in ("weights", "institutional_trust", "median_floor", "median_attestation", "tiers")},
        "counts": summary["counts"],
        "eras": root.eras(), "places": root.places(),
        "stories": out_stories, "links": links,
        "aliases": owner,
        "people": {p: {"name": v["name"], "roles": v.get("roles", []), "aliases": v.get("aliases", []), "image": headshots.get(p)}
                   for p, v in people.items()},
        "episodes": {e: {"show": v.get("show"), "title": v.get("title"), "url": v.get("url"), "published": v.get("published")} for e, v in episodes.items()},
    }
    plain = {sid: s["plain"] for sid, s in sorted(stories.items()) if s.get("plain")}
    out.parent.mkdir(parents=True, exist_ok=True)
    for path, glob, obj in ((out, "NHI_DATA", data), (out.parent / "plain.json", "NHI_PLAIN", plain)):
        compact = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
        path.write_text(compact, encoding="utf-8")
        path.with_suffix(".js").write_text(f"window.{glob} = " + compact + ";\n", encoding="utf-8")
    print(f"build: {len(out_stories)} stories ({len(plain)} plain), {len(links)} links -> {rel(out, root.path)}, {rel(out.parent / 'plain.json', root.path)} and their .js", file=sys.stderr)
    return data


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--out", type=Path, help="default: <root>/site/data.json")
    a = ap.parse_args(argv)
    root = Root(a.root)
    run(root, a.out.resolve() if a.out else root.site / "data.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
