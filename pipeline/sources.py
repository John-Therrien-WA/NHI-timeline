"""Primary sources: a named public document checked in the open, its own words added as a telling.

    uv run python -m pipeline.sources <manifest.json> [--root DIR] [--keep-going]

When a story names a source that can be read online (a paper, a book, a memo, a patent, a court
record, an article), a scout finds it and returns a manifest entry; this stage ingests it. The
source's words become one more telling of the story when the source itself says what the story
claims, and a `source` note in the story's `discussion` when the manifest says the source differs
from what the tellers make of it. Nothing here asserts that a story is true.

The evidence is `sources/documents/<document id>.txt`, like a caption file: for a document of status
`public-domain` with a `text_url` the full text as fetched from that plain-text URL, for every other
document (in copyright, `unknown`, or with no status) only the quoted passages, each a paragraph
after a line `[<locator>]` (a page, chapter or section). The format follows from the document's
status and text_url (`full_text`), never from the file's lines, so a bracketed line in a full text
(`[Illustration]`) is text. A quote is verbatim when, reduced by `common.norm_quote` (whitespace
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
document, one with a different url or year) or created. An existing one takes the manifest's title
when its own differs (a stored title may be a stub `merge.py` made from a teller's words, "Einstein
1921 ether paper"; each replacement is printed as a `title` line) and gets its other missing fields
filled, never overwritten. The text file is written from `text.url` (fetched with urllib; anything
but a 200 with a text/plain body fails) or from the passages (new passages appended to a passages
file); a text file already there is kept and never fetched again (delete it to fetch anew). Only a
public-domain document with a text_url takes `text.url`, and it takes nothing else. Every quote is
checked against the resulting text before anything of the entry is written. The teller is `teller`,
else the document's `author`, else its `issuer` as a person of role official whose tellings are of
kind `official` whatever the manifest's kind, created through `merge.ensure_person` and the person
aliases when new. Each quote becomes a telling `{ document, page, teller, quote, kind, cites: [],
documents: [] }` (`page` the quote's locator) unless the story holds the same (document, quote);
`differs` becomes `{ kind: "source", by: the document's title, date, source: url, text }` unless the
story holds the same text. A failed entry raises with its reason; with --keep-going the run goes on, lists the
failures at the end and exits 1.

The entries' images are written, deduplicated, to `<manifest stem>.images.json` beside the manifest
for `pipeline.images` (downloads need their own run). Run after clips, before `people --fold` and score; the
changed stories are printed so `explain --force` can rewrite their plain tellings.

`check.py` holds the document tellings to their text files with `problems`.
"""
from __future__ import annotations

import argparse
import http.client
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

from . import images
from .common import (DATE, HTTP, REPO, Root, document_aliases, load_json, norm_quote, norm_ws, person_aliases, rel, save_json,
                     slugify, text_field)
from .merge import ensure_person, same_telling

STATUSES = ("public-domain", "in-copyright", "unknown")
SOURCE_KINDS = ("firsthand", "official", "journalist", "researcher")
ROLE = {"firsthand": "participant", "official": "official", "journalist": "journalist", "researcher": "researcher"}
ENTRY_KEYS = ("story", "document", "text", "quotes", "teller", "kind", "differs", "images")
DOCUMENT_KEYS = ("id", "title", "author", "issuer", "date", "url", "text_url", "status")
FILL_KEYS = ("title", "issuer", "date", "url", "text_url", "status")
LOCATOR = re.compile(r"\[([^\[\]]+)\]")


def text_dir(root: Root) -> Path:
    return root.path / "sources" / "documents"


def text_path(root: Root, did: str) -> Path:
    return text_dir(root) / f"{did}.txt"


def full_text(doc: dict) -> bool:
    """A document whose evidence is its whole text: public domain, with the text_url it is fetched from.
    Every other document (in copyright, of unknown status, or with no status) keeps quoted passages."""
    return doc.get("status") == "public-domain" and bool(doc.get("text_url"))


