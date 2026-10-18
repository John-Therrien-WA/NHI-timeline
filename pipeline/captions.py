"""Captions in, text with time codes out.

    uv run python -m pipeline.captions <youtube url or video id> [--lang en]
    uv run python -m pipeline.captions --refill [--root DIR]

Fetches the video's own captions with yt-dlp (no audio download, no transcription): the original
automatic track `<lang>-orig` first (plain `<lang>` is YouTube's same-language translation of it, the
one track YouTube throttles with HTTP 429), then plain `<lang>` only when the video has no original
track in that language; keeps the
.vtt under sources/captions/<id>.<lang>.vtt, and writes sources/captions/<id>.<lang>.txt: one line
per caption cue, "[h:mm:ss] words", with the consecutive duplicates that auto-captions produce
removed. HTML entities are unescaped (the .vtt writes `&gt;&gt;` and `&amp;`); the `>>` with which
YouTube marks a change of speaker is kept as the line's prefix after the time code. Writes data/episodes/<id>.json from the video's metadata when it does not exist yet, with `host`
and `guests` filled by `host_and_guests`: the host of the American Alchemy channel (published as
"Jesse Michels") is `jesse-michels`, and the guests are names taken from the title by a few
conservative patterns (`ft.` names, `(Name Interview)`, a trailing `-Name`, `with Name`, `Name:` at
the start); when none matches, `guests` stays empty and the extraction prompt's title line serves.
Fails loud when the video has no captions in that language.

--refill fills `host` and `guests` the same way in every existing episode file whose `host` is
null, rewriting only those two fields and touching no captions.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CAPTIONS = ROOT / "sources" / "captions"
EPISODES = ROOT / "data" / "episodes"
VIDEO_ID = re.compile(r"(?:v=|youtu\.be/|/shorts/|^)([A-Za-z0-9_-]{11})(?:[&?/]|$)")
CUE_TIME = re.compile(r"^(\d\d):(\d\d):(\d\d)\.(\d{3}) --> ")
TAG = re.compile(r"<[^>]+>")
AMERICAN_ALCHEMY = ("american alchemy", "jesse michels")
NAME_WORD = r"[A-Z\u00c0-\u00de][a-z\u00df-\u00ff]+(?:[A-Z][a-z]+)?(?:[-'\u2019][A-Za-z]+)?"
NAME = re.compile(rf"(?:[A-Z]\. )?{NAME_WORD}(?: {NAME_WORD}){{1,2}}")
# Words a title puts after a name ("-Whitley Strieber Tells All"); dropped from the end of a segment.
TRAILING = {"Tells", "All", "Speaks", "Out", "Reveals", "Explains", "Interview", "Exclusive", "Documentary", "Full",
            "Episode", "Part", "Returns"}
# Role and descriptor words that title-case a phrase without naming anyone ("Top Navy Admiral").
NOT_NAMES = {"Admiral", "Advisor", "Agent", "Breaking", "Colonel", "Commander", "Doctor", "Expert", "Former", "General",
             "Historian", "Insider", "Navy", "Officer", "Philosopher", "Physicist", "Pilot", "Presidential", "Professor",
             "Scientist", "Senator", "Skeptic", "Story", "Top", "Whistleblower", "Neuroscientist", "Researcher",
             "Journalist", "Director", "Secret", "Alien", "Aliens", "The"}
FT = re.compile(r"\b(?:ft|feat)\.?\s+([^()\[\]|]+)", re.I)
PAREN = re.compile(r"\(([^()]+?)\s+(?:Interview|Documentary)\)")
DASH = re.compile(r"(?:^|[\s\"\u201d\u2019'!?])-\s?([^-()]+)$")
WITH = re.compile(r"\bwith\s+(.+)$")
COLON = re.compile(r"^([^:]{3,40}):")
FALLBACK = ("the fallback is a Gemini transcript: ../creator-watch/.venv/bin/python -m pipeline.gemini_captions {vid}")


def video_id(s: str) -> str:
    m = VIDEO_ID.search(s.strip())
    if not m:
        raise SystemExit(f"captions: no video id in {s!r}")
    return m.group(1)


def _name_at_end(segment: str) -> str | None:
    """The name a segment ends on ('Stanford Scientist Garry Nolan' -> 'Garry Nolan'), or None: the last
    two capitalised words (three with a leading initial) after trailing words such as 'Tells All' are dropped."""
    words = segment.strip().strip("\"\u201c\u201d!?.,").split()
    while words and words[-1] in TRAILING:
        words.pop()
    if len(words) < 2:
        return None
    take = 3 if len(words) >= 3 and re.fullmatch(r"[A-Z]\.", words[-3]) else 2
    return _is_name(" ".join(words[-take:]))


def _is_name(cand: str) -> str | None:
    cand = cand.strip()
    return cand if NAME.fullmatch(cand) and not NOT_NAMES & set(cand.split()) else None


def _names(segment: str) -> list[str]:
    """'Mike Masters & David Grusch' -> both names; every part must end on a name or the segment gives none."""
    parts = [x for x in re.split(r"\s*(?:&|,|\band\b)\s*", segment.strip()) if x.strip()]
    names = [_name_at_end(x) for x in parts]
    return names if names and all(names) else []


def host_and_guests(show: str | None, title: str | None) -> tuple[str | None, list[str]]:
    """The host id and guest names an episode's channel and title give; (None, []) when they give nothing."""
    host = "jesse-michels" if (show or "").strip().casefold() in AMERICAN_ALCHEMY else None
    title = (title or "").strip()
    whole = lambda seg: [n] if (n := _is_name(seg)) else []  # "Eric Davis:", not "Top Navy Admiral:"
    for pattern, take in ((FT, _names), (PAREN, _names), (DASH, _names), (WITH, _names), (COLON, whole)):
        m = pattern.search(title)
        if m and (guests := take(m.group(1))):
            return host, list(dict.fromkeys(guests))
    return host, []


