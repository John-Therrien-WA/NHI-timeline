"""Captions in, text with time codes out.

    uv run python -m pipeline.captions <youtube url or video id> [--lang en]

Fetches the video's own captions with yt-dlp (no audio download, no transcription), keeps the
.vtt under sources/captions/<id>.<lang>.vtt, and writes sources/captions/<id>.<lang>.txt: one line
per caption cue, "[h:mm:ss] words", with the consecutive duplicates that auto-captions produce
removed. HTML entities are unescaped (the .vtt writes `&gt;&gt;` and `&amp;`); the `>>` with which
YouTube marks a change of speaker is kept as the line's prefix after the time code. Writes data/episodes/<id>.json from the video's metadata when it does not exist yet.
Fails loud when the video has no captions in that language.
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


def video_id(s: str) -> str:
    m = VIDEO_ID.search(s.strip())
    if not m:
        raise SystemExit(f"captions: no video id in {s!r}")
    return m.group(1)


def fetch(vid: str, lang: str) -> tuple[Path, dict]:
    CAPTIONS.mkdir(parents=True, exist_ok=True)
    out = CAPTIONS / f"{vid}.%(ext)s"
    cmd = ["yt-dlp", "--skip-download", "--no-playlist", "--write-auto-sub", "--write-sub", "--sub-lang", lang,
           "--sub-format", "vtt", "--print-json", "-o", str(out), f"https://www.youtube.com/watch?v={vid}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"captions: yt-dlp failed for {vid}:\n{r.stderr.strip()}")
    meta = json.loads(r.stdout.splitlines()[-1])
    vtt = CAPTIONS / f"{vid}.{lang}.vtt"
    if not vtt.exists():
        raise SystemExit(f"captions: {vid} has no {lang} captions (manual or automatic); nothing written")
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
    doc = {
        "id": vid,
        "show": meta.get("channel") or meta.get("uploader"),
        "title": meta.get("title"),
        "host": None,
        "guests": [],
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
    ap.add_argument("video")
    ap.add_argument("--lang", default="en")
    a = ap.parse_args(argv)
    vid = video_id(a.video)
    vtt, meta = fetch(vid, a.lang)
    txt = to_text(vtt)
    ep = episode(vid, meta, vtt, a.lang)
    n = sum(1 for _ in txt.open(encoding="utf-8"))
    print(f"{vid}: {n} cues -> {txt.relative_to(ROOT)}; episode {ep.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
