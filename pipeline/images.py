"""Photographs for stories and tellers: the sidecars, their validation, and the ingest of a manifest.

    uv run python -m pipeline.images <manifest.json> [--root DIR] [--keep-going]

An image is a file `site/images/<owner>/<n>.jpg` (or `.png` when the source is a PNG with
transparency) and a sidecar `data/images/<owner>/<n>.json`, the owner a story id, an alias of one,
or a person id, `n` = 1, 2, ... A story's images are objects and places (`object`, `place-then`,
`place-now`), free-licensed or credited fair use, or a `person` picture: a free-licensed photograph
showing someone the story is about, named in `person` (their person id when they are in data/people,
else their name), allowed only when two or more independent tellers tell the story or the person shown
tells it themselves (read from data/scores.json), so a face never stands beside one other person's
claim about them. A person's own image is a `headshot`, free-licensed only, and the page shows it only
beside that person's own tellings, never as a story's picture.
Free images are at most 1200 px on the long side, fair-use ones at most 480 px.

The manifest is a JSON list of `{ "owner", "kind", "image_url", "source", "licence", "licence_kind",
"credit", "caption", "date"?, "person"? }`. Every entry is checked before anything is downloaded: an owner that
resolves to no story, alias or person, a kind that does not fit the owner, a fair-use headshot or
person picture, a person picture the story's tellers do not allow, an
`image_url` or `source` that is not http(s), or a missing or unknown field stops the run. An entry
whose `image_url` already has a sidecar under the owner (or under the story's id or aliases) is
`kept`; the others are downloaded (urllib, with a descriptive User-Agent), resized and converted
with macOS `sips`, and written under the resolved owner with the next free `n`, one line printed
per image. A download that is neither a JPEG, a PNG nor a GIF is refused before `sips`; a GIF (a scanned
page on Commons, often) is converted to a JPEG, so a stored file is always a JPEG or a PNG. A failed download or
conversion raises with the URL (and the HTTP status where there is one); with `--keep-going` the run
goes on to the next entry, lists the failures at the end and exits 1.

`check.py` validates the sidecars and the files with `problems`; `build.py` reads them with
`load_sidecars` and `blocks`.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import shutil
import http.client
import struct
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .common import DATE, HTTP, REPO, Root, load_json, rel, save_json, text_field

STORY_IMAGE_KINDS = ("object", "place-then", "place-now", "person")
PERSON_IMAGE_KINDS = ("headshot",)
LICENCE_KINDS = ("free", "fair-use")
SIDECAR_KEYS = ("file", "kind", "caption", "source", "image_url", "licence", "licence_kind", "credit", "date", "person", "fetched")
SIDECAR_OPTIONAL = ("date", "person")
MANIFEST_KEYS = ("owner", "kind", "image_url", "source", "licence", "licence_kind", "credit", "caption", "date", "person")
MANIFEST_OPTIONAL = ("date", "person")
BLOCK_KEYS = ("file", "kind", "caption", "credit", "licence", "licence_kind", "source", "date", "person")
MAX_PX = {"free": 1200, "fair-use": 480}
USER_AGENT = "NHI-timeline/0.1 (research; contact via github John-Therrien-WA)"
DAY = re.compile(r"\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])")
N = re.compile(r"[1-9]\d*")


def images_dir(root: Root) -> Path:
    return root.data / "images"


def site_images_dir(root: Root) -> Path:
    return root.site / "images"


def load_sidecars(root: Root) -> dict[str, list[tuple[int, dict]]]:
    """data/images/<owner>/<n>.json as {owner: [(n, sidecar), ...]} sorted by n; {} without the directory.
    Fails on a file that is not `<n>.json` or not a JSON object; `problems` checks the fields."""
    d = images_dir(root)
    out: dict[str, list[tuple[int, dict]]] = {}
    if not d.exists():
        return out
    for f in sorted(d.iterdir()):
        if f.name.startswith("."):
            continue
        if not f.is_dir():
            raise SystemExit(f"{rel(f, root.path)}: data/images holds one directory per owner, not files")
        rows = []
        for g in sorted(f.iterdir()):
            if g.name.startswith("."):
                continue
            if g.suffix != ".json" or not N.fullmatch(g.stem):
                raise SystemExit(f"{rel(g, root.path)}: a sidecar is named <n>.json with n = 1, 2, ...")
            obj = load_json(g)
            if not isinstance(obj, dict):
                raise SystemExit(f"{rel(g, root.path)}: a sidecar must be a JSON object")
            rows.append((int(g.stem), obj))
        out[f.name] = sorted(rows, key=lambda r: r[0])
    return out


def resolve_owner(owner: str, stories: dict, story_alias: dict[str, str], people: dict) -> tuple[str, str] | None:
    """("story", story id) for a story id or an alias of one, ("person", id) for a person, None for neither.
    Fails when the id is both a story (or alias) and a person: an owner must be one thing."""
    sid = owner if owner in stories else story_alias.get(owner)
    if sid is not None and owner in people:
        raise SystemExit(f"image owner {owner!r} is both a story (or alias) and a person")
    if sid is not None:
        return ("story", sid)
    if owner in people:
        return ("person", owner)
    return None


def kinds_for(owner_type: str) -> tuple[str, ...]:
    return STORY_IMAGE_KINDS if owner_type == "story" else PERSON_IMAGE_KINDS


def image_format(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def png_has_alpha(data: bytes) -> bool:
    """True when a PNG has an alpha channel (colour type 4 or 6) or a tRNS chunk."""
    if image_format(data) != "png" or len(data) < 26:
        return False
    if data[25] in (4, 6):
        return True
    i = 8
    while i + 8 <= len(data):
        length, ctype = struct.unpack(">I4s", data[i:i + 8])
        if ctype == b"tRNS":
            return True
        if ctype == b"IDAT":
            return False
        i += 12 + length
    return False


def dimensions(data: bytes) -> tuple[int, int] | None:
    """(width, height) of a JPEG or PNG from its header, None when it cannot be read."""
    fmt = image_format(data)
    if fmt == "png":
        if len(data) < 24 or data[12:16] != b"IHDR":
            return None
        return struct.unpack(">II", data[16:24])
    if fmt == "jpeg":
        i = 2
        while i + 4 <= len(data):
            if data[i] != 0xFF:
                return None
            marker = data[i + 1]
            if marker == 0xFF:
                i += 1
                continue
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            (length,) = struct.unpack(">H", data[i + 2:i + 4])
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                if i + 9 > len(data):
                    return None
                h, w = struct.unpack(">HH", data[i + 5:i + 9])
                return (w, h)
            i += 2 + length
    return None


def fields_problems(where: str, e: dict, keys: tuple, optional: tuple, owner_type: str | None) -> list[str]:
    """The fields a sidecar and a manifest entry share: kind, caption, source, image_url, licence,
    licence_kind, credit and the optional date."""
    out: list[str] = []
    for k in sorted(set(e) - set(keys)):
        out.append(f"{where}: unknown field {k!r} (the fields are {', '.join(keys)})")
    for k in keys:
        if k not in optional and k not in e:
            out.append(f"{where}: missing {k}")
    for k in ("caption", "licence", "credit"):
        if k in e and not text_field(e[k]):
            out.append(f"{where}: {k} must be a non-empty string")
    for k in ("source", "image_url"):
        if k in e and not (isinstance(e[k], str) and HTTP.fullmatch(e[k])):
            out.append(f"{where}: {k} {e[k]!r} is not an http(s) URL")
    if "licence_kind" in e and e["licence_kind"] not in LICENCE_KINDS:
        out.append(f"{where}: licence_kind {e['licence_kind']!r} is not one of {', '.join(LICENCE_KINDS)}")
    if "date" in e and not (isinstance(e["date"], str) and DATE.fullmatch(e["date"])):
        out.append(f"{where}: date {e['date']!r} is not YYYY, YYYY-MM or YYYY-MM-DD")
    if owner_type is not None and "kind" in e:
        allowed = kinds_for(owner_type)
        if e["kind"] not in allowed:
            out.append(f"{where}: kind {e['kind']!r} does not fit a {owner_type} owner (one of {', '.join(allowed)})")
    if e.get("kind") == "headshot" and e.get("licence_kind") == "fair-use":
        out.append(f"{where}: a headshot must be free-licensed, never fair use")
    if e.get("kind") == "person":
        if not text_field(e.get("person")):
            out.append(f"{where}: a person picture names who it shows in person")
        if e.get("licence_kind") == "fair-use":
            out.append(f"{where}: a person picture must be free-licensed, never fair use")
    elif "person" in e:
        out.append(f"{where}: person belongs to a person picture only, not a {e.get('kind')!r} one")
    return out


def load_profiles(root: Root) -> dict[str, dict]:
    """{story id: evidence profile} from data/scores.json, or {} when it is not there yet."""
    p = root.data / "scores.json"
    return {sid: s["profile"] for sid, s in load_json(p)["stories"].items()} if p.exists() else {}


def person_problem(where: str, story_id: str, e: dict, profiles: dict[str, dict]) -> str | None:
    """A person picture stands only beside a story two or more independent tellers tell, or one the
    person shown tells themselves."""
    if e.get("kind") != "person" or not text_field(e.get("person")):
        return None
    prof = profiles.get(story_id)
    if prof is None:
        return f"{where}: story {story_id} has no profile in data/scores.json (run pipeline.score) to allow a person picture"
    if prof["independent_tellers"] >= 2 or e["person"] in prof["tellers"]:
        return None
    return (f"{where}: a person picture of {e['person']!r} needs two or more independent tellers or {e['person']!r} "
            f"among them; story {story_id} is told by {', '.join(prof['tellers'])} only")


def problems(root: Root, stories: dict, story_alias: dict[str, str], people: dict) -> list[str]:
    """Every sidecar well formed, its owner resolving, its kind fitting the owner, no fair-use headshot,
    its `file` the JPEG or PNG at images/<owner>/<n>.<ext> under site/ within the size its licence
    allows, and every file under site/images/ claimed by a sidecar."""
    out: list[str] = []
    try:
        sidecars = load_sidecars(root)
    except SystemExit as e:
        return [str(e)]
    claimed: set[str] = set()
    profiles = load_profiles(root)
    seen_urls: dict[tuple[str, str], dict[str, str]] = {}  # resolved owner -> {image_url: "<dir>/<n>"}
    for owner, rows in sorted(sidecars.items()):
        try:
            resolved = resolve_owner(owner, stories, story_alias, people)
        except SystemExit as e:
            out.append(str(e))
            resolved = None
        if resolved is None:
            out.append(f"data/images/{owner}: {owner!r} is no story id, alias or person id")
        urls = seen_urls.setdefault(resolved or ("unresolved", owner), {})
        for n, sc in rows:
            where = f"data/images/{owner}/{n}.json"
            out += fields_problems(where, sc, SIDECAR_KEYS, SIDECAR_OPTIONAL, resolved[0] if resolved else None)
            if resolved and resolved[0] == "story" and (bad := person_problem(where, resolved[1], sc, profiles)):
                out.append(bad)
            if "fetched" in sc and not (isinstance(sc["fetched"], str) and DAY.fullmatch(sc["fetched"])):
                out.append(f"{where}: fetched {sc['fetched']!r} is not YYYY-MM-DD")
            url = sc.get("image_url")
            if isinstance(url, str):
                if url in urls:
                    out.append(f"{where}: image_url is the same as data/images/{urls[url]}.json's")
                urls[url] = f"{owner}/{n}"
            f = sc.get("file")
            if not isinstance(f, str):
                out.append(f"{where}: file must be a path relative to site/")
                continue
            claimed.add(f)
            if f not in (f"images/{owner}/{n}.jpg", f"images/{owner}/{n}.png"):
                out.append(f"{where}: file {f!r} must be images/{owner}/{n}.jpg or images/{owner}/{n}.png")
                continue
            p = root.site / f
            if not p.is_file():
                out.append(f"{where}: site/{f} does not exist")
                continue
            data = p.read_bytes()
            fmt = image_format(data)
            if fmt not in ("jpeg", "png"):
                out.append(f"{where}: site/{f} is neither a JPEG nor a PNG")
                continue
            if (fmt == "png") != f.endswith(".png"):
                out.append(f"{where}: site/{f} is a {fmt.upper()}, its extension says otherwise")
            if fmt == "png" and not png_has_alpha(data):
                out.append(f"{where}: site/{f} is a PNG without transparency; it must be a .jpg")
            size = dimensions(data)
            limit = MAX_PX.get(sc.get("licence_kind"))
            if size is None:
                out.append(f"{where}: cannot read the pixel size of site/{f}")
            elif limit and max(size) > limit:
                out.append(f"{where}: site/{f} is {size[0]}x{size[1]}, larger than the {limit} px a {sc['licence_kind']} image may be")
    sd = site_images_dir(root)
    if sd.exists():
        for p in sorted(sd.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                r = p.relative_to(root.site).as_posix()
                if r not in claimed:
                    out.append(f"site/{r}: no sidecar under data/images claims it")
    return out


def block(sc: dict) -> dict:
    """The image as the page gets it."""
    return {k: sc.get(k) for k in BLOCK_KEYS}


def blocks(root: Root, stories: dict, story_alias: dict[str, str], people: dict) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """({story id: [blocks]}, {person id: first headshot block}) for build.py; an alias's images fold into
    the surviving story after the story's own. Fails on an owner that resolves to nothing."""
    by_story: dict[str, list[tuple[int, int, dict]]] = {}
    by_person: dict[str, dict] = {}
    for owner, rows in sorted(load_sidecars(root).items()):
        resolved = resolve_owner(owner, stories, story_alias, people)
        if resolved is None:
            raise SystemExit(f"build: data/images/{owner} names no story, alias or person (run pipeline.check)")
        typ, oid = resolved
        for n, sc in rows:
            if sc.get("kind") not in kinds_for(typ):
                raise SystemExit(f"build: data/images/{owner}/{n}.json has kind {sc.get('kind')!r}, which does not fit a {typ} (run pipeline.check)")
            if typ == "story":
                by_story.setdefault(oid, []).append((0 if owner == oid else 1, n, block(sc)))
            elif oid not in by_person:
                by_person[oid] = block(sc)
    return ({sid: [b for _, _, b in sorted(rows, key=lambda r: (r[0], r[1]))] for sid, rows in by_story.items()}, by_person)


