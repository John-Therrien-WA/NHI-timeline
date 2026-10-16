"""Decide, a group of tellings per call, whether a story is already in the corpus: one story, many tellings.

    uv run python -m pipeline.link [episode ...] [--root DIR] [--model sonnet] [--batch 10] [--fixture FILE]
    uv run python -m pipeline.link --existing [--root DIR] [--model sonnet] [--fixture FILE] [--dry-run]

Candidate mode (the default) reads data/candidates/<episode>.json (every file, or the episodes
named) and takes the candidates without a `link` field in file order, in groups of --batch (10),
one `claude -p` call per group. For each candidate it retrieves the nearest stories in
data/stories (shared cited names, the same teller, years overlapping or within two years, the same
kind, content words of the candidate's title and quote shared with a story's title, summary and
first quote, weighted by rarity) and takes the top eight; the call offers the union of the group's
stories and asks with prompts/link.md, for each candidate, whether it is the `same` story as one
of them, a `variant` of one, or `new`, and at which grain (`same`, `broader`, `narrower`). A
candidate may also be `same` as, or a `variant` of, an earlier candidate of its group, named `#n`;
that resolves to the story the earlier candidate joins, or to its provisional id. A candidate that
scores against no story and no other candidate of its group is `new` without being asked, and a
group where that holds for every candidate makes no call. A `same` at another grain, or a `same`
joining a `program` to a story of another kind, is downgraded to `new` with the model's reason
kept, the refusal in the link's `downgraded` and in data/links.json. An answer that names a story
neither offered nor an earlier candidate is refused, and the group is asked once more with the
refusal as a note; a second refusal stops the run. The decision is written into the candidate as
`link` ({decision, story, grain, reason, difference, against}, plus `id` for `new` and `variant`;
`against` is what the call let it name: the union of the group's nearest stories and the stories
its earlier tellings `#n` end in, empty when no call was made), and the candidate file and the ledger are saved after each group, so a killed run
resumes at the first candidate without a `link`, with the provisional stories of the candidates
already linked `new` or `variant` held again; merge.py then honours it. Candidate files go in episode date order, then file order. A `new` or `variant`
candidate becomes a provisional story at once (the id merge will give it, the candidate's framing,
its quote as the first telling), so a later candidate of the same run can be `same` as it. A
candidate whose telling a story already holds (merged before linking) is skipped and keeps no
`link`.

--existing links the stories of data/stories among themselves: each story in id order is asked
about the nearest stories earlier in id order, with its first telling as the candidate. On `same`
the story is folded into the earlier one (its tellings appended with `difference` and
`link_reason`, its `related` entries and every reference to it re-pointed, its `discussion` entries
appended to the survivor's in order, its id and aliases kept
in the survivor's `aliases`, its file deleted); on `variant` a `variant` relation is added both
ways with the reason as the note. A story created from a candidate that was linked when it
arrived counts as decided. Each story is asked in a call of its own (a group of one), because a
fold changes which stories are earlier for the next. Every decision is kept in data/links.json with the stories it
was compared against, and the ids the corpus held when a run began; a story already decided is
asked again only about stories that arrived since (each decision is appended to the story's list), so a second run asks nothing.

--fixture FILE replaces `claude -p` with prepared answers, each the answer object the prompt's
schema gives ({"decisions": [...]}): in candidate mode a JSON list of groups, each
{"episode", "candidates": [the titles asked, in order], "decisions"}; for --existing a JSON object
from the story's id to {"decisions"}. A call without a prepared answer fails.
"""
from __future__ import annotations

import argparse
import math
import re
import sys
from pathlib import Path

from . import llm
from .common import REPO, Root, load_json, norm_ws, person_aliases, person_id, rel, save_json, story_id

DECISIONS = ("same", "variant", "new")
GRAINS = ("same", "broader", "narrower")
TOP = 8
BATCH = 10
ADJACENT_YEARS = 2
W_CITE, W_TELLER, W_YEARS, W_KIND = 3.0, 1.0, 1.5, 1.0