def refill(episodes: Path) -> list[Path]:
    """Fill host and guests in every episode file whose host is null; return the files changed."""
    changed = []
    for f in sorted(episodes.glob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        if doc.get("host") is not None:
            continue
        host, guests = host_and_guests(doc.get("show"), doc.get("title"))
        if host == doc.get("host") and guests == (doc.get("guests") or []):
            continue
        doc["host"], doc["guests"] = host, guests
        f.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        changed.append(f)
    return changed


def fetch(vid: str, lang: str) -> tuple[Path, dict]:
    CAPTIONS.mkdir(parents=True, exist_ok=True)
    out = CAPTIONS / f"{vid}.%(ext)s"
    # The original-language automatic track is `<lang>-orig`; plain `<lang>` is YouTube's translation of it
    # into the same language, and that track is what YouTube throttles with HTTP 429 (yt-dlp issue 13831).
    # The original track is asked for first and kept as <vid>.<lang>.vtt; only when the video has none
    # (its spoken language is another) is the plain track asked for, which also fetches a manual track.
    vtt = CAPTIONS / f"{vid}.{lang}.vtt"
    orig = CAPTIONS / f"{vid}.{lang}-orig.vtt"
    meta = None
    for sub_lang in (f"{lang}-orig", lang):
        cmd = ["yt-dlp", "--skip-download", "--no-playlist", "--write-sub", "--write-auto-sub", "--sub-lang", sub_lang,
               "--sub-format", "vtt", "--print-json", "-o", str(out), f"https://www.youtube.com/watch?v={vid}"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            hint = f"\n{FALLBACK.format(vid=vid)}" if "429" in r.stderr else ""
            raise SystemExit(f"captions: yt-dlp failed for {vid}:\n{r.stderr.strip()}{hint}")
        meta = json.loads(r.stdout.splitlines()[-1])
        if orig.exists():
            orig.rename(vtt)
        if vtt.exists():
            break
    if not vtt.exists():
        raise SystemExit(f"captions: {vid} has no {lang} captions (manual or automatic); nothing written\n"
                         f"{FALLBACK.format(vid=vid)}")
    return vtt, meta


def to_text(vtt: Path) -> Path:
    lines, last, t = [], "", None
    for raw in vtt.read_text(encoding="utf-8").splitlines():
        m = CUE_TIME.match(raw)
        if m:
            h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
            t = f"{h}:{mi:02d}:{s:02d}"
            continue
        if not raw.strip() or raw.startswith(("WEBVTT", "Kind:", "Language:", "NOTE")) or t is None:
            continue
        text = html.unescape(TAG.sub("", raw)).replace("\xa0", " ").strip()
        if not text or text == last:
            continue
        lines.append(f"[{t}] {text}")
        last = text
    if not lines:
        raise SystemExit(f"captions: {vtt} holds no cues")
    txt = vtt.with_suffix(".txt")
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return txt


def episode(vid: str, meta: dict, vtt: Path, lang: str) -> Path:
    EPISODES.mkdir(parents=True, exist_ok=True)
    f = EPISODES / f"{vid}.json"
    if f.exists():
        return f
    date = meta.get("upload_date")
    show = meta.get("channel") or meta.get("uploader")
    host, guests = host_and_guests(show, meta.get("title"))
    doc = {
        "id": vid,
        "show": show,
        "title": meta.get("title"),
        "host": host,
        "guests": guests,
        "published": f"{date[:4]}-{date[4:6]}-{date[6:]}" if date else None,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "duration_s": meta.get("duration"),
        "captions": str(vtt.relative_to(ROOT)),
        "language": lang,
        "auto_captions": not bool((meta.get("subtitles") or {}).get(lang)),
    }
    f.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return f


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video", nargs="?")
    ap.add_argument("--lang", default="en")
    ap.add_argument("--refill", action="store_true", help="fill host and guests of the episode files whose host is null")
    ap.add_argument("--root", type=Path, default=ROOT, help="the data root for --refill")
    a = ap.parse_args(argv)
    if a.refill:
        if a.video:
            raise SystemExit("captions: --refill takes no video")
        changed = refill(a.root / "data" / "episodes")
        for f in changed:
            d = json.loads(f.read_text(encoding="utf-8"))
            print(f"{f.stem}: host {d['host']}, guests {d['guests']}")
        print(f"captions: --refill changed {len(changed)} episode file(s)")
        return 0
    if not a.video:
        raise SystemExit("captions: give a video, or --refill")
    vid = video_id(a.video)
    vtt, meta = fetch(vid, a.lang)
    txt = to_text(vtt)
    ep = episode(vid, meta, vtt, a.lang)
    n = sum(1 for _ in txt.open(encoding="utf-8"))
    print(f"{vid}: {n} cues -> {txt.relative_to(ROOT)}; episode {ep.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
