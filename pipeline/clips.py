"""Clips a host cut into another episode: who speaks them, where they are from, and the tellings inside them.

    uv run python -m pipeline.clips [--root DIR] [--model opus] [--batch 6] [--timeout 600] [--fixture FILE] [--no-apply | --report]

A host edits clips of other people into his episodes (a guest of another episode, a news interview,
a documentary), and extract.py, which credits a quote to whoever the episode seems to be about,
then makes the clip's words a telling by the wrong person: a second, false teller. This stage finds
the passages two episodes share and corrects the tellings inside them.

Detect: every episode's caption text, reduced by `norm_quote`, lowercased and cut into words
(`[a-z0-9']+`), is indexed by word 8-grams; a shingle that occurs in more than 6 episodes is
boilerplate and ignored (the count of such shingles is printed with the run's stats). For each pair of episodes the shared shingles are chained into runs, a
gap of up to 12 words or a shift of up to 3 words allowed (two uploads of one clip are captioned
apart, so a misheard word breaks an exact chain), and a run of at least 15 words is an occurrence
in both episodes. Occurrences that overlap within one episode are one occurrence, and occurrences
joined by a run are one group, so a clip aired in three episodes is one group of three.

Judge: the groups without a verdict go to `claude -p` with prompts/clips.md, --batch (6) groups a
call; for each occurrence the prompt gives the episode's show, title, host, guests and published
date, the people the corpus knows in that episode, and about 60 s of caption text before and after
the shared passage with the `>>` speaker changes. The answer for each group is `clip` (the passage
is one recording aired more than once: the speaker, and the occurrence it originally belongs to
or `outside` when every occurrence replays a recording from outside the corpus), `not-a-clip` (the
words coincide but each episode's own speaker says them, such as two people reading one document)
or `unclear`, with a short reason; a clip also names `also_heard`, the other people heard in the passage
(an interviewer asking the questions). A speaker the prompt lists is answered by id; any other name
resolves through `person_id` and data/person-aliases.json. A refused answer is asked once more with
a note, a second refusal stops the run; the ledger is saved after each answered call, so a killed
run resumes at the first group without a verdict.

The ledger is data/clips.json: `{ "params", "groups": [...] }`, each group `{ "id", "text",
"occurrences": [ { "episode", "from_s", "to_s", "words" } ], "verdict", "speaker",
"speaker_name", "also_heard", "origin", "reason", "model" }` (schema.md). A run keeps a group's verdict while
detection finds the same occurrences; a group whose occurrences change is judged again. A group
marked `"by": "hand"` is kept exactly as written and never asked about, and a detected group that
overlaps it is dropped.

Apply (the default; --no-apply stops after judging, --report judges and prints what apply would
change without writing a story): for every `clip` group, a story telling whose span lies inside
an occurrence (4 s of slack at either end, the cue granularity) that is not the origin gets
`replay_of` (`{ "episode", "from_s" }` of the origin occurrence, or `{ "outside": true }`). When
its teller is neither the clip's speaker nor one of `also_heard` (the interviewer's own lines in a
replayed exchange stay his), the speaker becomes its `teller` and the teller extract.py gave is kept
as `teller_was`. A telling inside the origin occurrence gets no `replay_of`, only that teller
correction. A telling that carries `replay_of` or `teller_was` but lies in no `clip` group any
more is restored (its `teller_was` back as `teller`). A speaker who becomes a teller and has no
person file gets one. Re-running changes nothing. Runs after merge and before score.

--fixture FILE replaces `claude -p` with prepared answers: a JSON object from group id to the
answer for that group (`{ "verdict", "speaker", "also_heard", "origin", "reason" }`, origin `#n` or `outside`);
a group asked for that the file lacks fails.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

from . import llm
from .merge import ensure_person, role_for
from .common import REPO, Captions, Root, fmt_s, load_json, norm_quote, norm_ws, person_aliases, person_id, rel, save_json

SHINGLE = 8
MIN_WORDS = 15
MAX_SHINGLE = 6
JOIN_GAP = 12
JOIN_SHIFT = 3
CONTEXT_S = 60
SLACK_S = 4
BATCH = 6
VERDICTS = ("clip", "not-a-clip", "unclear")
WORD = re.compile(r"[a-z0-9']+")
PARAMS = {"shingle": SHINGLE, "min_words": MIN_WORDS, "max_shingle_count": MAX_SHINGLE, "join_gap": JOIN_GAP,
          "join_shift": JOIN_SHIFT, "slack_s": SLACK_S}
GROUP_KEYS = ("id", "text", "occurrences", "verdict", "speaker", "speaker_name", "also_heard", "origin", "reason", "model", "by")
OCC_KEYS = ("episode", "from_s", "to_s", "words")

SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "group": {"type": "integer"},
                    "reason": {"type": "string"},
                    "verdict": {"type": "string", "enum": list(VERDICTS)},
                    "speaker": {"type": ["string", "null"]},
                    "also_heard": {"type": "array", "items": {"type": "string"}},
                    "origin": {"type": ["string", "null"]},
                },
                "required": ["group", "reason", "verdict", "speaker", "also_heard", "origin"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["groups"],
    "additionalProperties": False,
}


# ---- detect ------------------------------------------------------------------------------------

class Words:
    """One episode's caption text as words, each with its cue."""

    def __init__(self, caps: Captions):
        self.caps = caps
        self.words: list[str] = []
        self.cue: list[int] = []
        for i, text in enumerate(caps.texts):
            for w in WORD.findall(norm_quote(text).lower()):
                self.words.append(w)
                self.cue.append(i)

    def from_s(self, w: int) -> float:
        return self.caps.seconds[self.cue[w]]

    def to_s(self, w_end: int) -> float:
        """The start of the cue after the one holding word w_end - 1 (the convention of `Captions.locate`)."""
        c = self.cue[w_end - 1]
        return self.caps.seconds[c + 1] if c + 1 < len(self.caps.seconds) else self.caps.seconds[c]


