"""Shared helpers for the pipeline: the root, the JSON files, slugs, caption text and time codes.

Every stage takes `--root` (default: this repo) so the same code runs on the real data and on a
copy of `tests/fixtures/`. Paths below are relative to that root.
"""
from __future__ import annotations

import bisect
import json
import re
import unicodedata
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

STORY_KINDS = ("sighting", "encounter", "crash-retrieval", "reverse-engineering", "program", "document",
               "testimony", "theory", "cosmology", "place-lore")
TELLING_KINDS = ("firsthand", "official", "journalist", "secondhand", "researcher", "host")
RELATIONS = ("same-event", "variant", "corroborates", "contradicts")

TIMECODE = re.compile(r"^\[(\d+):(\d\d):(\d\d)\] (.*)$")
WS = re.compile(r"\s+")


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


def slugify(s: str, limit: int = 60) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if not s:
        raise SystemExit(f"cannot make a slug from {s!r}")
    return s[:limit].rstrip("-")


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


def person_id(name: str) -> str:
    return slugify(person_name(name).casefold(), 40)


def story_id(title: str, years: dict | None) -> str:
    slug = slugify(title)
    y = years.get("from") if years else None
    if y is not None and str(y) not in slug:
        slug = f"{slug}-{y}"
    return slug


def norm_ws(s: str) -> str:
    return WS.sub(" ", s).strip()


class Captions:
    """The caption text of one episode: cues with seconds, and the plain text they join to.

    The plain text is the cues' words joined by single spaces, time codes stripped, whitespace
    collapsed. A quote is verbatim when it is a substring of that text (case and punctuation exact).
    """

    def __init__(self, f: Path):
        self.path = f
        self.seconds: list[float] = []
        self.texts: list[str] = []
        self.offsets: list[int] = []
        pos = 0
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            m = TIMECODE.match(line)
            if not m:
                raise SystemExit(f"{f}:{n}: expected '[h:mm:ss] words', got {line[:60]!r}")
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
            text = norm_ws(m.group(4))
            if not text:
                continue
            self.seconds.append(float(t))
            self.texts.append(text)
            self.offsets.append(pos)
            pos += len(text) + 1
        if not self.texts:
            raise SystemExit(f"{f}: no cues")
        self.plain = " ".join(self.texts)

    def lines(self) -> list[str]:
        return [f"[{fmt_s(s)}] {t}" for s, t in zip(self.seconds, self.texts)]

    def locate(self, quote: str) -> tuple[float, float] | None:
        """(from_s, to_s) of a verbatim quote, or None. to_s is the start of the cue after the last one spanned."""
        q = norm_ws(quote)
        if not q:
            return None
        i = self.plain.find(q)
        if i < 0:
            return None
        a = bisect.bisect_right(self.offsets, i) - 1
        b = bisect.bisect_right(self.offsets, i + len(q) - 1) - 1
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