# ---------- ingest ----------

DOWNLOAD_PAUSE_S = 2.0  # Wikimedia answers 429 to a burst of thumbnail requests
THROTTLE_WAITS_S = (30, 90, 180)  # after a 429, the waits before each new try; then the download fails


def download(url: str) -> bytes:
    # a file name with a letter outside ASCII (Mystères) is percent-encoded; an encoded one is left as it is
    req = urllib.request.Request(urllib.parse.quote(url, safe=":/?=&%,()'!*;+@~$#"), headers={"User-Agent": USER_AGENT})
    for wait in THROTTLE_WAITS_S + (None,):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and wait is not None:
                time.sleep(wait)
                continue
            raise SystemExit(f"download failed: {url}: HTTP {e.code} {e.reason}")
        except urllib.error.URLError as e:
            raise SystemExit(f"download failed: {url}: {e.reason}")
        except (http.client.HTTPException, OSError) as e:
            raise SystemExit(f"download failed: {url}: {e}")
    raise AssertionError("unreachable: the last try either returns or raises")


def sips() -> str:
    exe = shutil.which("sips")
    if not exe:
        raise SystemExit("images: macOS sips is not on the path; it resizes and converts the images")
    return exe


def convert(data: bytes, out_stem: Path, max_px: int) -> Path:
    """The downloaded bytes as <out_stem>.png (a PNG with transparency) or <out_stem>.jpg (anything
    else sips reads), at most `max_px` on the long side, never enlarged. A JPEG, or a PNG with
    transparency, already within the size is copied as downloaded; everything else goes through sips."""
    fmt = image_format(data)
    keep_png = fmt == "png" and png_has_alpha(data)
    target = out_stem.with_suffix(".png" if keep_png else ".jpg")
    size = dimensions(data) if fmt in ("jpeg", "png") else None
    if size and max(size) <= max_px and (fmt == "jpeg" or keep_png):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        return target
    exe = sips()
    with tempfile.TemporaryDirectory(prefix="nhi-image-") as tmp:
        src = Path(tmp) / "download"
        src.write_bytes(data)
        probe = subprocess.run([exe, "-g", "pixelWidth", "-g", "pixelHeight", str(src)], capture_output=True, text=True)
        w = re.search(r"pixelWidth: (\d+)", probe.stdout)
        h = re.search(r"pixelHeight: (\d+)", probe.stdout)
        if probe.returncode or not (w and h):
            raise SystemExit(f"images: sips cannot read the downloaded file as an image ({probe.stderr.strip() or probe.stdout.strip()})")
        cmd = [exe, "-s", "format", "png" if keep_png else "jpeg"]
        if not keep_png:
            cmd += ["-s", "formatOptions", "85"]
        if max(int(w.group(1)), int(h.group(1))) > max_px:
            cmd += ["-Z", str(max_px)]
        tmp_out = Path(tmp) / target.name
        run = subprocess.run(cmd + [str(src), "--out", str(tmp_out)], capture_output=True, text=True)
        if run.returncode or not tmp_out.exists():
            raise SystemExit(f"images: sips failed ({run.stderr.strip() or run.stdout.strip()}); inside the Claude Code "
                             "sandbox sips cannot write its temporary file under /var/folders, so run this stage outside it")
        made = tmp_out.read_bytes()
        size = dimensions(made)
        if size is None or max(size) > max_px:
            raise SystemExit(f"images: sips wrote {size}, expected at most {max_px} px on the long side")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(made)
    return target


