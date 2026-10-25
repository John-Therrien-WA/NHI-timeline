"""Shared helpers for the pipeline: the root, the JSON files, slugs, caption text and time codes.

Every stage takes `--root` (default: this repo) so the same code runs on the real data and on a
copy of `tests/fixtures/`. Paths below are relative to that root.
"""
from __future__ import annotations

import bisect
import html
import json
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

STORY_KINDS = ("sighting", "encounter", "crash-retrieval", "reverse-engineering", "program", "document",
               "testimony", "theory", "cosmology", "place-lore")
TELLING_KINDS = ("firsthand", "official", "journalist", "secondhand", "researcher", "host")
RELATIONS = ("same-event", "variant", "corroborates", "contradicts")
DISCUSSION_KINDS = ("debunk", "rebunk", "note", "source")
DISCUSSION_ROLES = ("witness", "participant", "official", "researcher", "journalist", "host", "viewer")
DISCUSSION_KEYS = ("kind", "by", "role", "date", "source", "episode", "time", "text")
NOTE_STATUSES = ("open", "folded", "dropped")
NOTE_KEYS = ("by", "date", "text", "status")
DATE = re.compile(r"\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?")
HTTP = re.compile(r"https?://\S+")

TIMECODE = re.compile(r"^\[(\d+:\d\d:\d\d)\] (.*)$")
HMS = re.compile(r"(\d+):([0-5]\d):([0-5]\d)")
WS = re.compile(r"\s+")
SPEAKER = re.compile(r">>+")
BRACKET_TAG = re.compile(r"\[[^\[\]]{0,40}\]")
SPACE_BEFORE_PUNCT = re.compile(r" ([,.;:!?])")


def text_field(v) -> bool:
    """A non-empty string."""
    return isinstance(v, str) and bool(v.strip())


class Root:
    """The directories of one data root."""

    def __init__(self, root: Path | str = REPO):
        self.path = Path(root).resolve()
        self.data = self.path / "data"
        self.stories = self.data / "stories"
        self.people = self.data / "people"
        self.episodes = self.data / "episodes"
        self.documents = self.data / "documents"
        self.candidates = self.data / "candidates"
        self.notes = self.data / "notes"
        self.captions = self.path / "sources" / "captions"
        self.site = self.path / "site"

    def eras(self) -> list[dict]:
        return load_json(self.data / "eras.json")

    def places(self) -> list[dict]:
        return load_json(self.data / "places.json")

    def load_dir(self, d: Path) -> dict[str, dict]:
        """Every JSON object in a directory keyed by id; the file name must equal the id."""
        out: dict[str, dict] = {}
        if not d.exists():
            return out
        for f in sorted(d.glob("*.json")):
            obj = load_json(f)
            if not isinstance(obj, dict) or obj.get("id") != f.stem:
                raise SystemExit(f"{rel(f, self.path)}: the file name must equal the object's id (got {obj.get('id')!r})")
            out[f.stem] = obj
        return out

    def story_aliases(self, stories: dict[str, dict] | None = None) -> dict[str, str]:
        """{alias: story id} from every story's `aliases` (the stories loaded here when not given).
        Fails when an alias is also a story id or is claimed by two stories."""
        if stories is None:
            stories = self.load_dir(self.stories)
        owner: dict[str, str] = {}
        for sid, s in sorted(stories.items()):
            for a in s.get("aliases", []):
                if a in stories:
                    raise SystemExit(f"story {sid}: alias {a!r} is also a story id")
                if a in owner:
                    raise SystemExit(f"story {sid}: alias {a!r} is also an alias of {owner[a]}")
                owner[a] = sid
        return owner

    def load_notes(self) -> dict[str, list]:
        """The viewer-note inboxes, data/notes/<story id>.json, keyed by the file name (a story id or an
        alias). Fails when a file is not a list of objects or an entry's `status` is not one of
        NOTE_STATUSES; check.py checks the other fields and that the name resolves."""
        out: dict[str, list] = {}
        if not self.notes.exists():
            return out
        for f in sorted(self.notes.glob("*.json")):
            obj = load_json(f)
            if not isinstance(obj, list):
                raise SystemExit(f"{rel(f, self.path)}: a notes file must be a list of entries")
            for i, e in enumerate(obj):
                if not isinstance(e, dict):
                    raise SystemExit(f"{rel(f, self.path)} entry {i + 1}: must be an object")
                if e.get("status") not in NOTE_STATUSES:
                    raise SystemExit(f"{rel(f, self.path)} entry {i + 1}: status {e.get('status')!r} is not one of {', '.join(NOTE_STATUSES)}")
            out[f.stem] = obj
        return out

    def caption_text(self, episode: dict) -> Path:
        """The plain-text captions of an episode (`captions.py` wrote them next to the .vtt)."""
        lang = episode.get("language") or "en"
        f = self.captions / f"{episode['id']}.{lang}.txt"
        if not f.exists():
            raise SystemExit(f"no caption text for {episode['id']}: {rel(f, self.path)} (run pipeline.captions first)")
        return f


def rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def load_json(f: Path):
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"missing file: {f}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"{f}: not valid JSON ({e})")


def dump_json(obj) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def save_json(f: Path, obj) -> bool:
    """Write pretty JSON; return True when the file changed."""
    text = dump_json(obj)
    if f.exists() and f.read_text(encoding="utf-8") == text:
        return False
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text, encoding="utf-8")
    return True


PICTURE_DATE_RULE = ("A picture date is YYYY, YYYY-MM or YYYY-MM-DD, or absent (the key left out or null); "
                     "a range, a decade or a century goes into the caption in words.")
ARTIFACT_FILE_BYTES = 16_000_000  # the most a published claude.ai artifact allows one file
ASSET_URL_PREFIXES = ("https://", "/")  # an asset url in publish/assets.json starts with one of these (the page holds a copy)
ASSET_URL_OFFSITE = "//"  # and never with this: a "/" url that starts so is an address on another site (the page holds a copy)
SLUG_LIMIT = 60  # the longest slug `slugify` makes by default, so the longest document or story id
SLUG = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def slugify(s: str, limit: int = SLUG_LIMIT) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if not s:
        raise SystemExit(f"cannot make a slug from {s!r}")
    return s[:limit].rstrip("-")


def is_document_id(x) -> bool:
    """A document id is a slug `slugify` could make of a title: lowercase letters and digits in runs joined by
    single hyphens, at most SLUG_LIMIT characters (so `slugify(x) == x`). The fold, the check and a source
    manifest hold an id to this one rule."""
    return isinstance(x, str) and len(x) <= SLUG_LIMIT and SLUG.fullmatch(x) is not None


ROLE = re.compile(r"\s*\([^()]*\)\s*$")


def person_name(s: str) -> str:
    """A person's name as the data keeps it: whitespace collapsed, a trailing parenthetical role such as
    '(host)' or '(guest)' stripped. The id is the slug of the case-folded name, so 'Jesse Michels (host)'
    and 'jesse michels' are one person."""
    if not isinstance(s, str):
        raise SystemExit(f"a person's name must be a string, got {s!r}")
    name = ROLE.sub("", norm_ws(s)).strip()
    if not name:
        raise SystemExit(f"cannot make a person's name from {s!r}")
    return name


def name_key(name: str) -> str:
    """The id a name would get without aliases: the slug of the case-folded name."""
    return slugify(person_name(name).casefold(), 40)


def raw_person_aliases(root: Path) -> dict[str, str]:
    """data/person-aliases.json of a root as written, {alias text: person id}; {} when the file is absent.
    Fails on a file that is not an object; `person_aliases` checks the entries."""
    f = Path(root) / "data" / "person-aliases.json"
    if not f.exists():
        return {}
    raw = load_json(f)
    if not isinstance(raw, dict):
        raise SystemExit(f"{f}: must be an object of alias text to person id")
    return raw


