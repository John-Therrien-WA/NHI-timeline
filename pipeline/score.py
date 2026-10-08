"""The corroboration score: scoring.md as code.

    uv run python -m pipeline.score [--root DIR]

For every story: group tellings by teller; build the citation graph from `cites` among the story's
tellers; a teller who reaches another teller of the same story through `cites` is a repetition
and adds nothing; the rest are independent, each weighted by the strongest kind among their
tellings; each independent document (a document telling) adds 0.5, each document cited by an
independent teller adds 0.25. Attestation is the sum. The corpus median of attestation is m (at
least 0.5); score = attestation / m, written into each story. data/scores.json holds the summary.
"""
from __future__ import annotations

import argparse
import datetime as dt
import statistics
import sys

from .common import REPO, Root, save_json

WEIGHTS = {"firsthand": 1.0, "official": 1.0, "journalist": 0.6, "secondhand": 0.4, "researcher": 0.25, "host": 0.1}
DOCUMENT_TELLING = 0.5
DOCUMENT_CITED = 0.25
MEDIAN_FLOOR = 0.5


def tellers_of(story: dict) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for t in story["tellings"]:
        if not t.get("teller"):
            raise SystemExit(f"score: story {story['id']}: a telling has no teller")
        by.setdefault(t["teller"], []).append(t)
    return by


def reach(graph: dict[str, set[str]]) -> dict[str, set[str]]:
    """Every node's set of nodes reachable through one or more edges."""
    out = {}
    for start in graph:
        seen, stack = set(), list(graph[start])
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(graph.get(n, ()))
        out[start] = seen
    return out


def independent(story: dict) -> tuple[list[str], list[str]]:
    """(independent tellers, repetitions). A teller who reaches another teller of the story through
    `cites` is a repetition. Tellers that reach each other (a cycle) count as one: the heaviest."""
    by = tellers_of(story)
    graph = {p: {c for t in ts for c in t.get("cites", []) if c in by and c != p} for p, ts in by.items()}
    r = reach(graph)
    originals, repetitions = [], []
    for p in by:
        others = r[p]
        if not others:
            originals.append(p)
        elif all(p in r[o] for o in others):  # a cycle: everyone it reaches reaches it back
            if p == max(others | {p}, key=lambda q: (weight_of(by[q]), q)):
                originals.append(p)
            else:
                repetitions.append(p)
        else:
            repetitions.append(p)
    return sorted(originals), sorted(repetitions)


def weight_of(tellings: list[dict]) -> float:
    kinds = [t["kind"] for t in tellings]
    for k in kinds:
        if k not in WEIGHTS:
            raise SystemExit(f"score: telling kind {k!r} is not one of {sorted(WEIGHTS)}")
    return max(WEIGHTS[k] for k in kinds)


def attest(story: dict) -> dict:
    by = tellers_of(story)
    originals, repetitions = independent(story)
    teller_sum = sum(weight_of(by[p]) for p in originals)
    doc_tellings = {t["document"] for t in story["tellings"] if t.get("document")}
    cited = {d for p in originals for t in by[p] for d in t.get("documents", [])} - doc_tellings
    attestation = teller_sum + DOCUMENT_TELLING * len(doc_tellings) + DOCUMENT_CITED * len(cited)
    return {"attestation": round(attestation, 4), "independent": originals, "repetitions": repetitions,
            "documents": sorted(doc_tellings), "documents_cited": sorted(cited)}


def run(root: Root) -> dict:
    stories = root.load_dir(root.stories)
    if not stories:
        raise SystemExit("score: no stories under data/stories")
    details = {sid: attest(s) for sid, s in stories.items()}
    m = max(MEDIAN_FLOOR, statistics.median(d["attestation"] for d in details.values()))
    by_kind: dict[str, int] = {}
    for sid, s in stories.items():
        s["score"] = round(details[sid]["attestation"] / m, 3)
        save_json(root.stories / f"{sid}.json", s)
        by_kind[s.get("kind") or "unknown"] = by_kind.get(s.get("kind") or "unknown", 0) + 1
    summary = {
        "computed": dt.date.today().isoformat(),
        "median_attestation": round(m, 4),
        "counts": {
            "stories": len(stories),
            "tellings": sum(len(s["tellings"]) for s in stories.values()),
            "independent_tellers": sum(len(d["independent"]) for d in details.values()),
            "repetitions": sum(len(d["repetitions"]) for d in details.values()),
            "documents": sum(len(d["documents"]) + len(d["documents_cited"]) for d in details.values()),
            "by_kind": dict(sorted(by_kind.items())),
        },
        "stories": {sid: {"attestation": d["attestation"], "score": stories[sid]["score"],
                          "independent": d["independent"], "repetitions": d["repetitions"]}
                    for sid, d in sorted(details.items())},
    }
    save_json(root.data / "scores.json", summary)
    print(f"score: {len(stories)} stories, median attestation {m:.3f} -> data/scores.json", file=sys.stderr)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=REPO)
    a = ap.parse_args(argv)
    run(Root(a.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