def load_words(root: Root, episodes: dict) -> dict[str, Words]:
    return {eid: Words(Captions(root.caption_text(e))) for eid, e in sorted(episodes.items())}


def pair_runs(words: dict[str, Words]) -> tuple[list[tuple[str, int, int, str, int, int]], int]:
    """(episode a, a from word, a end word, episode b, b from word, b end word) for every shared run
    of at least MIN_WORDS words between two different episodes, a < b; and the number of shingles
    left out as boilerplate."""
    index: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for eid, w in words.items():
        ws = w.words
        for i in range(len(ws) - SHINGLE + 1):
            index[" ".join(ws[i:i + SHINGLE])].append((eid, i))
    hits: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    boilerplate = 0
    for occ in index.values():
        eps = len({e for e, _ in occ})
        if eps > MAX_SHINGLE:
            boilerplate += 1
        if eps > MAX_SHINGLE or eps < 2:
            continue
        for ea, ia in occ:
            for eb, ib in occ:
                if ea < eb:
                    hits[(ea, eb)].append((ia, ib))
    out = []
    for (ea, eb), ps in sorted(hits.items()):
        runs: list[list[int]] = []  # [a0, a1, b0, b1, offset] with a1, b1 the last shingle starts
        for ia, ib in sorted(ps):
            for r in runs:
                if ia <= r[1] + JOIN_GAP and abs((ib - ia) - r[4]) <= JOIN_SHIFT:
                    r[1], r[2], r[3], r[4] = max(r[1], ia), min(r[2], ib), max(r[3], ib), ib - ia
                    break
            else:
                runs.append([ia, ia, ib, ib, ib - ia])
        for a0, a1, b0, b1, _ in runs:
            if a1 + SHINGLE - a0 >= MIN_WORDS:
                out.append((ea, a0, a1 + SHINGLE, eb, b0, b1 + SHINGLE))
    return out, boilerplate


