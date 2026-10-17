"""The fallback for captions: a transcript from Gemini, stored as the episode's caption text.

    ../creator-watch/.venv/bin/python -m pipeline.gemini_captions <video id or URL> [--root DIR] [--force]

Run from the NHI-timeline root with creator-watch's interpreter: this stage borrows creator-watch's
Gemini transcriber (Gemini reads the video by its YouTube URL, a route Google sanctions) and its
Data API client, so NHI-timeline itself keeps no dependency beyond the standard library. It is for
the episodes `captions.py` cannot serve: YouTube rate-limits caption downloads (HTTP 429), and some
videos have no caption track at all.

What it reads from creator-watch (`CREATOR_WATCH` below): the package `creator_watch`, the keys file
its `config.toml` names (`~/.config/creator-watch/keys.env`, mode 600, `GEMINI_API_KEY` and
`YOUTUBE_API_KEY`), the `[gemini]` settings of that config (model, words per minute, continuations,
rescale factor, timeouts, media resolution) and its prompt `prompts/transcribe.md`.

What it writes: `sources/captions/<id>.<lang>.txt`, one line per paragraph, "[h:mm:ss] text", the
shape `captions.py` writes, so `common.Captions`, extract and the verbatim quote check read it
unchanged; and `data/episodes/<id>.json` with the fields `captions.py` writes plus
`"captions_source": "gemini"` and `"timestamps_approximate"` (true when Gemini's time stamps overshot
the duration and were rescaled to fit, so a time-coded link may land some seconds off). An existing
episode file keeps its hand-edited fields (host, guests); the caption fields are set. There is no .vtt.

The ledger: `sources/gemini-ledger.json`, `{ "<UTC day>": seconds }`, counts the seconds of video
sent to Gemini per UTC day (every request sends the whole video, so a continuation is charged the
full duration again; a request that fails as an outage is refunded). The cap is 2 hours a day
(`--cap-hours`): Google's free tier of 8 hours a day is shared with creator-watch's hourly runs,
which keep their own ledger, and this stage must not starve them.

Fails loud when creator-watch, its config or its keys file is missing, when the video is absent or
live, when a caption text exists already (unless `--force`) and when Gemini cannot serve the video
(`GeminiFailure`, including a transcript rejected twice). When Gemini is blocked (rate limit, quota,
the cap, a timeout, the network) it says so and exits 2 without writing anything: try again later.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from .captions import host_and_guests, video_id
from .common import REPO, Root, dump_json, load_json, norm_ws, rel

CREATOR_WATCH = REPO.parent / "creator-watch"
CAP_HOURS = 2.0


class FileLedger:
    """Seconds of video sent to Gemini per UTC day, in one small JSON file."""

    def __init__(self, path: Path, cap_seconds: float):
        self.path, self.cap = path, cap_seconds

    @staticmethod
    def _day() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _load(self) -> dict:
        if not self.path.exists():
            return {}
        d = load_json(self.path)
        if not isinstance(d, dict) or not all(isinstance(v, (int, float)) for v in d.values()):
            raise SystemExit(f"{self.path}: expected {{\"<UTC day>\": seconds}}")
        return d

    def remaining(self) -> float:
        return self.cap - self._load().get(self._day(), 0.0)

    def add(self, seconds: float) -> None:
        d = self._load()
        day = self._day()
        d[day] = max(0.0, d.get(day, 0.0) + seconds)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def import_creator_watch():
    if not (CREATOR_WATCH / "creator_watch" / "gemini.py").is_file():
        raise SystemExit(f"gemini_captions: creator-watch not found at {CREATOR_WATCH}")
    sys.path.insert(0, str(CREATOR_WATCH))
    try:
        import creator_watch.gemini as gemini
        from creator_watch.config import load_config
        from creator_watch.keys import load_keys
        from creator_watch.youtube_api import YouTubeApi
    except ImportError as e:
        raise SystemExit(f"gemini_captions: cannot import creator-watch ({e}); run with "
                         f"{CREATOR_WATCH}/.venv/bin/python -m pipeline.gemini_captions")
    return gemini, load_config, load_keys, YouTubeApi


def caption_lines(paragraphs: list[tuple[float, str]]) -> list[str]:
    lines = []
    for start, text in paragraphs:
        text = norm_ws(text)
        if not text:
            continue
        s = int(start)
        lines.append(f"[{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}] {text}")
    if not lines:
        raise SystemExit("gemini_captions: the transcript holds no paragraphs")
    return lines


def run(root: Root, vid: str, *, force: bool = False, cap_hours: float = CAP_HOURS) -> tuple[Path, Path, dict]:
    gemini, load_config, load_keys, YouTubeApi = import_creator_watch()
    try:
        cfg = load_config(CREATOR_WATCH / "config.toml")
        keys = load_keys(cfg.keys_file)
    except Exception as e:  # ConfigError, KeysError: messages never hold a key value
        raise SystemExit(f"gemini_captions: {type(e).__name__}: {e}")

    try:
        metas = YouTubeApi(keys.youtube, keys.redact).videos([vid])
    except Exception as e:
        raise SystemExit(f"gemini_captions: Data API: {keys.redact(str(e))}")
    meta = metas.get(vid)
    if meta is None:
        raise SystemExit(f"gemini_captions: {vid} is absent from the Data API (private, deleted or a wrong id)")
    if isinstance(meta, Exception):
        raise SystemExit(f"gemini_captions: {vid}: {meta}")
    if meta.is_live_placeholder:
        raise SystemExit(f"gemini_captions: {vid} is {meta.live}, not a finished video")
    if meta.duration_seconds <= 0:
        raise SystemExit(f"gemini_captions: {vid} has no duration")

    lang = "en" if meta.language == "unknown" else meta.language.split("-")[0].lower()
    txt = root.captions / f"{vid}.{lang}.txt"
    if txt.exists() and not force:
        raise SystemExit(f"gemini_captions: {rel(txt, root.path)} exists; --force to replace it")

    ledger = FileLedger(root.path / "sources" / "gemini-ledger.json", cap_hours * 3600)
    if ledger.remaining() < meta.duration_seconds:
        print(f"gemini_captions: blocked: {vid} is {meta.duration_seconds} s, today's Gemini allowance has "
              f"{max(0, ledger.remaining()):.0f} s of {cap_hours:g} h left; nothing written", file=sys.stderr)
        raise SystemExit(2)
    tr = gemini.GeminiTranscriber(
        cfg.gemini_model, keys.gemini, cfg.prompts_dir / "transcribe.md", ledger,
        min_wpm=cfg.gemini_min_wpm, max_continuations=cfg.gemini_max_continuations,
        min_rescale_factor=cfg.gemini_min_rescale_factor, redact=keys.redact,
        timeout_base_seconds=cfg.gemini_timeout_base, timeout_per_video_minute=cfg.gemini_timeout_per_minute,
        timeout_max_seconds=cfg.gemini_timeout_max, media_resolution=cfg.gemini_media_resolution)
    try:
        result = tr.transcribe(vid, meta.duration_seconds, meta.language)
    except gemini.GeminiBlocked as e:
        print(f"gemini_captions: blocked ({type(e).__name__}): {keys.redact(str(e))}; nothing written, try later",
              file=sys.stderr)
        raise SystemExit(2)
    except gemini.GeminiFailure as e:
        raise SystemExit(f"gemini_captions: Gemini cannot serve {vid} ({type(e).__name__}): {keys.redact(str(e))}")

    lines = caption_lines(result.paragraphs)
    txt.parent.mkdir(parents=True, exist_ok=True)
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ep = root.episodes / f"{vid}.json"
    host, guests = host_and_guests(meta.channel_title, meta.title)
    doc = load_json(ep) if ep.exists() else {
        "id": vid, "show": meta.channel_title, "title": meta.title, "host": host, "guests": guests,
        "published": meta.published.astimezone(timezone.utc).date().isoformat(),
        "url": f"https://www.youtube.com/watch?v={vid}", "duration_s": meta.duration_seconds,
    }
    doc.update({
        "captions": rel(txt, root.path), "language": lang, "auto_captions": False,
        "captions_source": "gemini", "timestamps_approximate": bool(result.timestamps_approximate),
    })
    ep.parent.mkdir(parents=True, exist_ok=True)
    ep.write_text(dump_json(doc), encoding="utf-8")
    words = sum(len(t.split()) for _, t in result.paragraphs)
    return txt, ep, {"paragraphs": len(lines), "words": words, "last": lines[-1].split("]")[0] + "]",
                     "duration_s": meta.duration_seconds, "approximate": result.timestamps_approximate,
                     "model": result.model}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--force", action="store_true", help="replace an existing caption text")
    ap.add_argument("--cap-hours", type=float, default=CAP_HOURS, help="seconds of video sent to Gemini per UTC day, in hours")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    root = Root(a.root)
    txt, ep, s = run(root, video_id(a.video), force=a.force, cap_hours=a.cap_hours)
    print(f"{ep.stem}: {s['paragraphs']} paragraphs, {s['words']} words, last at {s['last']} of a "
          f"{s['duration_s']} s video ({s['model']}, time stamps {'rescaled' if s['approximate'] else 'as given'}) "
          f"-> {rel(txt, root.path)}; episode {rel(ep, root.path)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