def person_aliases(root: Path) -> dict[str, str]:
    """data/person-aliases.json of a root as {name key: person id}; {} when the file is absent.

    The file maps an alias as written ("Garry Nolan") to a person id ("gary-nolan"); the lookup is
    on the name key, so case, spacing, punctuation and a trailing role do not matter. A stage reads
    it once per run and passes the dict to `person_id`."""
    f = Path(root) / "data" / "person-aliases.json"
    raw = raw_person_aliases(root)
    out: dict[str, str] = {}
    for text, pid in raw.items():
        if not isinstance(pid, str) or slugify(pid, 40) != pid:
            raise SystemExit(f"{f}: {text!r} points at {pid!r}, which is not a person id (a lowercase slug)")
        key = name_key(text)
        if key in out and out[key] != pid:
            raise SystemExit(f"{f}: {text!r} is the same name as another alias, which points at {out[key]!r}, not {pid!r}")
        out[key] = pid
    return out


def person_id(name: str, aliases: dict[str, str]) -> str:
    """The person id of a name: the aliases (`person_aliases` of the run's root) when they name the
    spelling, else the name key."""
    key = name_key(name)
    return aliases.get(key, key)


def document_aliases(documents: dict[str, dict]) -> dict[str, str]:
    """{alias: document id} from every document's `aliases` (the ids `pipeline.documents --fold` folded into
    it). Fails when an alias is also a document id or is claimed by two documents."""
    out: dict[str, str] = {}
    for did, d in sorted(documents.items()):
        for a in d.get("aliases") or []:
            if a in documents:
                raise SystemExit(f"document {did}: alias {a!r} is also a document file (run pipeline.documents --fold)")
            if out.get(a, did) != did:
                raise SystemExit(f"document {did}: alias {a!r} is also an alias of {out[a]}")
            out[a] = did
    return out


def story_id(title: str, years: dict | None) -> str:
    slug = slugify(title)
    y = years.get("from") if years else None
    if y is not None and str(y) not in slug:
        slug = f"{slug}-{y}"
    return slug


def norm_ws(s: str) -> str:
    return WS.sub(" ", s).strip()


def norm_quote(s: str) -> str:
    """Caption text or a quote reduced to its words for the verbatim comparison: entities unescaped,
    the `>>` speaker markers and bracketed tags such as `[music]` or `[ __ ]` removed, whitespace
    collapsed (and the space a removed tag leaves before punctuation dropped). Case and punctuation
    stay exact."""
    s = SPEAKER.sub(" ", html.unescape(s).replace("\xa0", " "))
    s = BRACKET_TAG.sub(" ", s)
    return SPACE_BEFORE_PUNCT.sub(r"\1", norm_ws(s))


def seconds(hms: str) -> int:
    """`h:mm:ss` to seconds; fails on anything else."""
    m = HMS.fullmatch(hms) if isinstance(hms, str) else None
    if not m:
        raise SystemExit(f"time code {hms!r} is not h:mm:ss")
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))