FIELDS = ("candidate", "reason", "story", "grain", "decision", "difference")
SCHEMA = {
    "type": "object",
    "properties": {
        "decisions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "candidate": {"type": "integer"},
                    "reason": {"type": "string"},
                    "story": {"type": ["string", "null"]},
                    "grain": {"type": "string", "enum": list(GRAINS)},
                    "decision": {"type": "string", "enum": list(DECISIONS)},
                    "difference": {"type": "string"},
                },
                "required": list(FIELDS),
                "additionalProperties": False,
            },
        },
    },
    "required": ["decisions"],
    "additionalProperties": False,
}
EARLIER = re.compile(r"#([1-9][0-9]*)")

STOP = set("""
a about above after again against all also am an and any are as at be because been before being below between both
but by can could did do does doing down during each few for from further had has have having he her here hers him his
how i if in into is it its itself just me more most my no nor not now of off on once only or other our out over own
said same say says she should so some such than that the their them then there these they this those through to too
under until up very was we were what when where which while who whom why will with would you your yeah yes okay oh uh
um like know think mean really thing things going got get one two kind sort lot way actually right well just there's
it's that's don't didn't i'm you're he's they're we're there what's let thats also even still much many something
tells told telling about unknown time place saw took part relays named person summarises summarizes without source
frames host official document reads reports citing sources fact
""".split())
WORD = re.compile(r"[a-z0-9']+")


def words(text: str) -> set[str]:
    out = set()
    for w in WORD.findall((text or "").lower()):
        w = w.strip("'")
        if len(w) < 3 or w in STOP:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


def years_close(a: dict | None, b: dict | None) -> bool:
    if not a or not b or a.get("from") is None or b.get("from") is None:
        return False
    return a["from"] - ADJACENT_YEARS <= b["to"] and b["from"] - ADJACENT_YEARS <= a["to"]


class Probe:
    """What retrieval and the prompt know about the telling being linked."""

    def __init__(self, *, title, years, years_text, place_text, story_kind, teller, cites, documents, kind, quote, source):
        self.title, self.years, self.years_text, self.place_text = title, years, years_text, place_text
        self.story_kind, self.teller, self.cites, self.documents = story_kind, teller, cites, documents
        self.kind, self.quote, self.source = kind, quote, source
        self.words = words(f"{title} {quote}")

    def text(self, people: dict) -> str:
        name = lambda p: people[p]["name"] if p in people else p
        return "\n".join([
            f"title: {self.title}", f"years: {self.years_text or 'not given'}", f"place: {self.place_text or 'not given'}",
            f"story kind: {self.story_kind}", f"teller: {name(self.teller)} ({self.kind})",
            f"credits: {', '.join(name(c) for c in self.cites) or 'nobody'}",
            f"documents credited: {', '.join(self.documents) or 'none'}", f"from: {self.source}",
            f"quote: \"{self.quote}\""])


def probe_of_candidate(cand: dict, episode: str, aliases: dict[str, str]) -> Probe:
    """`aliases` is `person_aliases` of the run's root."""
    teller = person_id(cand["teller"], aliases)
    cites = [c for c in dict.fromkeys(person_id(n, aliases) for n in cand["cites"]) if c != teller]
    return Probe(title=cand["title"], years=cand["years"], years_text=cand.get("years_text"), place_text=cand.get("place_text"),
                 story_kind=cand["story_kind"], teller=teller, cites=cites, documents=cand.get("documents", []),
                 kind=cand["kind"], quote=cand["quote"], source=f"episode {episode} at {int(cand['from_s'])}s")


def probe_of_story(s: dict) -> Probe:
    t = s["tellings"][0]
    y = s.get("years")
    years_text = None if not y else (str(y["from"]) if y["from"] == y["to"] else f"{y['from']}-{y['to']}")
    src = f"episode {t['episode']} at {int(t.get('from_s') or 0)}s" if t.get("episode") else f"document {t.get('document')}"
    return Probe(title=s["title"], years=y, years_text=years_text, place_text=s.get("place_text") or s.get("place"),
                 story_kind=s.get("kind"), teller=t["teller"], cites=list(t.get("cites", [])), documents=list(t.get("documents", [])),
                 kind=t["kind"], quote=t.get("quote") or "", source=src)