class DocumentText:
    """The evidence file of one document, read in the format its document's status gives (`full_text`),
    never guessed from the file: a full text is one passage, a bracketed line in it (`[Illustration]`,
    `[Footnote 1]`) plain text; a passages file is paragraphs each under its `[locator]` line, with no
    text before the first."""

    def __init__(self, text: str, passages: bool, where: str = "document text"):
        self.is_passages = passages
        self.passages: list[tuple[str | None, str]] = []
        if passages:
            loc, buf = None, []
            for line in text.splitlines():
                m = LOCATOR.fullmatch(line.strip())
                if m:
                    if loc is not None:
                        self.passages.append((loc, " ".join(buf)))
                    loc, buf = norm_ws(m.group(1)), []
                elif line.strip():
                    if loc is None:
                        raise SystemExit(f"{where}: text before the first [locator] line; this document keeps quoted passages "
                                         "only, each under its [locator] (a full text is kept for a public-domain document with a text_url)")
                    buf.append(line)
            if loc is not None:
                self.passages.append((loc, " ".join(buf)))
            empty = [loc for loc, p in self.passages if not p.strip()]
            if empty:
                raise SystemExit(f"{where}: [{empty[0]}] has no text under it")
        else:
            self.passages.append((None, " ".join(line for line in text.splitlines() if line.strip())))
        if not any(p for _, p in self.passages):
            raise SystemExit(f"{where}: no text")
        self.norm = norm_quote(text)
        self._norm_passages = [(loc, norm_quote(p)) for loc, p in self.passages]

    @classmethod
    def read(cls, f: Path, root: Path, passages: bool) -> "DocumentText":
        return cls(f.read_text(encoding="utf-8"), passages, rel(f, root))

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
        if self.is_passages:
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
    """Every document's `status` and `text_url` well formed; every file under sources/documents a
    document's and readable in its document's format (a full text for a public-domain document with a
    text_url, else [locator] passages only); every document telling backed by its text file, its quote a
    verbatim substring of it, inside the passage its `page` names when the file holds passages."""
    out: list[str] = []
    for did, d in sorted(documents.items()):
        if d.get("status") is not None and d["status"] not in STATUSES:
            out.append(f"document {did}: status {d['status']!r} is not one of {', '.join(STATUSES)}")
        if d.get("text_url") is not None and not (isinstance(d["text_url"], str) and HTTP.fullmatch(d["text_url"])):
            out.append(f"document {did}: text_url {d['text_url']!r} is not an http(s) URL")
    texts: dict[str, DocumentText | None] = {}
    d = text_dir(root)
    if d.exists():
        for f in sorted(d.iterdir()):
            if f.name.startswith("."):
                continue
            if f.suffix != ".txt" or f.stem not in documents:
                out.append(f"{rel(f, root.path)}: no document in data/documents has this text")
                continue
            try:
                texts[f.stem] = DocumentText.read(f, root.path, not full_text(documents[f.stem]))
            except SystemExit as e:
                out.append(f"document {f.stem}: {e}")
                texts[f.stem] = None
    for sid, s in sorted(stories.items()):
        for i, t in enumerate(s.get("tellings") or []):
            did = t.get("document")
            if not did or did not in documents:
                continue
            tw = f"story {sid} telling {i + 1}"
            if did not in texts:
                out.append(f"{tw}: document {did} has no text file {rel(text_path(root, did), root.path)}")
                continue
            doc = texts[did]
            if doc is None or not (t.get("quote") or "").strip():
                continue
            if (bad := doc.quote_problem(t["quote"], t.get("page"))):
                out.append(f"{tw}: {did}: {bad}")
    return out


# ---------- the manifest ----------

def _opt_text(v) -> bool:
    return v is None or text_field(v)


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
        if not text_field(d.get("title")):
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
        if not (text_field(e.get("teller")) or text_field(d.get("author")) or text_field(d.get("issuer"))):
            out.append(f"{where}: no teller: give teller, or the document's author or issuer")
        if text_field(e.get("differs")) and not (d.get("url") or d.get("text_url")):
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
        if not isinstance(ps, list) or not all(isinstance(p, dict) and set(p) == {"locator", "text"} and text_field(p["locator"])
                                               and text_field(p["text"]) and not LOCATOR.search(p["locator"])
                                               and not any(LOCATOR.fullmatch(x.strip()) for x in p["text"].splitlines()) for p in ps):
            out.append(f"{where}: text passages must be a list of {{locator, text}}, both non-empty, the locator without brackets, no line of the text a bracketed line")
            ps = []
        if bool(t.get("url")) == bool(ps):
            out.append(f"{where}: text needs exactly one of a url or passages")
        if d is not None and t.get("url") and not full_text(d):
            out.append(f"{where}: a full text is fetched only for a public-domain document with a text_url; "
                       f"this one is {d.get('status')!r}{'' if d.get('text_url') else ' with no text_url'}, so give the quoted passages")
        if d is not None and ps and full_text(d):
            out.append(f"{where}: a public-domain document with a text_url keeps its full text; give text.url, not passages")
    qs = e.get("quotes")
    if "quotes" in e and not (isinstance(qs, list) and qs and all(isinstance(q, dict) and set(q) == {"quote", "locator"}
                                                                  and text_field(q["quote"]) and text_field(q["locator"]) for q in qs)):
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
    except (OSError, http.client.IncompleteRead) as e:
        raise SystemExit(f"fetch failed: {url}: {e}")
    try:
        text = data.decode(charset)
    except (UnicodeDecodeError, LookupError) as e:
        raise SystemExit(f"fetch failed: {url}: the body is not {charset} text ({e})")
    return text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")


