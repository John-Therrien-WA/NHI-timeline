"""The evidence profile, its attestation, score and tier: scoring.md as code.

    uv run python -m pipeline.score [--root DIR]

For every story: group tellings by teller (a replay, a telling with `replay_of`, carries the clip's
speaker as its teller since pipeline/clips.py ran, so it falls in with that person's tellings and
never adds a teller; its kind counts only for a teller whose every telling of the story is a replay,
so a replay never weighs more than the speaker's own telling); build the citation graph from `cites` among the story's
tellers; a teller who reaches another teller of the same story through `cites` is a repetition and
adds nothing, except that citing a source is not repeating it (a `cites` edge to a person who tells
the story only through document tellings, the source's own words, is dropped); the rest are
independent. The profile counts the independent tellers by their
strongest kind (an `official` teller is a record unless all its official tellings carry
`official_kind: "conclusion"`), the documents that are tellings, the documents credited by an
independent teller, the repetitions, the episodes, and whether any story says it contradicts this
one. The attestation is the weighted sum of the profile at the default institutional trust; the
score is the attestation over the corpus median (at least 0.5); the tier names the band. All of
it is written into each story, and data/scores.json holds the weights, the knob, the median, the
tier counts and every profile, so the page can recompute at another knob value.
"""
from __future__ import annotations

import argparse
import datetime as dt
import statistics
import sys

from .common import REPO, Root, save_json

# The order is the strength order: a teller's strongest kind is the first of theirs in it, and
# the knob never reorders it (scoring.md, "Independence and kinds").
KINDS = ("firsthand", "official", "journalist", "secondhand", "researcher", "host")
WEIGHTS = {"firsthand": 1.0, "official": 0.8, "journalist": 0.6, "secondhand": 0.5, "researcher": 0.25, "host": 0.1}
DOCUMENT_TELLING = 0.5
DOCUMENT_CREDITED = 0.25
TRUST = {"default": 1.0, "min": 0.5, "max": 1.25}  # institutional trust: multiplies WEIGHTS["official"]
MEDIAN_FLOOR = 0.5
TIERS = ("well-attested", "told-by-several", "told-once")
PROFILE_COUNTS = ("firsthand", "official_records", "official_conclusions", "journalist", "secondhand", "researcher", "host")


def tellers_of(story: dict) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for t in story["tellings"]:
        if not t.get("teller"):
            raise SystemExit(f"score: story {story['id']}: a telling has no teller")
        if t.get("kind") not in WEIGHTS:
            raise SystemExit(f"score: story {story['id']}: telling kind {t.get('kind')!r} is not one of {list(KINDS)}")
        if t.get("official_kind") not in (None, "record", "conclusion"):
            raise SystemExit(f"score: story {story['id']}: official_kind {t['official_kind']!r} is not record or conclusion")
        if t.get("official_kind") is not None and t["kind"] != "official":
            raise SystemExit(f"score: story {story['id']}: official_kind on a {t['kind']!r} telling")
        by.setdefault(t["teller"], []).append(t)
    return by


def own(tellings: list[dict]) -> list[dict]:
    """A teller's tellings that weigh: those that are not replays, or every one when all are replays."""
    return [t for t in tellings if "replay_of" not in t] or tellings