class Index:
    """The stories as retrieval sees them: title, summary and first quote as rare-weighted words, plus people."""

    def __init__(self, stories: dict):
        self.stories = stories
        self.words: dict[str, set[str]] = {}
        self.df: dict[str, int] = {}
        for sid in stories:
            self._count(sid)
        self._weigh()

    def _count(self, sid: str) -> None:
        s = self.stories[sid]
        self.words[sid] = words(f"{s['title']} {s.get('summary', '')} {(s['tellings'][0].get('quote') or '') if s['tellings'] else ''}")
        for w in self.words[sid]:
            self.df[w] = self.df.get(w, 0) + 1

    def _weigh(self) -> None:
        n = len(self.words)
        self.idf = {w: math.log((n + 1) / (c + 1)) for w, c in self.df.items()}

    def add(self, sid: str) -> None:
        """A story put into the indexed dict during the run (a provisional story of a linked candidate)."""
        self._count(sid)
        self._weigh()

    def score(self, probe: Probe, sid: str) -> float:
        return self.score_story(probe, self.stories[sid], self.words[sid])

    def score_story(self, probe: Probe, s: dict, story_words: set[str]) -> float:
        """`probe` against any story dict (a provisional one not in the index too), word weights the index's."""
        tellers = {t["teller"] for t in s["tellings"]}
        cited = {c for t in s["tellings"] for c in t.get("cites", [])}
        x = W_CITE * (len(set(probe.cites) & (tellers | cited)) + (probe.teller in cited))
        x += W_TELLER * (probe.teller in tellers)
        x += W_YEARS * years_close(probe.years, s.get("years"))
        x += W_KIND * (probe.story_kind is not None and probe.story_kind == s.get("kind"))
        x += sum(self.idf.get(w, 0.0) for w in probe.words & story_words)
        return x

    def nearest(self, probe: Probe, pool) -> list[str]:
        scored = [(self.score(probe, sid), sid) for sid in pool]
        scored = [(x, sid) for x, sid in scored if x > 0]
        scored.sort(key=lambda p: (-p[0], p[1]))
        return [sid for _, sid in scored[:TOP]]


def stories_text(stories: dict, ids: list[str], people: dict) -> str:
    name = lambda p: people[p]["name"] if p in people else p
    out = []
    for sid in ids:
        s = stories[sid]
        y = s.get("years")
        lines = [f"<story id=\"{sid}\">", f"title: {s['title']}",
                 f"years: {'not given' if not y else (y['from'] if y['from'] == y['to'] else str(y['from']) + '-' + str(y['to']))}",
                 f"place: {s.get('place_text') or s.get('place') or 'not given'}", f"story kind: {s.get('kind')}",
                 f"summary: {s.get('summary', '')}"]
        for t in s["tellings"][:4]:
            cites = ", ".join(name(c) for c in t.get("cites", []))
            lines.append(f"telling by {name(t['teller'])} ({t['kind']}{', crediting ' + cites if cites else ''}): \"{t.get('quote') or ''}\"")
        if len(s["tellings"]) > 4:
            lines.append(f"and {len(s['tellings']) - 4} more tellings")
        lines.append("</story>")
        out.append("\n".join(lines))
    return "\n\n".join(out)


def template(root: Root) -> str:
    f = root.path / "prompts" / "link.md"
    text = (f if f.exists() else REPO / "prompts" / "link.md").read_text(encoding="utf-8")
    for key in ("{candidates}", "{stories}"):
        if key not in text:
            raise SystemExit(f"prompts/link.md must contain {key}")
    return text


def candidates_text(probes: list[Probe], people: dict) -> str:
    return "\n\n".join(f"<telling number=\"{n}\">\n{p.text(people)}\n</telling>" for n, p in enumerate(probes, 1))


def retry_note(error: Exception) -> str:
    return (f"\n\nYour previous answer was refused: {error}. Answer again with one decision for every telling, "
            "naming only a story id given in <stories> or an earlier telling of this group as #n.")


