"""Primary sources: a named public document checked in the open, its own words added as a telling.

    uv run python -m pipeline.sources <manifest.json> [--root DIR] [--keep-going]

When a story names a source that can be read online (a paper, a book, a memo, a patent, a court
record, an article), a scout finds it and returns a manifest entry; this stage ingests it. The
source's words become one more telling of the story when the source itself says what the story
claims, and a `source` note in the story's `discussion` when the manifest says the source differs
from what the tellers make of it. Nothing here asserts that a story is true.

The evidence is `sources/documents/<document id>.txt`, like a caption file: for a public-domain or
government document the full text as fetched from the plain-text URL the scout gives, for a
document in copyright only the quoted passages, each a paragraph after a line `[<locator>]` (a
page, chapter or section). A quote is verbatim when, reduced by `common.norm_quote` (whitespace
collapsed, case and punctuation exact), it is a substring of the file reduced the same way; in a
passages file it must lie inside one passage, under its own locator.

The manifest is a JSON list, one entry per story:

    { "story": id or alias,
      "document": { "id": existing id or null, "title", "author", "issuer", "date", "url", "text_url", "status" },
      "text": { "url": plain-text URL or null, "passages": [ { "locator", "text" } ] },
      "quotes": [ { "quote", "locator" } ],
      "teller": author name or null, "kind": firsthand | official | journalist | researcher,
      "differs": text of the source note or null,
      "images": [ images.py manifest entries, owner the story id or the teller's person id ] }

The whole manifest is checked for shape before anything is fetched; a malformed entry refuses the
run. Then each entry in turn: the document is found (the id given; else an existing document with
the same `url` or `text_url`; else the slug of the title, plus `-<year>` when that slug is another
document, one with a different url or year) or created, and an existing one gets its missing fields
filled, never overwritten. The text file is written from `text.url` (fetched with urllib; anything
but a 200 with a text/plain body fails) or from the passages (new passages appended to a passages
file); a text file already there is kept and never fetched again (delete it to fetch anew). A
document `in-copyright` takes passages only. Every quote is checked against the resulting text
before anything of the entry is written. The teller is `teller`, else the document's `author`, else
its `issuer` as a person of role official, created through `merge.ensure_person` and the person
aliases when new. Each quote becomes a telling `{ document, page, teller, quote, kind, cites: [],
documents: [] }` (`page` the quote's locator) unless the story holds the same (document, quote);
`differs` becomes `{ kind: "source", by: title, date, source: url, text }` unless the story holds
the same text. A failed entry raises with its reason; with --keep-going the run goes on, lists the
failures at the end and exits 1.

The entries' images are written, deduplicated, to `<manifest stem>.images.json` beside the manifest
for `pipeline.images` (downloads need their own run). Run after merge and clips, before score; the
changed stories are printed so `explain --force` can rewrite their plain tellings.

`check.py` holds the document tellings to their text files with `problems`.
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import images
from .common import REPO, Root, load_json, norm_quote, norm_ws, person_aliases, rel, save_json, slugify
from .merge import ensure_person, same_telling

STATUSES = ("public-domain", "in-copyright", "unknown")
SOURCE_KINDS = ("firsthand", "official", "journalist", "researcher")
ROLE = {"firsthand": "participant", "official": "official", "journalist": "journalist", "researcher": "researcher"}
ENTRY_KEYS = ("story", "document", "text", "quotes", "teller", "kind", "differs", "images")
DOCUMENT_KEYS = ("id", "title", "author", "issuer", "date", "url", "text_url", "status")
FILL_KEYS = ("title", "issuer", "date", "url", "text_url", "status")
LOCATOR = re.compile(r"\[([^\[\]]+)\]")
DATE = re.compile(r"\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?")
HTTP = re.compile(r"https?://\S+")


def text_dir(root: Root) -> Path:
    return root.path / "sources" / "documents"


def text_path(root: Root, did: str) -> Path:
    return text_dir(root) / f"{did}.txt"


class DocumentText:
    """The evidence file of one document: the whole text reduced for the verbatim comparison, and its
    passages under their `[locator]` lines (a full text without locator lines is one passage)."""

    def __init__(self, text: str, where: str = "document text"):
        self.passages: list[tuple[str | None, str]] = []
        loc, buf = None, []
        for line in text.splitlines():
            m = LOCATOR.fullmatch(line.strip())
            if m:
                if buf or loc is not None:
                    self.passages.append((loc, " ".join(buf)))
                loc, buf = norm_ws(m.group(1)), []
            elif line.strip():
                buf.append(line)
        if buf or loc is not None:
            self.passages.append((loc, " ".join(buf)))
        if not any(p for _, p in self.passages):
            raise SystemExit(f"{where}: no text")
        self.has_locators = any(loc is not None for loc, _ in self.passages)
        self.norm = norm_quote(text)
        self._norm_passages = [(loc, norm_quote(p)) for loc, p in self.passages]

    @classmethod
    def read(cls, f: Path, root: Path) -> "DocumentText":
        return cls(f.read_text(encoding="utf-8"), rel(f, root))

    def contains(self, quote: str) -> bool:
        q = norm_quote(quote)
        return bool(q) and q in self.norm

    def locators_of(self, quote: str) -> list[str | None]:
        """The locators of the passages that hold the quote whole."""
        q = norm_quote(quote)
        return [loc for loc, p in self._norm_passages if q and q in p]

    def quote_problem(self, quote: str, locator) -> str | None:
        """Why a quote with its locator does not stand in this text, or None. In a passages file the
        quote lies inside one passage under that locator; in a full text anywhere."""
        if not self.contains(quote):
            return f"quote is not a verbatim substring of the text: {quote[:60]!r}"
        if self.has_locators:
            locs = self.locators_of(quote)
            if not locs:
                return f"quote runs across two passages: {quote[:60]!r}"
            if norm_ws(str(locator)) not in locs:
                return f"quote stands under [{'], ['.join(str(x) for x in locs)}], not [{locator}]: {quote[:60]!r}"
        return None


def passages_text(passages: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"[{loc}]\n{text}" for loc, text in passages) + "\n"


# ---------- the check ----------

def problems(root: Root, stories: dict, documents: dict) -> list[str]:
    """Every document's `status` and `text_url` well formed; every document telling backed by its text
    file, its quote a verbatim substring of it (inside the passage its `page` names when the document is
    in copyright, whose file holds passages only); every file under sources/documents a document's."""
    out: list[str] = []
    for did, d in sorted(documents.items()):
        if d.get("status") is not None and d["status"] not in STATUSES:
            out.append(f"document {did}: status {d['status']!r} is not one of {', '.join(STATUSES)}")
        if d.get("text_url") is not None and not (isinstance(d["text_url"], str) and HTTP.fullmatch(d["text_url"])):
            out.append(f"document {did}: text_url {d['text_url']!r} is not an http(s) URL")
    texts: dict[str, DocumentText | None] = {}
    for sid, s in sorted(stories.items()):
        for i, t in enumerate(s.get("tellings") or []):
            did = t.get("document")
            if not did or did not in documents:
                continue
            tw = f"story {sid} telling {i + 1}"
            if did not in texts:
                f = text_path(root, did)
                try:
                    texts[did] = DocumentText.read(f, root.path) if f.exists() else None
                except SystemExit as e:
                    out.append(f"{tw}: {e}")
                    texts[did] = None
                    continue
            doc = texts[did]
            if doc is None:
                out.append(f"{tw}: document {did} has no text file {rel(text_path(root, did), root.path)}")
                continue
            if not (t.get("quote") or "").strip():
                continue
            if not doc.contains(t["quote"]):
                out.append(f"{tw}: quote is not a verbatim substring of {did}'s text: {t['quote'][:60]!r}")
            elif documents[did].get("status") == "in-copyright":
                if not doc.has_locators or doc.passages[0][0] is None:
                    out.append(f"{tw}: {did} is in copyright, so its text file holds [locator] passages only")
                elif (bad := doc.quote_problem(t["quote"], t.get("page"))):
                    out.append(f"{tw}: {did}: {bad}")
    d = text_dir(root)
    if d.exists():
        for f in sorted(d.iterdir()):
            if f.name.startswith("."):
                continue
            if f.suffix != ".txt" or f.stem not in documents:
                out.append(f"{rel(f, root.path)}: no document in data/documents has this text")
    return out