def detect(words: dict[str, Words]) -> tuple[list[dict], int]:
    """The groups (occurrences overlapping in one episode merged, occurrences joined by a run grouped)
    and the number of boilerplate shingles left out."""
    runs, boilerplate = pair_runs(words)
    spans: dict[str, list[list[int]]] = defaultdict(list)
    for ea, a0, a1, eb, b0, b1 in runs:
        spans[ea].append([a0, a1])
        spans[eb].append([b0, b1])
    merged: dict[str, list[list[int]]] = {}
    for eid, ss in spans.items():
        ss.sort()
        m: list[list[int]] = []
        for s in ss:
            if m and s[0] < m[-1][1]:
                m[-1][1] = max(m[-1][1], s[1])
            else:
                m.append(list(s))
        merged[eid] = m

    def node(eid: str, w0: int) -> tuple[str, int]:
        for k, (a, b) in enumerate(merged[eid]):
            if a <= w0 < b:
                return eid, k
        raise AssertionError(f"clips: no merged span holds word {w0} of {eid}")

    parent: dict[tuple[str, int], tuple[str, int]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for ea, a0, _, eb, b0, _ in runs:
        parent[find(node(ea, a0))] = find(node(eb, b0))
    comps: dict[tuple[str, int], list[tuple[str, int]]] = defaultdict(list)
    for eid, m in merged.items():
        for k in range(len(m)):
            comps[find((eid, k))].append((eid, k))
    groups = []
    for members in comps.values():
        members = sorted(members, key=lambda x: (x[0], merged[x[0]][x[1]][0]))
        occs = []
        for eid, k in members:
            a, b = merged[eid][k]
            w = words[eid]
            occs.append({"episode": eid, "from_s": w.from_s(a), "to_s": w.to_s(b), "words": b - a})
        a, b = merged[members[0][0]][members[0][1]]
        text = " ".join(words[members[0][0]].words[a:b])
        groups.append({"id": f"{occs[0]['episode']}-{int(occs[0]['from_s'])}", "text": text[:400], "occurrences": occs})
    groups.sort(key=lambda g: g["id"])
    seen: dict[str, int] = {}
    for g in groups:  # two groups starting in the same second of one episode: number the later
        n = seen.get(g["id"], 0)
        seen[g["id"]] = n + 1
        if n:
            g["id"] = f"{g['id']}-{n + 1}"
    return groups, boilerplate


def overlaps(a: dict, b: dict) -> bool:
    return a["episode"] == b["episode"] and a["from_s"] < b["to_s"] and b["from_s"] < a["to_s"]


def same_occurrences(a: list[dict], b: list[dict]) -> bool:
    key = lambda o: (o["episode"], o["from_s"], o["to_s"])
    return sorted(map(key, a)) == sorted(map(key, b))


def reconcile(detected: list[dict], old: list[dict]) -> list[dict]:
    """The ledger's groups after a detection: hand groups as written, a detected group overlapping one
    dropped; a detected group with exactly the occurrences of a judged group keeps its id and verdict;
    every other detected group is new and unjudged."""
    hand = [g for g in old if g.get("by") == "hand"]
    judged = [g for g in old if g.get("by") != "hand"]
    out = list(hand)
    for g in detected:
        if any(overlaps(o, ho) for hg in hand for ho in hg["occurrences"] for o in g["occurrences"]):
            continue
        prev = next((p for p in judged if same_occurrences(p["occurrences"], g["occurrences"])), None)
        if prev is not None:
            out.append({**prev, "text": g["text"], "occurrences": g["occurrences"]})
        else:
            out.append({**g, "verdict": None, "speaker": None, "speaker_name": None, "also_heard": [], "origin": None, "reason": None, "model": None})
    ids: set[str] = set()
    for g in sorted(out, key=lambda g: (g.get("by") != "hand", g["id"])):
        base, n = g["id"], 1
        while g["id"] in ids:
            n += 1
            g["id"] = f"{base}-{n}"
        ids.add(g["id"])
    return sorted(out, key=lambda g: g["id"])


# ---- the ledger --------------------------------------------------------------------------------

def ledger_path(root: Root) -> Path:
    return root.data / "clips.json"


def load_ledger(root: Root) -> dict:
    f = ledger_path(root)
    if not f.exists():
        return {"params": PARAMS, "groups": []}
    led = load_json(f)
    if not isinstance(led, dict) or not isinstance(led.get("groups"), list):
        raise SystemExit(f"{rel(f, root.path)}: must be an object with a groups list")
    return led


def ledger_problems(led, episodes: dict, where: str = "data/clips.json") -> list[str]:
    """The ledger's shape: every group has an id, two or more occurrences in known episodes, a known
    verdict (or none yet), and a clip a speaker and an origin that is `outside` or one of its occurrences."""
    if not isinstance(led, dict) or not isinstance(led.get("groups"), list):
        return [f"{where}: must be an object with a groups list"]
    out: list[str] = []
    ids: set[str] = set()
    for i, g in enumerate(led["groups"]):
        gw = f"{where} group {i + 1}"
        if not isinstance(g, dict):
            out.append(f"{gw}: must be an object")
            continue
        gw = f"{where} group {g.get('id')!r}"
        for k in sorted(set(g) - set(GROUP_KEYS)):
            out.append(f"{gw}: unknown field {k!r}")
        if not isinstance(g.get("id"), str) or not g["id"]:
            out.append(f"{gw}: id must be a non-empty string")
        elif g["id"] in ids:
            out.append(f"{gw}: id is used twice")
        else:
            ids.add(g["id"])
        if g.get("by") not in (None, "hand"):
            out.append(f"{gw}: by must be \"hand\" when present")
        occs = g.get("occurrences")
        if not isinstance(occs, list) or len(occs) < 2:
            out.append(f"{gw}: needs a list of two or more occurrences")
            occs = []
        for j, o in enumerate(occs):
            ow = f"{gw} occurrence {j + 1}"
            if not isinstance(o, dict) or set(o) != set(OCC_KEYS):
                out.append(f"{ow}: must have exactly {', '.join(OCC_KEYS)}")
                continue
            if o["episode"] not in episodes:
                out.append(f"{ow}: episode {o['episode']!r} is not in data/episodes")
            if not all(isinstance(o[k], (int, float)) and not isinstance(o[k], bool) for k in ("from_s", "to_s", "words")) \
                    or o["from_s"] > o["to_s"]:
                out.append(f"{ow}: from_s, to_s and words must be numbers, from_s not after to_s")
        v = g.get("verdict")
        if v is None:
            continue
        if v not in VERDICTS:
            out.append(f"{gw}: verdict {v!r} is not one of {', '.join(VERDICTS)}")
            continue
        if not (isinstance(g.get("reason"), str) and g["reason"].strip()):
            out.append(f"{gw}: a judged group needs a reason")
        if g.get("by") != "hand" and not isinstance(g.get("model"), str):
            out.append(f"{gw}: a judged group needs the model that judged it (or by: hand)")
        heard = g.get("also_heard", [])
        if not (isinstance(heard, list) and all(isinstance(p, str) and p for p in heard)):
            out.append(f"{gw}: also_heard must be a list of person ids")
        if v == "clip":
            if not (isinstance(g.get("speaker"), str) and g["speaker"]):
                out.append(f"{gw}: a clip needs a speaker (a person id)")
            o = g.get("origin")
            if o != "outside" and not (isinstance(o, dict) and set(o) == {"episode", "from_s"}
                                       and any(x.get("episode") == o["episode"] and x.get("from_s") == o["from_s"] for x in occs if isinstance(x, dict))):
                out.append(f"{gw}: origin {o!r} must be \"outside\" or {{episode, from_s}} of one of its occurrences")
        elif g.get("speaker") is not None or g.get("origin") is not None or heard:
            out.append(f"{gw}: a {v} group has no speaker, no also_heard and no origin")
    return out


# ---- judge -------------------------------------------------------------------------------------

def template(root: Root) -> str:
    f = root.path / "prompts" / "clips.md"
    text = (f if f.exists() else REPO / "prompts" / "clips.md").read_text(encoding="utf-8")
    if "{groups}" not in text:
        raise SystemExit("prompts/clips.md must contain {groups}")
    return text


def person_label(p: str, people: dict) -> str:
    return people[p]["name"] if p in people else p


def known_people(eid: str, episodes: dict, people: dict, stories: dict, aliases: dict) -> dict[str, str]:
    """{person id: name} for the host, the guests and every teller of the episode in the corpus."""
    e = episodes[eid]
    ids = []
    if e.get("host"):
        ids.append(e["host"] if e["host"] in people else person_id(e["host"], aliases))
    for g in e.get("guests") or []:
        ids.append(g if g in people else person_id(g, aliases))
    for s in stories.values():
        for t in s["tellings"]:
            if t.get("episode") == eid:
                ids.append(t.get("teller_was") or t["teller"])
    out = {}
    for p in dict.fromkeys(ids):
        out[p] = people[p]["name"] if p in people else p.replace("-", " ").title()
    return out


def occurrence_text(n: int, o: dict, w: Words, episodes: dict, people: dict, known: dict[str, str]) -> str:
    e = episodes[o["episode"]]
    caps = w.caps
    lines = caps.lines()
    before = [l for s, l in zip(caps.seconds, lines) if o["from_s"] - CONTEXT_S <= s < o["from_s"]]
    inside = [l for s, l in zip(caps.seconds, lines) if o["from_s"] <= s < o["to_s"]] or \
             [l for s, l in zip(caps.seconds, lines) if s == o["from_s"]]
    after = [l for s, l in zip(caps.seconds, lines) if o["to_s"] <= s < o["to_s"] + CONTEXT_S]
    guests = ", ".join(person_label(g, people) for g in e.get("guests") or []) or "none listed"
    host = person_label(e["host"], people) if e.get("host") else "not listed"
    return "\n".join([
        f"<occurrence number=\"{n}\">",
        f"episode: {e['id']}; show: {e.get('show') or 'unknown'}; title: {e.get('title') or 'unknown'}",
        f"host: {host}; guests: {guests}; published: {e.get('published') or 'unknown'}",
        "people the corpus knows in this episode: " + "; ".join(f"{name} (id {pid})" for pid, name in known.items()),
        f"shared passage: {fmt_s(o['from_s'])} to {fmt_s(o['to_s'])}",
        "before:", *before, "shared passage:", *inside, "after:", *after,
        "</occurrence>"])


def group_text(n: int, g: dict, words: dict[str, Words], episodes, people, stories, aliases) -> str:
    occ = [occurrence_text(k, o, words[o["episode"]], episodes, people,
                           known_people(o["episode"], episodes, people, stories, aliases))
           for k, o in enumerate(g["occurrences"], 1)]
    return "\n".join([f"<group number=\"{n}\">", f"the shared words: \"{g['text']}\"", *occ, "</group>"])


def validate(ans, size: int, n_occ: list[int]) -> list[dict]:
    """One answer per group 1..size, in order: a clip names a speaker and an origin `#k` or `outside`;
    any other verdict names neither."""
    if not isinstance(ans, dict) or set(ans) != {"groups"} or not isinstance(ans["groups"], list):
        raise ValueError(f"the answer must be an object with exactly a groups list: {str(ans)[:200]}")
    got: dict[int, dict] = {}
    for a in ans["groups"]:
        if not isinstance(a, dict) or set(a) != {"group", "reason", "verdict", "speaker", "also_heard", "origin"}:
            raise ValueError(f"a group answer must have exactly group, reason, verdict, speaker, also_heard and origin: {str(a)[:200]}")
        if not isinstance(a["also_heard"], list) or not all(isinstance(p, str) and p.strip() for p in a["also_heard"]):
            raise ValueError(f"group {a.get('group')}: also_heard must be a list of names or ids")
        n = a["group"]
        if not isinstance(n, int) or not 1 <= n <= size:
            raise ValueError(f"group {n!r} is not one of 1 to {size}")
        if n in got:
            raise ValueError(f"group {n} is answered twice")
        if a["verdict"] not in VERDICTS:
            raise ValueError(f"group {n}: verdict {a['verdict']!r} is not one of {', '.join(VERDICTS)}")
        if not isinstance(a["reason"], str) or not a["reason"].strip():
            raise ValueError(f"group {n}: reason must be a non-empty string")
        if a["verdict"] == "clip":
            if not isinstance(a["speaker"], str) or not a["speaker"].strip():
                raise ValueError(f"group {n}: a clip needs the speaker's name or id")
            o = a["origin"]
            m = re.fullmatch(r"#(\d+)", o) if isinstance(o, str) else None
            if o != "outside" and not (m and 1 <= int(m.group(1)) <= n_occ[n - 1]):
                raise ValueError(f"group {n}: origin {o!r} must be #1 to #{n_occ[n - 1]} or outside")
        elif a["speaker"] is not None or a["origin"] is not None or a["also_heard"]:
            raise ValueError(f"group {n}: a {a['verdict']} answer has speaker and origin null and also_heard empty")
        got[n] = {**a, "reason": norm_ws(a["reason"].replace(" \u2014 ", ", ").replace("\u2014", ", "))}
    missing = [n for n in range(1, size + 1) if n not in got]
    if missing:
        raise ValueError(f"no answer for group(s) {missing}")
    return [got[n] for n in range(1, size + 1)]


def retry_note(error: Exception) -> str:
    return (f"\n\nYour previous answer was refused: {error}. Answer again with exactly one entry for every group "
            "above, numbered as the groups are, a clip's origin as #n of one of its occurrences or outside.")


class Asker:
    """claude -p, or the prepared answers of a fixture. One call judges a batch of groups."""

    def __init__(self, root: Root, model: str, timeout: int, fixture: Path | None, complete=None):
        self.template, self.model, self.timeout = template(root), model, timeout
        self.complete = complete or llm.complete_json
        self.fixture = None
        if fixture:
            self.fixture = load_json(fixture)
            if not isinstance(self.fixture, dict):
                raise SystemExit(f"clips: fixture {fixture} must be an object of group id to answer")
        self.calls = 0
        self.used: set[str] = set()

    def ask(self, text: str, ids: list[str], n_occ: list[int]) -> list[dict]:
        self.calls += 1
        if self.fixture is not None:
            missing = [i for i in ids if i not in self.fixture]
            if missing:
                raise SystemExit(f"clips: fixture has no answer for {missing}")
            self.used |= set(ids)
            ans = {"groups": [{"group": n, **self.fixture[i]} for n, i in enumerate(ids, 1)]}
            try:
                return validate(ans, len(ids), n_occ)
            except ValueError as e:
                raise SystemExit(f"clips: fixture answer refused: {e}")
        prompt = self.template.replace("{groups}", text)
        print(f"clips: {len(ids)} groups ({ids[0]} ...) -> claude -p {self.model}", file=sys.stderr)
        last, note = None, ""
        for attempt in range(2):
            try:
                return validate(self.complete(prompt + note, SCHEMA, model=self.model, timeout=self.timeout), len(ids), n_occ)
            except llm.LlmUnavailable:
                raise
            except (llm.LlmError, ValueError) as e:
                last = e
                note = retry_note(e) if isinstance(e, ValueError) else ""
                print(f"clips: {e}" + ("; asking once more" if attempt == 0 else ""), file=sys.stderr)
        raise SystemExit(f"clips: {ids[0]} ...: no valid answer after two tries: {last}")


def record(g: dict, a: dict, model: str, people: dict, aliases: dict) -> None:
    g["verdict"], g["reason"], g["model"] = a["verdict"], a["reason"], model
    g["speaker"] = g["speaker_name"] = g["origin"] = None
    g["also_heard"] = []
    if a["verdict"] != "clip":
        return
    s = norm_ws(a["speaker"])
    g["speaker"] = s if s in people else person_id(s, aliases)
    heard = [p if p in people else person_id(p, aliases) for p in map(norm_ws, a["also_heard"])]
    g["also_heard"] = [p for p in dict.fromkeys(heard) if p != g["speaker"]]
    g["speaker_name"] = people[s]["name"] if s in people else (s.replace("-", " ").title() if re.fullmatch(r"[a-z0-9-]+", s) else s)
    if a["origin"] == "outside":
        g["origin"] = "outside"
    else:
        o = g["occurrences"][int(a["origin"][1:]) - 1]
        g["origin"] = {"episode": o["episode"], "from_s": o["from_s"]}


def judge(root: Root, asker: Asker, words: dict[str, Words], size: int = BATCH) -> dict:
    """Detect, reconcile with the ledger, and ask about every group without a verdict; the ledger is
    saved after each call."""
    if size < 1:
        raise SystemExit(f"clips: --batch must be at least 1, got {size}")
    episodes = root.load_dir(root.episodes)
    people = root.load_dir(root.people)
    stories = root.load_dir(root.stories)
    aliases = person_aliases(root.path)
    led = load_ledger(root)
    bad = ledger_problems(led, episodes)
    if bad:
        raise SystemExit("clips: the ledger has problems:\n" + "\n".join(bad))
    detected, boilerplate = detect(words)
    led = {"params": PARAMS, "groups": reconcile(detected, led["groups"])}
    save_json(ledger_path(root), led)
    todo = [g for g in led["groups"] if g.get("by") != "hand" and g.get("verdict") is None]
    stats = {"groups": len(led["groups"]), "boilerplate_shingles": boilerplate, "asked": len(todo), "calls": 0}
    for i in range(0, len(todo), size):
        batch = todo[i:i + size]
        text = "\n\n".join(group_text(n, g, words, episodes, people, stories, aliases) for n, g in enumerate(batch, 1))
        answers = asker.ask(text, [g["id"] for g in batch], [len(g["occurrences"]) for g in batch])
        stats["calls"] += 1
        for g, a in zip(batch, answers):
            record(g, a, asker.model, people, aliases)
        save_json(ledger_path(root), led)
        print(f"clips: {min(i + size, len(todo))} of {len(todo)} groups judged", file=sys.stderr)
    return stats


# ---- apply -------------------------------------------------------------------------------------

def inside(t: dict, o: dict) -> bool:
    if t.get("episode") != o["episode"] or not isinstance(t.get("from_s"), (int, float)):
        return False
    to = t.get("to_s") if isinstance(t.get("to_s"), (int, float)) else t["from_s"]
    return o["from_s"] - SLACK_S <= t["from_s"] and to <= o["to_s"] + SLACK_S


def covering(t: dict, groups: list[dict]) -> tuple[dict, dict] | None:
    """The clip group and occurrence a telling lies inside, or None."""
    for g in groups:
        if g.get("verdict") != "clip":
            continue
        for o in g["occurrences"]:
            if inside(t, o):
                return g, o
    return None


def corrected(t: dict, groups: list[dict]) -> dict:
    """The telling as the ledger makes it (a copy; the input is untouched)."""
    new = dict(t)
    original = t.get("teller_was") or t["teller"]
    hit = covering(t, groups)
    new.pop("replay_of", None)
    new.pop("teller_was", None)
    new["teller"] = original
    if hit is None:
        return new
    g, o = hit
    origin = g["origin"]
    if origin == "outside":
        new["replay_of"] = {"outside": True}
    elif not (o["episode"] == origin["episode"] and o["from_s"] == origin["from_s"]):
        new["replay_of"] = {"episode": origin["episode"], "from_s": origin["from_s"]}
    if g["speaker"] != original and original not in g.get("also_heard", []):
        new["teller"] = g["speaker"]
        new["teller_was"] = original
    return new


def apply(root: Root, write: bool) -> list[dict]:
    """Every telling the ledger changes, as {story, n, episode, from_s, teller_was, teller, replay_of,
    quote, before, after}; with write, the stories and the person file of any speaker who becomes a teller
    and has none are saved."""
    led = load_ledger(root)
    episodes = root.load_dir(root.episodes)
    bad = ledger_problems(led, episodes)
    if bad:
        raise SystemExit("clips: the ledger has problems:\n" + "\n".join(bad))
    groups = led["groups"]
    stories = root.load_dir(root.stories)
    people = root.load_dir(root.people)
    aliases = person_aliases(root.path)
    names = {g["speaker"]: g.get("speaker_name") for g in groups if g.get("verdict") == "clip"}
    changes: list[dict] = []
    for sid, s in sorted(stories.items()):
        dirty = False
        for n, t in enumerate(s["tellings"]):
            if not t.get("episode"):
                if "replay_of" in t or "teller_was" in t:
                    raise SystemExit(f"clips: story {sid} telling {n + 1}: replay_of or teller_was on a document telling")
                continue
            new = corrected(t, groups)
            if new == t:
                continue
            changes.append({"story": sid, "n": n, "episode": t["episode"], "from_s": t.get("from_s"), "before": t["teller"],
                            "after": new["teller"], "replay_of": new.get("replay_of"), "quote": t.get("quote") or ""})
            s["tellings"][n] = new
            dirty = True
            p = new["teller"]
            if p not in people:  # a speaker the corpus has not met: a person file before the story names them
                made = ensure_person(people, names.get(p) or p.replace("-", " ").title(), role_for(new["kind"]), aliases)
                if made != p:
                    raise SystemExit(f"clips: speaker {p!r} is named {names.get(p)!r}, whose person id is {made!r}: "
                                     "correct the group's speaker or speaker_name in data/clips.json")
                people[p].pop("_new", None)
                if write:
                    save_json(root.people / f"{p}.json", people[p])
        if dirty and write:
            save_json(root.stories / f"{sid}.json", s)
    return changes


def report(root: Root, changes: list[dict]) -> None:
    led = load_ledger(root)
    gs = led["groups"]
    by = {v: sum(g.get("verdict") == v for g in gs) for v in VERDICTS}
    print(f"groups: {len(gs)} ({', '.join(f'{n} {v}' for v, n in by.items())}, {sum(g.get('verdict') is None for g in gs)} unjudged), "
          f"occurrences: {sum(len(g['occurrences']) for g in gs)}, outside origins: {sum(g.get('origin') == 'outside' for g in gs)}")
    replays = [c for c in changes if c["replay_of"]]
    teller = [c for c in changes if c["before"] != c["after"]]
    print(f"tellings changed: {len(changes)}; with replay_of: {len(replays)}; teller changed: {len(teller)}")
    for c in changes:
        r = c["replay_of"]
        where = "" if r is None else (" replay of outside" if r.get("outside") else f" replay of {r['episode']}@{int(r['from_s'])}")
        who = f"{c['before']} -> {c['after']}" if c["before"] != c["after"] else f"{c['after']} (teller kept)"
        print(f"  {c['story']} #{c['n'] + 1} {c['episode']}@{int(c['from_s'] or 0)}: {who}{where}: \"{c['quote'][:120]}\"")


def run(root: Root, asker: Asker, *, size: int = BATCH, write: bool = True, show: bool = False) -> dict:
    episodes = root.load_dir(root.episodes)
    words = load_words(root, episodes)
    stats = judge(root, asker, words, size)
    changes = apply(root, write)
    stats["tellings_changed"] = len(changes)
    if show:
        report(root, changes)
    print("clips: " + ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in stats.items())
          + ("" if write else " (stories not written)"), file=sys.stderr)
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per call")
    ap.add_argument("--batch", type=int, default=BATCH, help=f"groups per call (default {BATCH})")
    ap.add_argument("--fixture", type=Path, help="prepared answers instead of claude -p")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--no-apply", action="store_true", help="detect and judge; write only data/clips.json")
    mode.add_argument("--report", action="store_true", help="detect and judge, then print what apply would change; write no story")
    ap.add_argument("--root", type=Path, default=REPO)
    a = ap.parse_args(argv)
    root = Root(a.root)
    run(root, Asker(root, a.model, a.timeout, a.fixture), size=a.batch, write=not (a.no_apply or a.report), show=a.report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