class Asker:
    """claude -p, or the prepared answers of a fixture. One call decides a group of tellings."""

    def __init__(self, root: Root, model: str, timeout: int, fixture: Path | None, complete=None):
        self.template, self.model, self.timeout = template(root), model, timeout
        self.complete = complete or llm.complete_json
        self.fixture = None
        if fixture:
            self.fixture = fixture_answers(load_json(fixture), fixture)
        self.used: list[str] = []
        self.calls = 0

    def ask(self, key: str, probes: list[Probe], stories: dict, ids: list[str], people: dict) -> list[dict]:
        """One decision per probe, in order; `ids` are the stories offered to the whole group."""
        self.calls += 1
        kinds = {i: stories[i].get("kind") for i in ids}
        if self.fixture is not None:
            if key not in self.fixture:
                raise SystemExit(f"link: fixture has no answer for {key!r} (offered {ids})")
            self.used.append(key)
            try:
                return validate(self.fixture[key], ids, probes, kinds)
            except ValueError as e:
                raise SystemExit(f"link: fixture answer for {key!r} refused: {e}")
        prompt = self.template.replace("{candidates}", candidates_text(probes, people)).replace(
            "{stories}", stories_text(stories, ids, people))
        print(f"link: {key!r}: {len(probes)} tellings against {len(ids)} stories -> claude -p {self.model}", file=sys.stderr)
        last, note = None, ""
        for attempt in range(2):
            try:
                return validate(self.complete(prompt + note, SCHEMA, model=self.model, timeout=self.timeout), ids,
                                probes, kinds)
            except llm.LlmUnavailable:
                raise
            except (llm.LlmError, ValueError) as e:
                last = e
                note = retry_note(e) if isinstance(e, ValueError) else ""
                print(f"link: {key!r}: {e}" + ("; asking once more" if attempt == 0 else ""), file=sys.stderr)
        raise SystemExit(f"link: {key!r}: no valid answer after two tries: {last}")


def group_key(episode: str | None, titles: list[str]) -> str:
    return f"{episode}: " + " | ".join(titles)


def fixture_answers(data, where: Path) -> dict:
    """The prepared answers as key to answer: a list of groups (candidate mode) or an object of story id to answer."""
    if isinstance(data, dict):
        return data
    if not isinstance(data, list):
        raise SystemExit(f"link: fixture {where} must be a list of groups or an object of story id to answer")
    out = {}
    for g in data:
        if not isinstance(g, dict) or set(g) != {"episode", "candidates", "decisions"}:
            raise SystemExit(f"link: fixture {where}: a group must have exactly episode, candidates, decisions: {str(g)[:200]}")
        key = group_key(g["episode"], g["candidates"])
        if key in out:
            raise SystemExit(f"link: fixture {where}: group {key!r} is given twice")
        out[key] = {"decisions": g["decisions"]}
    return out


def validate(ans, offered: list[str], probes: list[Probe], kinds: dict[str, str | None]) -> list[dict]:
    """The group's answer checked and normalised, one decision per probe in order. A decision's story is
    an offered id or `#n`, an earlier telling of the group; `#n` is kept for the caller to resolve. A
    `same` at another grain, or a `same` joining a `program` to a story of another kind, is downgraded
    to `new`: the model's reason is kept and `downgraded` says what was refused. `kinds` are the
    offered stories' kinds; an earlier telling's kind is that of the story it ends in."""
    if not isinstance(ans, dict) or set(ans) != {"decisions"} or not isinstance(ans["decisions"], list):
        raise ValueError(f"the answer must be an object with exactly a decisions list: {str(ans)[:200]}")
    items = ans["decisions"]
    for d in items:
        if not isinstance(d, dict) or set(d) != set(FIELDS):
            raise ValueError(f"a decision must have exactly {', '.join(FIELDS)}: {str(d)[:200]}")
    numbers = sorted(d["candidate"] for d in items if isinstance(d["candidate"], int))
    if numbers != list(range(1, len(probes) + 1)) or len(items) != len(probes):
        raise ValueError(f"the answer must decide each telling 1 to {len(probes)} once, "
                         f"got {[d['candidate'] for d in items]}")
    out: list[dict] = []
    ends: list[str | None] = []  # the kind of the story each telling ends in
    for d in sorted(items, key=lambda d: d["candidate"]):
        n, probe = d["candidate"], probes[d["candidate"] - 1]
        where = f"telling {n}"
        if d["decision"] not in DECISIONS:
            raise ValueError(f"{where}: decision {d['decision']!r} is not one of {DECISIONS}")
        if d["grain"] not in GRAINS:
            raise ValueError(f"{where}: grain {d['grain']!r} is not one of {GRAINS}")
        if not isinstance(d["reason"], str) or not d["reason"].strip() or not isinstance(d["difference"], str):
            raise ValueError(f"{where}: reason must be a non-empty string and difference a string")
        if d["decision"] == "new":
            story, difference, theirs = None, "", None
        else:
            story, difference = d["story"], norm_ws(d["difference"])
            m = EARLIER.fullmatch(story) if isinstance(story, str) else None
            if m and int(m.group(1)) < n:
                theirs = ends[int(m.group(1)) - 1]
            elif story in offered:
                theirs = kinds.get(story)
            else:
                raise ValueError(f"{where}: {d['decision']} names {story!r}, which is neither an offered story ({offered}) "
                                 f"nor an earlier telling of the group (#1 to #{n - 1})")
        link = {"decision": d["decision"], "story": story, "grain": d["grain"], "reason": norm_ws(d["reason"]),
                "difference": difference}
        if link["decision"] == "same":
            why = None
            if link["grain"] != "same":
                why = f"the telling is {link['grain']} than {story}: another grain is never the same story"
            elif probe.story_kind != theirs and "program" in (probe.story_kind, theirs):
                why = f"a {probe.story_kind} telling and the {theirs} story {story}: a program and a story of another kind are different grains"
            if why:
                link.update(decision="new", story=None, difference="", downgraded={"from": "same", "story": story, "why": why})
        ends.append(theirs if link["decision"] == "same" else probe.story_kind)
        out.append(link)
    return out