def find_document(documents: dict, m: dict) -> tuple[str, bool]:
    """(document id, True when it is to be created). An id or title slug that a document fold made an alias
    (`common.document_aliases`) is the document that absorbed it."""
    aliases = document_aliases(documents)
    if m["id"] is not None:
        did = aliases.get(m["id"], m["id"])
        return did, did not in documents
    for key in ("url", "text_url"):
        if m.get(key):
            hits = sorted(did for did, d in documents.items() if m[key] in (d.get("url"), d.get("text_url")))
            if hits:
                return hits[0], False
    year = (m.get("date") or "")[:4] or None

    def same(d: dict) -> bool:
        return (d.get("url") in (None, m.get("url"))) and (d.get("date") is None or year is None or str(d["date"])[:4] == year)

    did = slugify(m["title"])
    did = aliases.get(did, did)
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
    # the teller: an institution standing in as author tells as an official record
    name, kind = e.get("teller") or m.get("author"), e["kind"]
    if not name:
        name, kind = m["issuer"], "official"
    did, new_doc = find_document(documents, m)
    doc = dict(documents.get(did) or {"id": did, "title": m["title"], "issuer": None, "date": None, "url": None,
                                      "text_url": None, "status": None, "kind": None, "attests": []})
    lines: list[str] = []
    if doc["title"] != m["title"]:  # a stored title may be a stub merge made from a teller's words
        lines.append(f"title    {did}  {doc['title']!r} becomes {m['title']!r}")
        doc["title"] = m["title"]
    for k in FILL_KEYS:
        if doc.get(k) is None and m.get(k) is not None:
            doc[k] = m[k]
    if doc.get("kind") is None:
        doc["kind"] = kind
    # the text, in the format the document's status gives
    full = full_text(doc)
    f = text_path(root, did)
    held = DocumentText.read(f, root.path, not full) if f.exists() else None
    body = None
    if e["text"].get("url"):
        if not full:
            raise SystemExit(f"document {did} is {doc.get('status')!r}{'' if doc.get('text_url') else ' with no text_url'}, "
                             "so it keeps quoted passages only; a full text is fetched for a public-domain document")
        if held is not None:
            text = held
        else:
            body = fetch(e["text"]["url"])
            text = DocumentText(body, False, e["text"]["url"])
    else:
        if full:
            raise SystemExit(f"document {did} is public domain with a text_url, so its evidence is the full text; give text.url")
        body = passages_text(merged_passages(held, e["text"]["passages"]))
        text = DocumentText(body, True, rel(f, root.path))
        if held is not None and body == f.read_text(encoding="utf-8"):
            body = None
    bad = [p for q in e["quotes"] if (p := text.quote_problem(q["quote"], q["locator"]))]
    if bad:
        raise SystemExit(f"document {did}: " + "; ".join(bad))
    role = ROLE[kind]
    pid = ensure_person(people, name, role, aliases)
    new_person = people[pid].pop("_new", False)
    if (bad := image_owner_problems(f"entry for {sid}", e, sid, story_alias, pid)):
        raise SystemExit("; ".join(bad))
    # the story
    changed = False
    for q in e["quotes"]:
        t = {"document": did, "page": norm_ws(q["locator"]), "teller": pid, "quote": q["quote"], "kind": kind,
             "cites": [], "documents": []}
        if any(same_telling(t, x) for x in story["tellings"]):
            lines.append(f"kept     {sid}  {did} [{t['page']}]")
            continue
        story["tellings"].append(t)
        changed = True
        lines.append(f"added    {sid}  telling {did} [{t['page']}] by {pid} ({kind})")
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
