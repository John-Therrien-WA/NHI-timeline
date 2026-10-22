"""A plain telling for every story: what the story is, written ground up for a reader new to the subject.

    uv run python -m pipeline.explain [story id ...] [--all] [--force] [--shard i/n] [--model opus] [--batch 12] [--timeout 600] [--fixture FILE] [--root DIR]

Each story gets `plain`: a plain-language telling in the reported voice (who the people are by role,
what they say happened, where and when, what every programme, acronym and document named is, and
why the story is told), two to three sentences for a `told-once` story, three to five for
`told-by-several`, a short paragraph for `well-attested`. The stories go to `claude -p` with
prompts/explain.md in groups of --batch (12), well-attested first, then told-by-several, then
told-once, so the stories the page foregrounds get theirs first; the prompt gives each story's
title, kind, years, era, place, tier, claims, related stories and every telling (the teller
by name and kind, the show and date or the document and its locator, the quote, whom and what it
cites, the difference where the tellers disagree) and the story's `source` notes (what a source
itself says against the tellers, from `pipeline.sources`; a note on a document the story quotes only
in its notes, a note-only entry's, is sent as from a disputed document, and the prompt has the model
report it as what that document says, never as the record). The answer is `{ "tellings": [ { "id", "plain" } ] }` and must name every id of
the group once and no other; a refused answer is asked once more with a note, a second refusal stops
the run; an answered id that spells out an asked id's truncated last word or drops its `-<year>`
suffix is mapped back to the asked id when exactly one fits. Em dashes in an answer become commas. Every story file of a group is saved as soon as the
group is answered, so a killed run resumes at the first story without `plain`. A story with `plain`
is skipped unless --force; a story with `plain_by: "hand"` (written or edited by a person) is never
touched. The stories named on the command line, or --all, are the run's set; --all with nothing
to do prints so and exits 0. --shard i/n (1 <= i <= n) keeps every nth story of the ordered
selection, starting at the ith, before the stories already told are skipped (so a shard's set stays
fixed while it or another shard progresses or resumes), and forms the groups inside the shard: n
runs with 1/n to n/n cover the selection once over disjoint sets, so they can run side by side. Run after score
(the tier comes from it) and before build.

--fixture FILE replaces `claude -p` with prepared answers: a JSON object from story id to the plain
telling; a story asked for that the file lacks fails.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from . import llm
from .common import REPO, Root, load_json, norm_ws, rel, save_json
from .sources import note_only_documents, url_index

BATCH = 12
TIER_ORDER = {"well-attested": 0, "told-by-several": 1, "told-once": 2}
TELLING_KINDS = {
    "firsthand": "first-hand: says they saw it or took part",
    "official": "official: a government record, sworn testimony or an official's statement",
    "journalist": "journalist citing named sources",
    "secondhand": "second-hand: relays what a named person told them",
    "researcher": "researcher summarising without a named source",
    "host": "the podcast host's own framing",
}
SCHEMA = {
    "type": "object",
    "properties": {
        "tellings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"id": {"type": "string"}, "plain": {"type": "string"}},
                "required": ["id", "plain"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["tellings"],
    "additionalProperties": False,
}


def template(root: Root) -> str:
    f = root.path / "prompts" / "explain.md"
    text = (f if f.exists() else REPO / "prompts" / "explain.md").read_text(encoding="utf-8")
    if "{stories}" not in text:
        raise SystemExit("prompts/explain.md must contain {stories}")
    return text


def years_text(y: dict | None) -> str:
    if not y or y.get("from") is None:
        return "not given"
    return str(y["from"]) if y["from"] == y["to"] else f"{y['from']} to {y['to']}"


def person_text(pid: str, people: dict) -> str:
    """'David Fravor (roles: pilot; affiliation: US Navy)' when the person file says more than the name."""
    p = people.get(pid)
    if p is None:
        return pid.replace("-", " ").title()
    extra = []
    if p.get("roles"):
        extra.append("roles: " + ", ".join(p["roles"]))
    if p.get("affiliation"):
        extra.append("affiliation: " + str(p["affiliation"]))
    if (p.get("note") or "").strip():
        extra.append("note: " + norm_ws(p["note"]))
    return p["name"] + (f" ({'; '.join(extra)})" if extra else "")


def document_text(did: str, documents: dict) -> str:
    d = documents.get(did)
    if d is None:
        return did
    bits = [d.get("title") or did]
    if d.get("issuer"):
        bits.append(str(d["issuer"]))
    if d.get("date"):
        bits.append(str(d["date"]))
    return ", ".join(bits)


def locator_text(page) -> str:
    """', page 12' for a page number, ', chapter 3' for any other locator, '' without one."""
    if not page:
        return ""
    return f", page {page}" if str(page).isdigit() else f", {page}"


def source_notes_text(s: dict, documents: dict) -> list[str]:
    """The story's `source` discussion entries: what a source itself says against what the tellers say. A note on
    a document no telling of the story names (`sources.note_only_documents`, a note-only entry's note) is marked
    as from a disputed document, which the prompt never takes for the record."""
    index = url_index(documents)
    return [f"source note, from {'a disputed document, ' if note_only_documents(s, d, index) else ''}{d['by']}: {norm_ws(d['text'])}"
            for d in s.get("discussion") or [] if d.get("kind") == "source"]


def telling_text(n: int, t: dict, people: dict, episodes: dict, documents: dict) -> str:
    kind = TELLING_KINDS.get(t.get("kind"), t.get("kind"))
    where = ""
    if t.get("episode"):
        ep = episodes.get(t["episode"], {})
        bits = [b for b in (ep.get("show"), ep.get("title")) if b]
        where = " on " + (": ".join(bits) if bits else f"episode {t['episode']}") + (f", {ep['published']}" if ep.get("published") else "")
    elif t.get("document"):
        where = " in the document " + document_text(t["document"], documents) + locator_text(t.get("page")) + ", the document's own words"
    lines = [f"telling {n} by {person_text(t['teller'], people)} ({kind}){where}:", f"  \"{t.get('quote') or ''}\""]
    if t.get("cites"):
        lines.append("  cites: " + "; ".join(person_text(c, people) for c in t["cites"]))
    if t.get("documents"):
        lines.append("  credits the documents: " + "; ".join(document_text(d, documents) for d in t["documents"]))
    if (t.get("difference") or "").strip():
        lines.append("  told differently: " + norm_ws(t["difference"]))
    return "\n".join(lines)


def story_text(s: dict, stories: dict, people: dict, episodes: dict, documents: dict, eras: dict[str, str]) -> str:
    lines = [f"<story id=\"{s['id']}\">", f"title: {s['title']}", f"kind: {s.get('kind') or 'not given'}",
             f"years: {years_text(s.get('years'))}", f"era: {eras.get(s.get('era'), 'not given')}",
             f"place: {s.get('place_text') or s.get('place') or 'not given'}"]
    profile = s.get("profile") or {}
    n = profile.get("independent_tellers")
    lines.append(f"tier: {s['tier']}" + (f" ({n} independent {'teller' if n == 1 else 'tellers'})" if n is not None else ""))
    if s.get("claims"):
        lines.append("claims: " + "; ".join(s["claims"]))
    related = [f"\"{stories[r['story']]['title']}\" ({r['relation'].replace('-', ' ')})" for r in s.get("related", []) if r.get("story") in stories]
    if related:
        lines.append("related stories: " + "; ".join(related))
    lines.append("")
    lines += [telling_text(i, t, people, episodes, documents) for i, t in enumerate(s["tellings"], 1)]
    lines += source_notes_text(s, documents)
    lines.append("</story>")
    return "\n".join(lines)


def split_suffix(sid: str) -> tuple[str, str | None]:
    """A slug and its trailing `-<digits>` (a year or a number), None when it has none."""
    m = re.fullmatch(r"(.*)-(\d+)", sid)
    return (m.group(1), m.group(2)) if m else (sid, None)


def asked_id(sid: str, ids: list[str]) -> str:
    """The one asked id an answered id stands for. A story id is a slug cut at 60 letters, so it can end
    mid-word (`...-stopped-by-entiti-2026`), and the model spells the word out now and then
    (`...-stopped-by-entities-2026`) or drops the `-<year>` suffix: an answered id whose stem the asked
    id's stem begins and whose suffix is the asked id's or none is that asked id, when it is the only
    one. Anything else is refused."""
    stem, suffix = split_suffix(sid)
    found = []
    for i in ids:
        i_stem, i_suffix = split_suffix(i)
        if stem.startswith(i_stem) and suffix in (i_suffix, None):
            found.append(i)
    if len(found) != 1:
        raise ValueError(f"{sid!r} is not one of the stories asked about ({ids})")
    return found[0]


def validate(ans, ids: list[str]) -> dict[str, str]:
    """{id: plain} for exactly the ids asked, each plain a non-empty string with em dashes made commas."""
    if not isinstance(ans, dict) or set(ans) != {"tellings"} or not isinstance(ans["tellings"], list):
        raise ValueError(f"the answer must be an object with exactly a tellings list: {str(ans)[:200]}")
    out: dict[str, str] = {}
    for item in ans["tellings"]:
        if not isinstance(item, dict) or set(item) != {"id", "plain"}:
            raise ValueError(f"a telling must have exactly id and plain: {str(item)[:200]}")
        sid, plain = item["id"], item["plain"]
        if sid not in ids:
            sid = asked_id(sid, ids)
        if sid in out:
            raise ValueError(f"{sid!r} is answered twice")
        if not isinstance(plain, str) or not plain.strip():
            raise ValueError(f"{sid}: plain must be a non-empty string")
        out[sid] = norm_ws(plain.replace(" — ", ", ").replace("—", ", "))
    missing = [i for i in ids if i not in out]
    if missing:
        raise ValueError(f"no telling for {missing}")
    return out


def retry_note(error: Exception) -> str:
    return (f"\n\nYour previous answer was refused: {error}. Answer again with exactly one telling for every story "
            "above, its id copied letter for letter from the story's tag (even where it ends mid-word), and no other.")


class Asker:
    """claude -p, or the prepared answers of a fixture. One call explains a group of stories."""

    def __init__(self, root: Root, model: str, timeout: int, fixture: Path | None, complete=None):
        self.template, self.model, self.timeout = template(root), model, timeout
        self.complete = complete or llm.complete_json
        self.fixture = None
        if fixture:
            self.fixture = load_json(fixture)
            if not isinstance(self.fixture, dict) or not all(isinstance(v, str) for v in self.fixture.values()):
                raise SystemExit(f"explain: fixture {fixture} must be an object of story id to plain telling")
        self.calls = 0

    def ask(self, text: str, ids: list[str]) -> dict[str, str]:
        self.calls += 1
        if self.fixture is not None:
            missing = [i for i in ids if i not in self.fixture]
            if missing:
                raise SystemExit(f"explain: fixture has no answer for {missing}")
            return validate({"tellings": [{"id": i, "plain": self.fixture[i]} for i in ids]}, ids)
        prompt = self.template.replace("{stories}", text)
        print(f"explain: {len(ids)} stories ({ids[0]} ...) -> claude -p {self.model}", file=sys.stderr)
        last, note = None, ""
        for attempt in range(2):
            try:
                return validate(self.complete(prompt + note, SCHEMA, model=self.model, timeout=self.timeout), ids)
            except llm.LlmUnavailable:
                raise
            except (llm.LlmError, ValueError) as e:
                last = e
                note = retry_note(e) if isinstance(e, ValueError) else ""
                print(f"explain: {e}" + ("; asking once more" if attempt == 0 else ""), file=sys.stderr)
        raise SystemExit(f"explain: {ids[0]} ...: no valid answer after two tries: {last}")


def ordered(stories: dict, wanted: list[str] | None) -> list[str]:
    """The selected ids in run order: well-attested first, then told-by-several, then told-once, each
    tier by score (highest first) then id."""
    ids = list(stories) if wanted is None else list(dict.fromkeys(wanted))
    for sid in ids:
        if sid not in stories:
            raise SystemExit(f"explain: no story {sid!r}")
        if stories[sid].get("tier") not in TIER_ORDER:
            raise SystemExit(f"explain: story {sid} has no tier: run pipeline.score first")
    return sorted(ids, key=lambda sid: (TIER_ORDER[stories[sid]["tier"]], -(stories[sid].get("score") or 0), sid))


def todo(stories: dict, wanted: list[str] | None, force: bool, shard: tuple[int, int] | None = None) -> list[str]:
    """The ids to explain in run order: the shard of the ordered selection (taken before the skips
    below, so a shard's set does not move as it or another shard progresses), less the stories
    already told. A hand-written telling is never redone; one the stage wrote is redone only with
    --force."""
    out = []
    for sid in shard_of(ordered(stories, wanted), shard):
        s = stories[sid]
        if s.get("plain_by") == "hand":
            continue
        if s.get("plain") and not force:
            continue
        out.append(sid)
    return out


def parse_shard(text: str) -> tuple[int, int]:
    """'2/4' as (2, 4); anything but i/n with 1 <= i <= n fails (shard_of holds the range rule)."""
    m = re.fullmatch(r"\s*(\d+)\s*/\s*(\d+)\s*", text or "")
    if not m:
        raise SystemExit(f"explain: --shard must be i/n with 1 <= i <= n, got {text!r}")
    shard = int(m.group(1)), int(m.group(2))
    shard_of([], shard)
    return shard


def shard_of(ids: list[str], shard: tuple[int, int] | None) -> list[str]:
    """Every nth id of the ordered list, starting at the ith (1-based); the whole list without a shard."""
    if shard is None:
        return ids
    i, n = shard
    if not 1 <= i <= n:
        raise SystemExit(f"explain: shard must be i/n with 1 <= i <= n, got {i}/{n}")
    return ids[i - 1::n]


def run(root: Root, asker: Asker, wanted: list[str] | None = None, *, force: bool = False, size: int = BATCH,
        shard: tuple[int, int] | None = None) -> dict:
    if size < 1:
        raise SystemExit(f"explain: --batch must be at least 1, got {size}")
    stories = root.load_dir(root.stories)
    people = root.load_dir(root.people)
    episodes = root.load_dir(root.episodes)
    documents = root.load_dir(root.documents)
    eras = {e["id"]: f"{e['name']} ({e['from']} to {e['to']})" for e in root.eras()}
    ids = todo(stories, wanted, force, shard)
    selected = len(shard_of(ordered(stories, wanted), shard))
    stats = {"explained": 0, "skipped": selected - len(ids), "calls": 0}
    for i in range(0, len(ids), size):
        group = ids[i:i + size]
        text = "\n\n".join(story_text(stories[sid], stories, people, episodes, documents, eras) for sid in group)
        answers = asker.ask(text, group)
        stats["calls"] += 1
        for sid in group:
            s = stories[sid]
            s["plain"] = answers[sid]
            s.pop("plain_by", None)
            save_json(root.stories / f"{sid}.json", s)
            stats["explained"] += 1
        print(f"explain: {stats['explained']} of {len(ids)} stories explained", file=sys.stderr)
    print("explain: " + ", ".join(f"{v} {k}" for k, v in stats.items()), file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stories", nargs="*", help="story ids to explain")
    ap.add_argument("--all", action="store_true", help="every story without a plain telling")
    ap.add_argument("--force", action="store_true", help="redo the tellings the stage wrote (never a hand-written one)")
    ap.add_argument("--shard", type=parse_shard, help="i/n: every nth story of the ordered list from the ith, "
                    "the groups formed inside it; n runs 1/n to n/n together cover the list once")
    ap.add_argument("--model", default="opus")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per call")
    ap.add_argument("--batch", type=int, default=BATCH, help=f"stories per call (default {BATCH})")
    ap.add_argument("--fixture", type=Path, help="prepared answers instead of claude -p")
    ap.add_argument("--root", type=Path, default=REPO)
    a = ap.parse_args(argv)
    if bool(a.stories) == a.all:
        raise SystemExit("explain: name story ids or give --all, not both and not neither")
    root = Root(a.root)
    run(root, Asker(root, a.model, a.timeout, a.fixture), None if a.all else a.stories, force=a.force, size=a.batch, shard=a.shard)
    return 0


if __name__ == "__main__":
    sys.exit(main())