NOTHING = "no story shares a cited name, a teller, the years, the kind or a content word"


def alias_map(stories: dict) -> dict[str, str]:
    """Old id to the id of the story that absorbed it."""
    out: dict[str, str] = {}
    for sid, s in stories.items():
        for a in s.get("aliases", []):
            if a in stories:
                raise SystemExit(f"story {sid}: alias {a!r} is also a story id")
            if out.get(a, sid) != sid:
                raise SystemExit(f"alias {a!r} is claimed by both {out[a]} and {sid}")
            out[a] = sid
    return out


def resolve(sid, stories: dict, aliases: dict) -> str | None:
    if sid in stories:
        return sid
    return aliases.get(sid)


def fresh_id(sid: str, stories: dict, aliases: dict) -> str:
    """The id a new story gets: its slug, or the slug with the first free numbered suffix."""
    base, n = sid, 2
    while sid in stories or sid in aliases:
        sid, n = f"{base}-{n}", n + 1
    return sid


def candidate_files(root: Root, episodes: list[str] | None) -> list[Path]:
    """The candidate files to link or merge (every one, or the episodes named), in the order of their
    episode's date, then file name, so a story is created before a later episode can join it.
    An episode without a date comes after the dated ones."""
    files = [root.candidates / f"{e}.json" for e in episodes] if episodes else sorted(root.candidates.glob("*.json"))
    def key(f: Path):
        ep = root.episodes / f"{f.stem}.json"
        date = load_json(ep).get("published") if ep.exists() else None
        return (date is None, date or "", f.name)
    return sorted(files, key=key)


def as_told(framing: dict, story: dict) -> dict | None:
    """A telling's own framing ({title, years, place_text, story_kind}) when any of it differs from
    the story it joins, else None."""
    held = {"title": story["title"], "years": story.get("years"), "place_text": story.get("place_text"),
            "story_kind": story.get("kind")}
    return dict(framing) if framing != held else None


def framing_of_candidate(cand: dict) -> dict:
    t = cand.get("place_text")
    return {"title": cand["title"], "years": cand["years"],
            "place_text": norm_ws(t) if isinstance(t, str) and t.strip() else None, "story_kind": cand["story_kind"]}


def framing_of_story(s: dict) -> dict:
    return {"title": s["title"], "years": s.get("years"), "place_text": s.get("place_text"), "story_kind": s.get("kind")}