class Captions:
    """The caption text of one episode: cues with seconds, and the normalised text they join to.

    The normalised text is each cue reduced by `norm_quote` (time codes stripped, speaker markers
    and bracketed tags removed, whitespace collapsed), the cues joined by single spaces. A quote is
    verbatim when, reduced the same way, it is a substring of that text, case and punctuation
    exact. Its time codes come from the original cues the match spans.
    """

    def __init__(self, f: Path):
        self.path = f
        self.seconds: list[float] = []
        self.texts: list[str] = []
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            m = TIMECODE.match(line)
            if not m:
                raise SystemExit(f"{f}:{n}: expected '[h:mm:ss] words', got {line[:60]!r}")
            t = seconds(m.group(1))
            text = norm_ws(m.group(2))
            if not text:
                continue
            self.seconds.append(float(t))
            self.texts.append(text)
        if not self.texts:
            raise SystemExit(f"{f}: no cues")
        # The normalised text, cue by cue; a cue that is only a tag ("[music]") adds nothing.
        self._norm_offsets: list[int] = []
        self._norm_cue: list[int] = []
        parts, pos = [], 0
        for i, text in enumerate(self.texts):
            n = norm_quote(text)
            if not n:
                continue
            parts.append(n)
            self._norm_offsets.append(pos)
            self._norm_cue.append(i)
            pos += len(n) + 1
        self.norm = " ".join(parts)

    def lines(self) -> list[str]:
        return [f"[{fmt_s(s)}] {t}" for s, t in zip(self.seconds, self.texts)]

    def locate(self, quote: str, near: float | None = None) -> tuple[float, float] | None:
        """(from_s, to_s) of a verbatim quote, or None. to_s is the start of the cue after the last one spanned.

        When the quote occurs more than once (a trailer at the top of the episode repeats a line of
        the body), the occurrence whose first cue is nearest `near` (the time code the model gave)
        is taken; without `near`, the first."""
        q = norm_quote(quote)
        if not q:
            return None
        spans, i = [], self.norm.find(q)
        while i >= 0:
            a = self._norm_cue[bisect.bisect_right(self._norm_offsets, i) - 1]
            b = self._norm_cue[bisect.bisect_right(self._norm_offsets, i + len(q) - 1) - 1]
            spans.append((a, b))
            i = self.norm.find(q, i + 1)
        if not spans:
            return None
        a, b = spans[0] if near is None else min(spans, key=lambda ab: abs(self.seconds[ab[0]] - near))
        to_s = self.seconds[b + 1] if b + 1 < len(self.seconds) else self.seconds[b]
        return self.seconds[a], to_s

    def contains(self, quote: str) -> bool:
        return self.locate(quote) is not None


def fmt_s(s: float) -> str:
    s = int(s)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def parse_timecode(v) -> float | None:
    """Seconds from a number or an 'h:mm:ss' / 'mm:ss' string; None when it is neither."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        v = v.strip().strip("[]")
        if re.fullmatch(r"\d+(\.\d+)?", v):
            return float(v)
        parts = v.split(":")
        if 2 <= len(parts) <= 3 and all(re.fullmatch(r"\d+", p) for p in parts):
            parts = [int(p) for p in parts]
            if len(parts) == 2:
                return float(parts[0] * 60 + parts[1])
            return float(parts[0] * 3600 + parts[1] * 60 + parts[2])
    return None


YEAR = re.compile(r"\b(1[89]\d\d|20\d\d)(s)?\b")


def parse_years(v) -> dict | None:
    """{'from', 'to'} from free text such as '1958', '1947-1952', 'the early 1970s'; None when no year is in it."""
    if isinstance(v, dict):
        f, t = v.get("from"), v.get("to")
        if f is None and t is None:
            return None
        if not all(x is None or isinstance(x, int) for x in (f, t)):
            raise SystemExit(f"years must be integers or null, got {v!r}")
        return {"from": f if f is not None else t, "to": t if t is not None else f}
    if isinstance(v, int):
        return {"from": v, "to": v}
    if not isinstance(v, str):
        return None
    low = v.lower()
    years: list[int] = []
    for m in YEAR.finditer(v):
        y = int(m.group(1))
        if m.group(2):  # a decade
            a, b = y, y + 9
            if "early" in low:
                b = y + 3
            elif "mid" in low:
                a, b = y + 3, y + 6
            elif "late" in low:
                a = y + 7
            years += [a, b]
        else:
            years.append(y)
    if not years:
        return None
    return {"from": min(years), "to": max(years)}


def era_for(years: dict | None, eras: list[dict]) -> str | None:
    if not years or years.get("from") is None:
        return None
    for e in eras:
        if e["from"] <= years["from"] <= e["to"]:
            return e["id"]
    return None
