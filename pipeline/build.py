"""Data to site/data.json (and site/data.js, the same object for a page opened from disk).

    uv run python -m pipeline.build [--root DIR] [--out site/data.json]

Stories with era, place (and the free place text for the unresolved), years, score and the
repetition count, tellings with quotes and time codes and the YouTube URL at that second, the
documents, the links between stories (shared document and every `related` relation), the count of
other stories told by each of a story's tellers (`shared_teller`, by teller and in all: a count,
never a link, since one host telling fifty stories would link every story to every other), the
axes, and the corpus date (the latest episode published). Fails when a story has no score: run
pipeline.score first.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from .common import REPO, Root, rel, save_json
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
    stories_of: dict[str, set[str]] = {}
    for sid, s in stories.items():
        for t in s["tellings"]:
            stories_of.setdefault(t["teller"], set()).add(sid)
    out_stories, links, seen = [], [], set()
    for sid, s in sorted(stories.items()):
        if not isinstance(s.get("score"), (int, float)):
            raise SystemExit(f"build: story {sid} has no numeric score: run pipeline.score first")
        d = attest(s)
        tellings = []
        for t in s["tellings"]:
            ep = episodes.get(t["episode"]) if t.get("episode") else None
            tellings.append({
                "episode": t.get("episode"), "document": t.get("document"), "page": t.get("page"),
                "from_s": t.get("from_s"), "to_s": t.get("to_s"),
                "url": url_at(ep, t.get("from_s")) if ep else (documents.get(t["document"], {}).get("url") if t.get("document") else None),
                "show": ep.get("show") if ep else None, "episode_title": ep.get("title") if ep else None,
                "published": ep.get("published") if ep else None,
                "teller": t["teller"], "teller_name": people[t["teller"]]["name"], "quote": t.get("quote"),
                "kind": t["kind"], "cites": t.get("cites", []), "documents": t.get("documents", []),
                "repetition": t["teller"] in d["repetitions"],
            })
        docs = sorted({x for t in s["tellings"] for x in t.get("documents", [])} | {t["document"] for t in s["tellings"] if t.get("document")})
        tellers = sorted({t["teller"] for t in s["tellings"]})
        shared_by = {p: len(stories_of[p]) - 1 for p in tellers}
        out_stories.append({
            "id": sid, "title": s["title"], "summary": s["summary"], "era": s.get("era"), "years": s.get("years"),
            "place": s.get("place"), "place_text": s.get("place_text"), "coordinates": s.get("coordinates"),
            "kind": s.get("kind"), "claims": s.get("claims", []),
            "tags": s.get("tags", []), "score": s["score"], "attestation": d["attestation"],
            "independent": d["independent"], "repetitions": d["repetitions"], "tellings": tellings,
            "shared_teller": len(set().union(*(stories_of[p] for p in tellers)) - {sid}) if tellers else 0,
            "shared_teller_by": shared_by,
            "documents": [{"id": x, "title": documents[x]["title"], "url": documents[x].get("url"), "date": documents[x].get("date")} for x in docs],
            "related": s.get("related", []),
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
        "counts": summary["counts"],
        "eras": root.eras(), "places": root.places(),
        "stories": out_stories, "links": links,
        "people": {p: {"name": v["name"], "roles": v.get("roles", [])} for p, v in people.items()},
        "episodes": {e: {"show": v.get("show"), "title": v.get("title"), "url": v.get("url"), "published": v.get("published")} for e, v in episodes.items()},
    }
    save_json(out, data)
    js = out.with_suffix(".js")
    js.write_text("window.NHI_DATA = " + json.dumps(data, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"build: {len(out_stories)} stories, {len(links)} links -> {rel(out, root.path)} and {rel(js, root.path)}", file=sys.stderr)
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