def provisional(cand: dict, eid: str, probe: Probe, sid: str) -> dict:
    """The story merge will create from a candidate linked `new` or `variant`, as retrieval needs it,
    so a later candidate of the same run can be linked to it."""
    f = framing_of_candidate(cand)
    return {"id": sid, "title": f["title"], "summary": "", "years": f["years"], "place_text": f["place_text"],
            "kind": f["story_kind"], "related": [],
            "tellings": [{"episode": eid, "from_s": cand["from_s"], "teller": probe.teller, "quote": cand["quote"],
                          "kind": cand["kind"], "cites": probe.cites, "documents": []}]}


def load_ledger(root: Root) -> tuple[Path, dict]:
    f = root.data / "links.json"
    ledger = load_json(f) if f.exists() else {"seen": [], "decisions": {}}
    if not {"seen", "decisions"} <= set(ledger) <= {"seen", "decisions", "downgraded"}:
        raise SystemExit(f"{rel(f, root.path)}: must hold seen and decisions, and may hold downgraded")
    return f, ledger


def note_downgrade(ledger: dict, key: str, episode: str | None, link: dict) -> None:
    ledger.setdefault("downgraded", []).append({"key": key, "episode": episode, "grain": link["grain"],
                                                "reason": link["reason"], **link["downgraded"]})


def held_by(stories: dict, episode: str, quote: str) -> str | None:
    q = norm_ws(quote)
    for sid, s in stories.items():
        if any(t.get("episode") == episode and norm_ws(t.get("quote") or "") == q for t in s["tellings"]):
            return sid
    return None


def connected(index: Index, probes: list[Probe], nearest: list[list[str]], cands: list[dict], eid: str) -> list[bool]:
    """Whether each candidate of a group is worth asking: it scores against a held story, or it and
    another candidate of the group score against each other (the later as probe, the earlier as the
    provisional story it may become)."""
    out = [bool(ids) for ids in nearest]
    for i in range(len(cands)):
        held = provisional(cands[i], eid, probes[i], f"#{i + 1}")
        held_words = words(f"{held['title']}  {held['tellings'][0]['quote']}")
        for j in range(i + 1, len(cands)):
            if index.score_story(probes[j], held, held_words) > 0:
                out[i] = out[j] = True
    return out


def resolve_earlier(link: dict, ends: list[str]) -> None:
    """`#n` in a decision of the group replaced by the story id telling n ends in."""
    def real(x):
        m = EARLIER.fullmatch(x) if isinstance(x, str) else None
        return ends[int(m.group(1)) - 1] if m else x
    if link["story"] is not None:
        link["story"] = real(link["story"])
    d = link.get("downgraded")
    if d and real(d["story"]) != d["story"]:
        d["why"] = d["why"].replace(d["story"], real(d["story"]))
        d["story"] = real(d["story"])