def manifest_problems(entries, stories: dict, story_alias: dict[str, str], people: dict, profiles: dict[str, dict]) -> list[str]:
    if not isinstance(entries, list):
        return ["manifest: must be a JSON list of entries"]
    out: list[str] = []
    for i, e in enumerate(entries):
        where = f"manifest entry {i + 1}"
        if not isinstance(e, dict):
            out.append(f"{where}: must be an object")
            continue
        where += f" ({e.get('owner')!r})"
        owner = e.get("owner")
        resolved = None
        if not text_field(owner):
            out.append(f"{where}: owner must be a story id, an alias or a person id")
        else:
            try:
                resolved = resolve_owner(owner, stories, story_alias, people)
            except SystemExit as x:
                out.append(f"{where}: {x}")
            else:
                if resolved is None:
                    out.append(f"{where}: owner {owner!r} is no story id, alias or person id")
        out += fields_problems(where, e, MANIFEST_KEYS, MANIFEST_OPTIONAL, resolved[0] if resolved else None)
        if resolved and resolved[0] == "story" and (bad := person_problem(where, resolved[1], e, profiles)):
            out.append(bad)
    return out


def ingest(root: Root, entries, fetch=download, keep_going: bool = False, today: str | None = None, echo=print) -> tuple[list[str], list[str]]:
    """Download, resize and record every manifest entry; return (the lines printed, the failures).
    `fetch` is the downloader and `echo` the printer (the fixture check passes a downloader that serves
    local bytes and a silent printer)."""
    stories, people = root.load_dir(root.stories), root.load_dir(root.people)
    story_alias = root.story_aliases(stories)
    bad = manifest_problems(entries, stories, story_alias, people, load_profiles(root))
    if bad:
        raise SystemExit("images: the manifest is refused:\n" + "\n".join(bad))
    today = today or dt.date.today().isoformat()
    lines: list[str] = []
    failures: list[str] = []
    for e in entries:
        typ, oid = resolve_owner(e["owner"], stories, story_alias, people)
        dirs = [oid] + ([a for a in stories[oid].get("aliases", [])] if typ == "story" else [])
        held = load_sidecars(root)
        known = {sc.get("image_url"): f"{d}/{n}" for d in dirs for n, sc in held.get(d, [])}
        if e["image_url"] in known:
            line = f"kept     {known[e['image_url']]}  {e['image_url']}"
            echo(line)
            lines.append(line)
            continue
        n = max([k for k, _ in held.get(oid, [])], default=0) + 1
        while (images_dir(root) / oid / f"{n}.json").exists():
            n += 1
        url = e["image_url"]
        try:
            time.sleep(DOWNLOAD_PAUSE_S)
            data = fetch(url)
            if image_format(data) is None:
                raise SystemExit(f"images: {url}: the download is neither a JPEG, a PNG nor a GIF")
            target = convert(data, site_images_dir(root) / oid / str(n), MAX_PX[e["licence_kind"]])
        except SystemExit as x:
            msg = str(x) if url in str(x) else f"images: {url}: {x}"
            if not keep_going:
                raise SystemExit(msg)
            failures.append(msg)
            echo(f"failed   {oid}  {msg}")
            continue
        sc = {"file": target.relative_to(root.site).as_posix(), "kind": e["kind"], "caption": e["caption"],
              "source": e["source"], "image_url": e["image_url"], "licence": e["licence"],
              "licence_kind": e["licence_kind"], "credit": e["credit"]}
        for k in MANIFEST_OPTIONAL:
            if k in e:
                sc[k] = e[k]
        sc["fetched"] = today
        save_json(images_dir(root) / oid / f"{n}.json", sc)
        w, h = dimensions(target.read_bytes())
        line = f"added    {oid}/{n}  {sc['file']} {w}x{h} {e['kind']} {e['licence_kind']}"
        echo(line)
        lines.append(line)
    return lines, failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--keep-going", action="store_true", help="go on after a failed download; exit 1 at the end")
    a = ap.parse_args(argv)
    _, failures = ingest(Root(a.root), load_json(a.manifest), keep_going=a.keep_going)
    if failures:
        print(f"images: {len(failures)} download(s) failed:", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
