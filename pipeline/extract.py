"""An episode's caption text to story candidates.

    uv run python -m pipeline.extract <video id> [--model sonnet] [--chunk-words 12000] [--fixture FILE] [--root DIR]

Reads sources/captions/<id>.<lang>.txt, sends it in chunks of about --chunk-words words with
prompts/extract.md through `claude -p` (pipeline/llm.py), validates each answer against the
prompt's keys, checks every quote to be a verbatim substring of the caption text (a quote that is
not is dropped, with the reason logged and kept in the output), locates every kept quote in the
cues for its time codes, and writes data/candidates/<id>.json.

--fixture FILE bypasses `claude -p`: FILE holds the prepared answers, a JSON list with one answer
(a list of candidate objects) per chunk, or a single list of candidates for a one-chunk episode.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import llm
from .common import REPO, Captions, Root, load_json, parse_timecode, parse_years, rel, save_json

KEYS = ("title", "story_kind", "years", "place", "teller", "kind", "quote", "from_s", "cites", "documents")
KINDS = ("firsthand", "official", "journalist", "secondhand", "researcher", "host")
STORY_KINDS = ("sighting", "encounter", "crash-retrieval", "reverse-engineering", "program", "document", "testimony",
               "theory", "cosmology", "place-lore")

SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "story_kind": {"type": "string", "enum": list(STORY_KINDS)},
                    "years": {"type": "string"},
                    "place": {"type": "string"},
                    "teller": {"type": "string"},
                    "kind": {"type": "string", "enum": list(KINDS)},
                    "quote": {"type": "string"},
                    "from_s": {"type": "string"},
                    "cites": {"type": "array", "items": {"type": "string"}},
                    "documents": {"type": "array", "items": {"type": "string"}},
                },
                "required": list(KEYS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["stories"],
    "additionalProperties": False,
}


def chunks(cap: Captions, words: int) -> list[str]:
    """The caption lines in chunks of about `words` words, never splitting a cue."""
    out, cur, n = [], [], 0
    for line in cap.lines():
        cur.append(line)
        n += len(line.split()) - 1
        if n >= words:
            out.append("\n".join(cur))
            cur, n = [], 0
    if cur:
        out.append("\n".join(cur))
    return out


def prompt_for(template: str, episode: dict, chunk: str) -> str:
    if "{episode}" not in template or "{captions}" not in template:
        raise SystemExit("prompts/extract.md must contain {episode} and {captions}")
    head = f"{episode['id']}: {episode.get('show') or '?'}, {episode.get('title') or '?'} ({episode.get('published') or 'date unknown'})"
    return template.replace("{episode}", head).replace("{captions}", chunk)


def answer_list(data) -> list:
    """The list of candidate objects from an answer that is either the list or {'stories': list}."""
    if isinstance(data, dict) and set(data) == {"stories"}:
        data = data["stories"]
    if not isinstance(data, list):
        raise SystemExit(f"extract: the answer is not a list of stories: {str(data)[:200]}")
    return data


def validate(obj, where: str) -> dict:
    if not isinstance(obj, dict):
        raise SystemExit(f"extract: {where}: a candidate is not an object: {str(obj)[:120]}")
    missing, extra = set(KEYS) - set(obj), set(obj) - set(KEYS)
    if missing or extra:
        raise SystemExit(f"extract: {where}: keys differ from the prompt's (missing {sorted(missing)}, extra {sorted(extra)})")
    for k in ("title", "teller", "quote", "kind"):
        if not isinstance(obj[k], str) or not obj[k].strip():
            raise SystemExit(f"extract: {where}: {k} must be a non-empty string")
    if obj["kind"] not in KINDS:
        raise SystemExit(f"extract: {where}: kind {obj['kind']!r} is not one of {KINDS}")
    if obj["story_kind"] not in STORY_KINDS:
        raise SystemExit(f"extract: {where}: story_kind {obj['story_kind']!r} is not one of {STORY_KINDS}")
    for k in ("cites", "documents"):
        if not isinstance(obj[k], list) or not all(isinstance(x, str) for x in obj[k]):
            raise SystemExit(f"extract: {where}: {k} must be a list of strings")
    return obj


def candidates_from(answers: list[list], cap: Captions, episode_id: str) -> tuple[list[dict], list[dict]]:
    kept, dropped = [], []
    for ci, answer in enumerate(answers):
        for oi, raw in enumerate(answer_list(answer)):
            where = f"chunk {ci + 1} story {oi + 1}"
            obj = validate(raw, where)
            loc = cap.locate(obj["quote"])
            if loc is None:
                reason = "quote is not a verbatim substring of the caption text"
                print(f"extract: {episode_id}: dropped {obj['title']!r} ({where}): {reason}", file=sys.stderr)
                dropped.append({"title": obj["title"], "quote": obj["quote"], "reason": reason, "where": where})
                continue
            from_s, to_s = loc
            said = parse_timecode(obj["from_s"])
            if said is not None and abs(said - from_s) > 90:
                print(f"extract: {episode_id}: {obj['title']!r}: the answer said {obj['from_s']}, the cue is at {from_s:.0f}s; keeping the cue",
                      file=sys.stderr)
            kept.append({
                "title": obj["title"].strip(),
                "story_kind": obj["story_kind"],
                "years_text": obj["years"],
                "years": parse_years(obj["years"]),
                "place_text": obj["place"],
                "teller": obj["teller"].strip(),
                "kind": obj["kind"],
                "quote": obj["quote"],
                "from_s": from_s,
                "to_s": to_s,
                "cites": [c.strip() for c in obj["cites"] if c.strip()],
                "documents": [d.strip() for d in obj["documents"] if d.strip()],
            })
    return kept, dropped


def ask(cap: Captions, episode: dict, template: str, words: int, model: str, timeout: int) -> list[list]:
    answers = []
    parts = chunks(cap, words)
    for i, chunk in enumerate(parts, 1):
        print(f"extract: {episode['id']}: chunk {i}/{len(parts)} ({len(chunk.split())} words) -> claude -p {model}", file=sys.stderr)
        data = llm.complete_json(prompt_for(template, episode, chunk), SCHEMA, model=model, timeout=timeout)
        answers.append(answer_list(data))
    return answers


def fixture_answers(f: Path) -> list[list]:
    data = load_json(f)
    if not isinstance(data, list):
        raise SystemExit(f"extract: fixture {f} must be a JSON list")
    if data and all(isinstance(x, dict) for x in data):
        return [data]
    if all(isinstance(x, list) for x in data):
        return data
    raise SystemExit(f"extract: fixture {f} must be a list of candidates or a list of such lists (one per chunk)")


def run(root: Root, episode_id: str, *, model: str, chunk_words: int, fixture: Path | None, timeout: int) -> Path:
    episode = load_json(root.episodes / f"{episode_id}.json")
    if episode.get("id") != episode_id:
        raise SystemExit(f"extract: {root.episodes / (episode_id + '.json')} has id {episode.get('id')!r}")
    cap = Captions(root.caption_text(episode))
    template = (root.path / "prompts" / "extract.md")
    template = (template if template.exists() else REPO / "prompts" / "extract.md").read_text(encoding="utf-8")
    answers = fixture_answers(fixture) if fixture else ask(cap, episode, template, chunk_words, model, timeout)
    kept, dropped = candidates_from(answers, cap, episode_id)
    out = root.candidates / f"{episode_id}.json"
    save_json(out, {"episode": episode_id, "captions": rel(cap.path, root.path), "model": "fixture" if fixture else model,
                    "chunks": len(answers), "candidates": kept, "dropped": dropped})
    print(f"extract: {episode_id}: {len(kept)} candidates, {len(dropped)} dropped -> {rel(out, root.path)}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episode")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--chunk-words", type=int, default=12000)
    ap.add_argument("--timeout", type=int, default=900, help="seconds per chunk")
    ap.add_argument("--fixture", type=Path, help="prepared answers instead of claude -p")
    ap.add_argument("--root", type=Path, default=REPO)
    a = ap.parse_args(argv)
    run(Root(a.root), a.episode, model=a.model, chunk_words=a.chunk_words, fixture=a.fixture, timeout=a.timeout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