def run_candidates(root: Root, episodes: list[str] | None, asker: Asker, size: int = BATCH) -> dict:
    if size < 1:
        raise SystemExit(f"link: --batch must be at least 1, got {size}")
    stories = root.load_dir(root.stories)
    people = root.load_dir(root.people)
    names = person_aliases(root.path)
    story_aliases = alias_map(stories)
    index = Index(stories)
    files = candidate_files(root, episodes)
    for f in files:  # a resumed run holds the provisional stories the killed run created
        eid = load_json(f).get("episode")
        for cand in load_json(f)["candidates"]:
            link = cand.get("link")
            if link and link["decision"] in ("new", "variant") and link["id"] not in stories \
                    and link["id"] not in story_aliases:
                stories[link["id"]] = provisional(cand, eid, probe_of_candidate(cand, eid, names), link["id"])
                index.add(link["id"])
    stats = {"same": 0, "variant": 0, "new": 0, "skipped": 0, "calls": 0, "downgraded": 0}
    for f in files:
        batch = load_json(f)
        eid = batch.get("episode")
        todo = [c for c in batch["candidates"] if "link" not in c]  # a linked candidate was decided by an earlier run
        while todo:
            group: list[dict] = []
            while todo and len(group) < size:
                cand = todo.pop(0)
                if held_by(stories, eid, cand["quote"]):
                    stats["skipped"] += 1
                else:
                    group.append(cand)
            if not group:
                break
            probes = [probe_of_candidate(c, eid, names) for c in group]
            nearest = [index.nearest(p, stories) for p in probes]
            asked = [i for i, yes in enumerate(connected(index, probes, nearest, group, eid)) if yes]
            decided: dict[int, dict] = {}
            offered: list[str] = []
            if asked:
                offered = list(dict.fromkeys(sid for i in asked for sid in nearest[i]))
                key = group_key(eid, [group[i]["title"] for i in asked])
                answers = asker.ask(key, [probes[i] for i in asked], stories, offered, people)
                stats["calls"] += 1
                decided = dict(zip(asked, answers))
            ends: list[str] = []  # by position among the asked: the story id each ends in
            downgrades = []
            for i, cand in enumerate(group):
                link = decided.get(i) or {"decision": "new", "story": None, "reason": NOTHING, "difference": ""}
                if i in decided:
                    resolve_earlier(link, ends)
                link["against"] = list(dict.fromkeys(offered + ends)) if i in decided else []  # what the prompt let it name
                cand["link"] = link
                stats[link["decision"]] += 1
                if link["decision"] in ("new", "variant"):
                    sid = fresh_id(story_id(cand["title"], cand["years"]), stories, story_aliases)
                    link["id"] = sid
                    stories[sid] = provisional(cand, eid, probes[i], sid)
                    index.add(sid)
                if i in decided:
                    ends.append(link["id"] if link["decision"] != "same" else link["story"])
                if "downgraded" in link:
                    stats["downgraded"] += 1
                    downgrades.append((cand["title"], link))
                print(f"link: {eid}: {cand['title']!r}: {link['decision']} {link['story'] or ''}", file=sys.stderr)
            save_json(f, batch)
            if downgrades:
                ledger_file, ledger = load_ledger(root)
                for title, link in downgrades:
                    note_downgrade(ledger, title, eid, link)
                save_json(ledger_file, ledger)
    print("link: " + ", ".join(f"{v} {k}" for k, v in stats.items()), file=sys.stderr)
    return stats


def telling_key(t: dict) -> tuple:
    return (t.get("episode"), t.get("document"), norm_ws(t.get("quote") or ""))


def add_relation(s: dict, other: str, relation: str, note: str) -> bool:
    if any(r.get("story") == other and r.get("relation") == relation for r in s["related"]):
        return False
    s["related"].append({"story": other, "relation": relation, "note": note})
    return True


def fold(stories: dict, loser: str, survivor: str, reason: str, difference: str) -> None:
    """The later story into the earlier: tellings, relations, references, discussion, aliases; the loser is removed."""
    lo, su = stories.pop(loser), stories[survivor]
    have = {telling_key(t) for t in su["tellings"]}
    told = as_told(framing_of_story(lo), su)
    for t in lo["tellings"]:
        if telling_key(t) in have:
            continue
        t = dict(t)
        t["difference"] = difference
        t["link_reason"] = reason
        if told and "as_told" not in t:  # a telling that joined the loser keeps its own framing
            t["as_told"] = told
        su["tellings"].append(t)
        have.add(telling_key(t))
    for r in lo["related"]:
        if r.get("story") not in (survivor, loser):
            add_relation(su, r["story"], r["relation"], r.get("note", ""))
    su["related"] = [r for r in su["related"] if r.get("story") != loser]
    for sid, s in stories.items():
        if sid == survivor:
            continue
        moved = [r for r in s["related"] if r.get("story") == loser]
        s["related"] = [r for r in s["related"] if r.get("story") != loser]
        for r in moved:
            add_relation(s, survivor, r["relation"], r.get("note", ""))
    for key in ("claims", "tags"):
        for x in lo.get(key, []):
            if x not in su.setdefault(key, []):
                su[key].append(x)
    if lo.get("discussion"):  # the debate about the loser is the debate about the survivor, appended in order
        su["discussion"] = su.get("discussion", []) + [e for e in lo["discussion"] if e not in su.get("discussion", [])]
    if su.get("place") is None and lo.get("place") is not None:
        su["place"] = lo["place"]
    if su.get("place_text") is None and lo.get("place_text"):
        su["place_text"] = lo["place_text"]
    su["aliases"] = list(dict.fromkeys(su.get("aliases", []) + [loser] + lo.get("aliases", [])))