# ---------- the manifest ----------

def _text(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def _opt_text(v) -> bool:
    return v is None or _text(v)


def _opt_url(v) -> bool:
    return v is None or (isinstance(v, str) and bool(HTTP.fullmatch(v)))


def entry_problems(where: str, e, stories: dict, story_alias: dict[str, str]) -> list[str]:
    """The shape of one manifest entry, before anything is fetched or written."""
    if not isinstance(e, dict):
        return [f"{where}: must be an object"]
    out: list[str] = []
    for k in sorted(set(e) - set(ENTRY_KEYS)):
        out.append(f"{where}: unknown field {k!r} (the fields are {', '.join(ENTRY_KEYS)})")
    for k in ("story", "document", "text", "quotes", "kind"):
        if k not in e:
            out.append(f"{where}: missing {k}")
    if "story" in e and e["story"] not in stories and e["story"] not in story_alias:
        out.append(f"{where}: story {e['story']!r} is no story id or alias")
    if "kind" in e and e["kind"] not in SOURCE_KINDS:
        out.append(f"{where}: kind {e['kind']!r} is not one of {', '.join(SOURCE_KINDS)}")
    if not _opt_text(e.get("teller")):
        out.append(f"{where}: teller must be a name or null")
    if not _opt_text(e.get("differs")):
        out.append(f"{where}: differs must be the source note's text or null")
    d = e.get("document")
    if "document" in e and not isinstance(d, dict):
        out.append(f"{where}: document must be an object")
        d = None
    if d is not None:
        for k in sorted(set(d) - set(DOCUMENT_KEYS)):
            out.append(f"{where}: document has unknown field {k!r} (the fields are {', '.join(DOCUMENT_KEYS)})")
        for k in DOCUMENT_KEYS:
            if k not in d:
                out.append(f"{where}: document is missing {k} (null when unknown)")
        if not _text(d.get("title")):
            out.append(f"{where}: document title must be a non-empty string")
        if d.get("id") is not None and not (isinstance(d["id"], str) and d["id"] and slugify(d["id"]) == d["id"]):
            out.append(f"{where}: document id {d['id']!r} is not a slug")
        for k in ("author", "issuer"):
            if not _opt_text(d.get(k)):
                out.append(f"{where}: document {k} must be a name or null")
        for k in ("url", "text_url"):
            if not _opt_url(d.get(k)):
                out.append(f"{where}: document {k} {d.get(k)!r} is not an http(s) URL")
        if d.get("date") is not None and not (isinstance(d["date"], str) and DATE.fullmatch(d["date"])):
            out.append(f"{where}: document date {d['date']!r} is not YYYY, YYYY-MM or YYYY-MM-DD")
        if d.get("status") not in STATUSES:
            out.append(f"{where}: document status {d.get('status')!r} is not one of {', '.join(STATUSES)}")
        if not (_text(e.get("teller")) or _text(d.get("author")) or _text(d.get("issuer"))):
            out.append(f"{where}: no teller: give teller, or the document's author or issuer")
        if _text(e.get("differs")) and not (d.get("url") or d.get("text_url")):
            out.append(f"{where}: a source note needs the document's url or text_url")
    t = e.get("text")
    if "text" in e and not isinstance(t, dict):
        out.append(f"{where}: text must be an object")
        t = None
    if t is not None:
        for k in sorted(set(t) - {"url", "passages"}):
            out.append(f"{where}: text has unknown field {k!r} (the fields are url, passages)")
        if not _opt_url(t.get("url")):
            out.append(f"{where}: text url {t.get('url')!r} is not an http(s) URL")
        ps = t.get("passages", [])
        if not isinstance(ps, list) or not all(isinstance(p, dict) and set(p) == {"locator", "text"} and _text(p["locator"])
                                               and _text(p["text"]) and not LOCATOR.search(p["locator"]) for p in ps):
            out.append(f"{where}: text passages must be a list of {{locator, text}}, both non-empty, the locator without brackets")
            ps = []
        if bool(t.get("url")) == bool(ps):
            out.append(f"{where}: text needs exactly one of a url or passages")
        if t.get("url") and d is not None and d.get("status") == "in-copyright":
            out.append(f"{where}: a document in copyright keeps the quoted passages only, never a fetched full text")
    qs = e.get("quotes")
    if "quotes" in e and not (isinstance(qs, list) and qs and all(isinstance(q, dict) and set(q) == {"quote", "locator"}
                                                                  and _text(q["quote"]) and _text(q["locator"]) for q in qs)):
        out.append(f"{where}: quotes must be a non-empty list of {{quote, locator}}, both non-empty")
    ims = e.get("images", [])
    if not isinstance(ims, list):
        out.append(f"{where}: images must be a list")
    return out


def image_owner_problems(where: str, e: dict, sid: str, story_alias: dict[str, str], teller: str) -> list[str]:
    out: list[str] = []
    for i, im in enumerate(e.get("images") or []):
        iw = f"{where} image {i + 1}"
        if not isinstance(im, dict):
            out.append(f"{iw}: must be an object")
            continue
        owner = im.get("owner")
        if owner == sid or story_alias.get(owner) == sid:
            typ = "story"
        elif owner == teller:
            typ = "person"
        else:
            out.append(f"{iw}: owner {owner!r} is neither the story {sid} nor the teller {teller}")
            typ = None
        out += images.fields_problems(iw, im, images.MANIFEST_KEYS, images.MANIFEST_OPTIONAL, typ)
    return out


# ---------- the ingest ----------

USER_AGENT = images.USER_AGENT


def download(url: str) -> str:
    """The plain text at a URL; fails on anything but a 200 with a text/plain body."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            if r.status != 200:
                raise SystemExit(f"fetch failed: {url}: HTTP {r.status}")
            ctype = r.headers.get_content_type()
            if ctype != "text/plain":
                raise SystemExit(f"fetch failed: {url}: the body is {ctype}, not text/plain (give the plain-text URL)")
            data = r.read()
            charset = r.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        raise SystemExit(f"fetch failed: {url}: HTTP {e.code} {e.reason}")
    except urllib.error.URLError as e:
        raise SystemExit(f"fetch failed: {url}: {e.reason}")
    except OSError as e:
        raise SystemExit(f"fetch failed: {url}: {e}")
    try:
        text = data.decode(charset)
    except (UnicodeDecodeError, LookupError) as e:
        raise SystemExit(f"fetch failed: {url}: the body is not {charset} text ({e})")
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def find_document(documents: dict, m: dict) -> tuple[str, bool]:
    """(document id, True when it is to be created)."""
    if m["id"] is not None:
        return m["id"], m["id"] not in documents
    for key in ("url", "text_url"):
        if m.get(key):
            hits = sorted(did for did, d in documents.items() if m[key] in (d.get("url"), d.get("text_url")))
            if hits:
                return hits[0], False
    year = (m.get("date") or "")[:4] or None

    def same(d: dict) -> bool:
        return (d.get("url") in (None, m.get("url"))) and (d.get("date") is None or year is None or str(d["date"])[:4] == year)

    did = slugify(m["title"])
    if did not in documents:
        return did, True
    if same(documents[did]):
        return did, False
    if year is None:
        raise SystemExit(f"document {did} exists and is another document (url or year differ), and the manifest gives no date to tell them apart")
    did2 = f"{did}-{year}" if not did.endswith(year) else f"{did}-2"
    if did2 not in documents:
        return did2, True
    if same(documents[did2]):
        return did2, False
    raise SystemExit(f"documents {did} and {did2} both exist and both are other documents; give the document's id")


def merged_passages(existing: DocumentText | None, new: list[dict]) -> list[tuple[str, str]]:
    held = [(loc, norm_ws(p)) for loc, p in existing.passages] if existing else []
    for p in new:
        item = (norm_ws(p["locator"]), norm_ws(p["text"]))
        if item not in held:
            held.append(item)
    return held


def ingest_entry(root: Root, e: dict, stories: dict, story_alias: dict[str, str], people: dict, documents: dict,
                 aliases: dict[str, str], fetch) -> tuple[list[str], list[Path]]:
    """One entry in memory, then written; returns (the lines to print, the files it wrote).
    Raises SystemExit before writing anything when the text or a quote does not stand."""
    sid = e["story"] if e["story"] in stories else story_alias[e["story"]]
    story = stories[sid]
    m = e["document"]
    did, new_doc = find_document(documents, m)
    doc = dict(documents.get(did) or {"id": did, "title": m["title"], "issuer": None, "date": None, "url": None,
                                      "text_url": None, "status": None, "kind": None, "attests": []})
    for k in FILL_KEYS:
        if doc.get(k) is None and m.get(k) is not None:
            doc[k] = m[k]
    if doc.get("kind") is None:
        doc["kind"] = e["kind"]
    # the text
    f = text_path(root, did)
    held = DocumentText.read(f, root.path) if f.exists() else None
    body = None
    if held is not None and not held.has_locators:
        text = held
    elif e["text"].get("url"):
        if held is not None:
            text = held
        else:
            body = fetch(e["text"]["url"])
            text = DocumentText(body, e["text"]["url"])
    else:
        if held is not None and held.passages[0][0] is None:
            raise SystemExit(f"{rel(f, root.path)} holds text before its first [locator]; passages cannot be added to it")
        body = passages_text(merged_passages(held, e["text"]["passages"]))
        text = DocumentText(body, rel(f, root.path))
        if held is not None and body == f.read_text(encoding="utf-8"):
            body = None
    if doc.get("status") == "in-copyright" and not (text.has_locators and text.passages[0][0] is not None):
        raise SystemExit(f"document {did} is in copyright, and its text file holds a full text; keep the quoted passages only")
    bad = [p for q in e["quotes"] if (p := text.quote_problem(q["quote"], q["locator"]))]
    if bad:
        raise SystemExit(f"document {did}: " + "; ".join(bad))
    # the teller
    name = e.get("teller") or m.get("author")
    role = ROLE[e["kind"]]
    if not name:
        name, role = m["issuer"], "official"
    pid = ensure_person(people, name, role, aliases)
    new_person = people[pid].pop("_new", False)
    if (bad := image_owner_problems(f"entry for {sid}", e, sid, story_alias, pid)):
        raise SystemExit("; ".join(bad))
    # the story
    lines: list[str] = []
    changed = False
    for q in e["quotes"]:
        t = {"document": did, "page": norm_ws(q["locator"]), "teller": pid, "quote": q["quote"], "kind": e["kind"],
             "cites": [], "documents": []}
        if any(same_telling(t, x) for x in story["tellings"]):
            lines.append(f"kept     {sid}  {did} [{t['page']}]")
            continue
        story["tellings"].append(t)
        changed = True
        lines.append(f"added    {sid}  telling {did} [{t['page']}] by {pid} ({e['kind']})")
    if e.get("differs"):
        note = {"kind": "source", "by": doc["title"]}
        if isinstance(doc.get("date"), str) and DATE.fullmatch(doc["date"]):
            note["date"] = doc["date"]
        note["source"] = doc.get("url") or doc.get("text_url")
        note["text"] = norm_ws(e["differs"])
        if any(norm_ws(x.get("text") or "") == note["text"] for x in story.get("discussion", [])):
            lines.append(f"kept     {sid}  source note from {did}")
        else:
            story.setdefault("discussion", []).append(note)
            changed = True
            lines.append(f"added    {sid}  source note from {did}")
    # written only now that everything stands
    wrote: list[Path] = []
    if body is not None:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body if body.endswith("\n") else body + "\n", encoding="utf-8")
        wrote.append(f)
        lines.insert(0, f"text     {did}  {rel(f, root.path)}")
    documents[did] = doc
    if save_json(root.documents / f"{did}.json", doc):
        wrote.append(root.documents / f"{did}.json")
        lines.insert(0, f"{'document' if new_doc else 'filled  '} {did}")
    if save_json(root.people / f"{pid}.json", people[pid]) or new_person:
        wrote.append(root.people / f"{pid}.json")
    if changed and save_json(root.stories / f"{sid}.json", story):
        wrote.append(root.stories / f"{sid}.json")
    return lines, wrote


def images_manifest_path(manifest: Path) -> Path:
    return manifest.with_name(f"{manifest.stem}.images.json")


def run(root: Root, entries, *, manifest: Path | None = None, fetch=download, keep_going: bool = False,
        echo=print) -> dict:
    """Ingest every entry; return { "lines", "failures", "changed" (story ids), "images" (the entries
    written for pipeline.images) }. `fetch` is the text downloader (the fixture check serves local text)."""
    stories, people, documents = root.load_dir(root.stories), root.load_dir(root.people), root.load_dir(root.documents)
    story_alias = root.story_aliases(stories)
    aliases = person_aliases(root.path)
    if not isinstance(entries, list):
        raise SystemExit("sources: the manifest must be a JSON list of entries")
    bad = [p for i, e in enumerate(entries) for p in
           entry_problems(f"manifest entry {i + 1}" + (f" ({e.get('story')!r})" if isinstance(e, dict) else ""), e, stories, story_alias)]
    if bad:
        raise SystemExit("sources: the manifest is refused:\n" + "\n".join(bad))
    lines: list[str] = []
    failures: list[str] = []
    changed: list[str] = []
    found_images: list[dict] = []
    for i, e in enumerate(entries):
        sid = e["story"] if e["story"] in stories else story_alias[e["story"]]
        try:
            got, wrote = ingest_entry(root, e, stories, story_alias, people, documents, aliases, fetch)
        except SystemExit as x:
            msg = f"sources: entry {i + 1} ({sid}): {x}"
            if not keep_going:
                raise SystemExit(msg)
            failures.append(msg)
            echo(f"failed   {sid}  {x}")
            continue
        for line in got:
            echo(line)
        lines += got
        if root.stories / f"{sid}.json" in wrote and sid not in changed:
            changed.append(sid)
        for im in e.get("images") or []:
            if not any(x["owner"] == im["owner"] and x["image_url"] == im["image_url"] for x in found_images):
                found_images.append(im)
    if manifest is not None and found_images:
        out = images_manifest_path(manifest)
        save_json(out, found_images)
        echo(f"images   {len(found_images)} for pipeline.images in {out}")
    if changed:
        echo("sources: stories with new tellings or notes (explain --force them): " + " ".join(changed))
    return {"lines": lines, "failures": failures, "changed": changed, "images": found_images}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("manifest", type=Path)
    ap.add_argument("--root", default=REPO)
    ap.add_argument("--keep-going", action="store_true", help="go on after a failed entry; exit 1 at the end")
    a = ap.parse_args(argv)
    res = run(Root(a.root), load_json(a.manifest), manifest=a.manifest, keep_going=a.keep_going)
    if res["failures"]:
        print(f"sources: {len(res['failures'])} entr{'y' if len(res['failures']) == 1 else 'ies'} failed:", file=sys.stderr)
        for f in res["failures"]:
            print(f"  {f}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