def strongest(tellings: list[dict]) -> str:
    return min((t["kind"] for t in own(tellings)), key=KINDS.index)


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
    `cites` is a repetition. Citing a source is not repeating it: a `cites` edge to a person whose
    every telling of the story is a document telling (the source's own words, which
    pipeline/sources.py adds only when they carry the story and check.py holds verbatim to the
    source's text) is no edge, so the citer and the source's author are both independent. Tellers
    that reach each other (a cycle) count as one: the strongest, the id breaking a tie."""
    by = tellers_of(story)
    source_only = {p for p, ts in by.items() if all(t.get("document") for t in ts)}
    graph = {p: {c for t in ts for c in t.get("cites", []) if c in by and c != p and c not in source_only}
             for p, ts in by.items()}
    r = reach(graph)
    originals, repetitions = [], []
    for p in by:
        others = r[p]
        if not others:
            originals.append(p)
        elif all(p in r[o] for o in others):  # a cycle: everyone it reaches reaches it back
            if p == min(others | {p}, key=lambda q: (KINDS.index(strongest(by[q])), q)):
                originals.append(p)
            else:
                repetitions.append(p)
        else:
            repetitions.append(p)
    return sorted(originals), sorted(repetitions)


def count_key(tellings: list[dict]) -> str:
    """The profile count an independent teller lands in."""
    k = strongest(tellings)
    if k != "official":
        return k
    official = [t for t in own(tellings) if t["kind"] == "official"]
    return "official_conclusions" if all(t.get("official_kind") == "conclusion" for t in official) else "official_records"


def attest(story: dict) -> dict:
    """The profile without `contradicted` (which needs the corpus), plus the teller lists."""
    by = tellers_of(story)
    originals, repetitions = independent(story)
    counts = dict.fromkeys(PROFILE_COUNTS, 0)
    for p in originals:
        counts[count_key(by[p])] += 1
    doc_tellings = {t["document"] for t in story["tellings"] if t.get("document")}
    credited = {d for p in originals for t in by[p] for d in t.get("documents", [])} - doc_tellings
    kinds = [strongest(by[p]) for p in originals]
    profile = {
        "independent_tellers": len(originals), **counts,
        "documents": len(doc_tellings), "credited_documents": len(credited),
        "repetitions": len(repetitions), "contradicted": False,
        "strongest_kind": min(kinds, key=KINDS.index) if kinds else None,
        "tellers": originals,
        "episodes": sorted({t["episode"] for t in story["tellings"] if t.get("episode")}),
    }
    return {"profile": profile, "independent": originals, "repetitions": repetitions,
            "documents": sorted(doc_tellings), "documents_cited": sorted(credited)}


def attestation(profile: dict, trust: float = TRUST["default"]) -> float:
    """The weighted sum of a profile; the page computes the same at the reader's knob value."""
    if not TRUST["min"] <= trust <= TRUST["max"]:
        raise SystemExit(f"score: institutional trust {trust} is outside {TRUST['min']} to {TRUST['max']}")
    official = WEIGHTS["official"] * trust
    a = (WEIGHTS["firsthand"] * profile["firsthand"]
         + official * (profile["official_records"] + profile["official_conclusions"])
         + sum(WEIGHTS[k] * profile[k] for k in ("journalist", "secondhand", "researcher", "host"))
         + DOCUMENT_TELLING * profile["documents"] + DOCUMENT_CREDITED * profile["credited_documents"])
    return round(a, 4)


def tier(profile: dict) -> str:
    if profile["independent_tellers"] >= 2:
        if profile["documents"] + profile["credited_documents"] or profile["firsthand"] or profile["official_records"]:
            return "well-attested"
        return "told-by-several"
    return "told-once"


def contradicted_ids(stories: dict) -> set[str]:
    """Stories that name a `contradicts` relation, and the stories they name: the flag goes both ways."""
    out = set()
    for sid, s in stories.items():
        for r in s.get("related", []):
            if r.get("relation") == "contradicts":
                out |= {sid, r["story"]}
    return out


def run(root: Root) -> dict:
    stories = root.load_dir(root.stories)
    if not stories:
        raise SystemExit("score: no stories under data/stories")
    flagged = contradicted_ids(stories)
    profiles = {}
    for sid, s in stories.items():
        p = attest(s)["profile"]
        p["contradicted"] = sid in flagged
        profiles[sid] = p
    att = {sid: attestation(p) for sid, p in profiles.items()}
    m = max(MEDIAN_FLOOR, statistics.median(att.values()))
    tiers = dict.fromkeys(TIERS, 0)
    by_kind: dict[str, int] = {}
    for sid, s in stories.items():
        s["profile"] = profiles[sid]
        s["attestation"] = att[sid]
        s["score"] = round(att[sid] / m, 3)
        s["tier"] = tier(profiles[sid])
        tiers[s["tier"]] += 1
        save_json(root.stories / f"{sid}.json", s)
        by_kind[s.get("kind") or "unknown"] = by_kind.get(s.get("kind") or "unknown", 0) + 1
    summary = {
        "computed": dt.date.today().isoformat(),
        "weights": {**WEIGHTS, "document_telling": DOCUMENT_TELLING, "document_credited": DOCUMENT_CREDITED},
        "institutional_trust": TRUST,
        "median_floor": MEDIAN_FLOOR,
        "median_attestation": round(m, 4),
        "tiers": tiers,
        "counts": {
            "stories": len(stories),
            "tellings": sum(len(s["tellings"]) for s in stories.values()),
            "independent_tellers": sum(p["independent_tellers"] for p in profiles.values()),
            "repetitions": sum(p["repetitions"] for p in profiles.values()),
            "documents": sum(p["documents"] + p["credited_documents"] for p in profiles.values()),
            "contradicted": sum(p["contradicted"] for p in profiles.values()),
            "by_kind": dict(sorted(by_kind.items())),
        },
        "stories": {sid: {"attestation": att[sid], "score": stories[sid]["score"], "tier": stories[sid]["tier"],
                          "profile": profiles[sid]} for sid in sorted(stories)},
    }
    save_json(root.data / "scores.json", summary)
    print(f"score: {len(stories)} stories, median attestation {m:.3f}, "
          + ", ".join(f"{n} {t}" for t, n in tiers.items()) + " -> data/scores.json", file=sys.stderr)
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=REPO)
    a = ap.parse_args(argv)
    run(Root(a.root))
    return 0


if __name__ == "__main__":
    sys.exit(main())