def born_linked(root: Root, stories: dict) -> set[str]:
    """The stories whose first telling came from a candidate linked `new` or `variant`."""
    firsts = {(s["tellings"][0].get("episode"), norm_ws(s["tellings"][0].get("quote") or "")): sid
              for sid, s in stories.items() if s["tellings"]}
    out = set()
    for f in sorted(root.candidates.glob("*.json")) if root.candidates.exists() else []:
        batch = load_json(f)
        for c in batch["candidates"]:
            if c.get("link", {}).get("decision") in ("new", "variant"):
                sid = firsts.get((batch.get("episode"), norm_ws(c["quote"])))
                if sid:
                    out.add(sid)
    return out


def run_existing(root: Root, asker: Asker, dry_run: bool = False) -> dict:
    stories = root.load_dir(root.stories)
    people = root.load_dir(root.people)
    ledger_file, ledger = load_ledger(root)
    born = born_linked(root, stories)  # compared with the corpus when their candidate was linked
    seen_before = set(ledger["seen"]) | born
    ledger["seen"] = sorted((seen_before | set(stories)) - born)
    index = Index(stories)  # word weights fixed at the start of the run
    stats = {"same": 0, "variant": 0, "new": 0, "calls": 0, "pending": 0}
    for sid in sorted(stories):
        if sid not in stories or sid in born:
            continue  # folded earlier in this run, or linked when it was created
        aliases = alias_map(stories)
        # a story born from a linked candidate was compared with the corpus when it arrived
        earlier = [x for x in sorted(stories) if x < sid and x not in born]
        if sid in ledger["decisions"]:
            earlier = [x for x in earlier if x not in seen_before]
        if not earlier:
            continue
        probe = probe_of_story(stories[sid])
        ids = index.nearest(probe, earlier)
        if not ids:
            if sid not in ledger["decisions"]:
                ledger["decisions"][sid] = [{"decision": "new", "story": None, "reason": NOTHING, "difference": "", "against": []}]
            continue
        if dry_run:
            stats["pending"] += 1
            print(f"link: would ask {sid} against {ids}", file=sys.stderr)
            continue
        ans = asker.ask(sid, [probe], stories, ids, people)[0]
        stats["calls"] += 1
        stats[ans["decision"]] += 1
        ans["against"] = ids
        ledger["decisions"].setdefault(sid, []).append(ans)
        if "downgraded" in ans:
            note_downgrade(ledger, sid, None, ans)
        target = resolve(ans["story"], stories, aliases) if ans["story"] else None
        if ans["decision"] == "same":
            fold(stories, sid, target, ans["reason"], ans["difference"])
            (root.stories / f"{sid}.json").unlink()
        elif ans["decision"] == "variant":
            add_relation(stories[sid], target, "variant", ans["reason"])
            add_relation(stories[target], sid, "variant", ans["reason"])
        for s in stories.values():
            save_json(root.stories / f"{s['id']}.json", s)
        save_json(ledger_file, ledger)
        print(f"link: {sid}: {ans['decision']} {target or ''}", file=sys.stderr)
    if not dry_run:
        save_json(ledger_file, ledger)
    print("link --existing: " + ", ".join(f"{v} {k}" for k, v in stats.items()), file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("episodes", nargs="*", help="candidate files to link (default: every one)")
    ap.add_argument("--existing", action="store_true", help="link the stories in data/stories among themselves")
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--timeout", type=int, default=300, help="seconds per call")
    ap.add_argument("--batch", type=int, default=None, help=f"candidates per call (candidate mode, default {BATCH})")
    ap.add_argument("--fixture", type=Path, help="prepared answers instead of claude -p")
    ap.add_argument("--dry-run", action="store_true", help="--existing only: list the calls a run would make")
    ap.add_argument("--root", type=Path, default=REPO)
    a = ap.parse_args(argv)
    root = Root(a.root)
    asker = Asker(root, a.model, a.timeout, a.fixture)
    if a.existing:
        if a.episodes:
            raise SystemExit("link: --existing takes no episodes")
        if a.batch is not None:
            raise SystemExit("link: --existing takes no --batch")
        run_existing(root, asker, a.dry_run)
    else:
        run_candidates(root, a.episodes or None, asker, BATCH if a.batch is None else a.batch)
    return 0


if __name__ == "__main__":
    sys.exit(main())
