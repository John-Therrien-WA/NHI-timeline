"""A review page for a chosen set of stories: each story in full, followed by a rating and a comment box.

    uv run python -m pipeline.review <story id ...> -o <out.html> [--name N] [--title T] [--root DIR]

`--name` is the page's name (two to four words, the <title> and the heading), `--title` the one line
under it saying what the set is.

John reviews stories by reading them whole. The page shows, per story and in the order named: the title,
the years, era and place by name, the kind, the score block as scored now (tier, score, attestation and
the profile), the plain telling, the story's own photographs (data/images/<story id or alias>, embedded
as data URIs from site/images with caption, credit and licence), every telling grouped by teller (the
teller's headshot beside their own tellings only; an episode telling with its show, title, date and the
YouTube link at the time code, a document telling with its title, date, locator and URL; the quote
verbatim; what it cites and credits; its `difference` and `as_told`), the discussion entries (a source
note's text begins with the provenance of a document quoted only in source notes) and the
count of open viewer notes. Under each story a rating from 1 to 10 and a note, and at the end a general
note. The page is one self-contained file for a private claude.ai artifact with the `db` capability:
each story's comment is the document `comments/<story id>` (`{story, rating, note, at}`), the general
note `comments/general`, written as the fields change; without a database it keeps them in the
browser's localStorage. A button copies every filled comment as markdown. Numbers and ids are shown
exactly as the data holds them; the generator writes no words of its own about a story.

A page over ARTIFACT_FILE_BYTES (16,000,000, the most an artifact allows a file) is refused with
nothing written; the message names the size and the story ids cut into lists that each fit, walked in
the given order and cut when the running size would pass the limit (`split_to_fit`).

Fails on an unknown story id, a story without score, profile or tier, a teller, cited person, episode
or document that does not resolve, or a sidecar whose image file is missing.
"""
from __future__ import annotations

import argparse
import base64
import html
import json
import sys
from pathlib import Path

from . import images
from .build import open_notes, url_at
from .common import ARTIFACT_FILE_BYTES, REPO, Root, fmt_s, rel, seconds

MIME = {".jpg": "image/jpeg", ".png": "image/png"}
TIER_CLASS = {"well-attested": "tier-well", "told-by-several": "tier-several", "told-once": "tier-once"}
INSTRUCTIONS = ("Read each story as it stands, then rate it from 1 to 10 and write what you notice in the box "
                "beneath it; comments save as you type.")


def esc(v) -> str:
    return html.escape("" if v is None else str(v), quote=True)


def num(v) -> str:
    """A number exactly as the JSON holds it."""
    return json.dumps(v)


def years_text(y: dict | None) -> str:
    if not y:
        return "years not given"
    a, b = y.get("from"), y.get("to")
    if a is None and b is None:
        return "years not given"
    if a == b or b is None:
        return str(a)
    if a is None:
        return f"to {b}"
    return f"{a} to {b}"


class Data:
    """What the page reads, loaded once."""

    def __init__(self, root: Root):
        self.root = root
        self.stories = root.load_dir(root.stories)
        self.people = root.load_dir(root.people)
        self.episodes = root.load_dir(root.episodes)
        self.documents = root.load_dir(root.documents)
        self.eras = {e["id"]: e for e in root.eras()}
        self.places = {p["id"]: p for p in root.places()}
        self.owner = root.story_aliases(self.stories)
        self.notes_open = open_notes(root, self.stories, self.owner)
        self.story_images, self.headshots = images.blocks(root, self.stories, self.owner, self.people)

    def story_id(self, sid: str) -> str:
        if sid in self.stories:
            return sid
        if sid in self.owner:
            print(f"review: {sid} is an alias of {self.owner[sid]}; showing that story", file=sys.stderr)
            return self.owner[sid]
        raise SystemExit(f"review: no story or alias {sid!r} under {rel(self.root.stories, self.root.path)}")

    def person(self, pid: str, where: str) -> dict:
        if pid not in self.people:
            raise SystemExit(f"review: {where} names person {pid!r}, who has no file under data/people")
        return self.people[pid]

    def episode(self, eid: str, where: str) -> dict:
        if eid not in self.episodes:
            raise SystemExit(f"review: {where} names episode {eid!r}, which has no file under data/episodes")
        return self.episodes[eid]

    def document(self, did: str, where: str) -> dict:
        if did not in self.documents:
            raise SystemExit(f"review: {where} names document {did!r}, which has no file under data/documents")
        return self.documents[did]

    def data_uri(self, block: dict, where: str) -> str:
        f = images.site_images_dir(self.root) / Path(block["file"]).relative_to("images")
        if not f.exists():
            raise SystemExit(f"review: {where}: image {rel(f, self.root.path)} is missing")
        mime = MIME.get(f.suffix.lower())
        if mime is None:
            raise SystemExit(f"review: {where}: image {rel(f, self.root.path)} is neither .jpg nor .png")
        return f"data:{mime};base64," + base64.b64encode(f.read_bytes()).decode("ascii")


def link(url: str | None, text: str) -> str:
    return f'<a href="{esc(url)}" target="_blank" rel="noopener">{text}</a>' if url else text


def upfirst(s: str) -> str:
    return s[:1].upper() + s[1:]


def figure(d: Data, b: dict, where: str, cls: str = "pic") -> str:
    meta = [f"Credit: {esc(b['credit'])}.", f"Licence: {esc(b['licence'])} ({esc(b['licence_kind'])})."]
    extra = [esc(b["kind"])] + ([esc(b["date"])] if b.get("date") else []) + ([f"shows {esc(b['person'])}"] if b.get("person") else [])
    return (f'<figure class="{cls}"><img src="{d.data_uri(b, where)}" alt="{esc(b["caption"])}" loading="lazy">'
            f'<figcaption><span class="cap">{esc(b["caption"])}</span> '
            f'<span class="meta">{" ".join(meta)} {upfirst(", ".join(extra))}. {link(b.get("source"), "Source")}</span></figcaption></figure>')


def score_block(d: Data, s: dict) -> str:
    sid = s["id"]
    if not isinstance(s.get("score"), (int, float)) or not s.get("profile") or not s.get("tier"):
        raise SystemExit(f"review: story {sid} has no score, profile or tier: run pipeline.score first")
    p = s["profile"]
    rows = [("Tier", f'<span class="chip {TIER_CLASS.get(s["tier"], "")}">{esc(s["tier"])}</span>'),
            ("Score", esc(num(s["score"]))), ("Attestation", esc(num(s["attestation"])))]
    for k, v in p.items():
        if k == "tellers":
            names = [f'{esc(d.person(t, f"story {sid} profile")["name"])} <span class="id">{esc(t)}</span>' for t in v]
            rows.append(("tellers", ", ".join(names) or "none"))
        elif k == "episodes":
            rows.append(("episodes", f'{len(v)} <span class="id">{esc(", ".join(v))}</span>' if v else "0"))
        else:
            rows.append((k, esc(num(v) if not isinstance(v, str) else v)))
    cells = "".join(f"<div><dt>{esc(k).replace('_', ' ')}</dt><dd>{v}</dd></div>" for k, v in rows)
    return f'<section class="scored" aria-label="As scored now"><h3>As scored now</h3><dl>{cells}</dl></section>'


def telling_html(d: Data, s: dict, t: dict) -> str:
    sid = s["id"]
    where = f"story {sid}"
    if t.get("episode"):
        ep = d.episode(t["episode"], where)
        at = f" at {fmt_s(t['from_s'])}" if t.get("from_s") is not None else ""
        src = (f'{esc(ep.get("show"))}, &ldquo;{esc(ep.get("title"))}&rdquo;, {esc(ep.get("published"))}'
               f'{link(url_at(ep, t.get("from_s")), esc(at or " (episode)"))}'
               f' <span class="id">{esc(t["episode"])}</span>')
    elif t.get("document"):
        doc = d.document(t["document"], where)
        src = (f'{link(doc.get("url"), esc(doc["title"]))}, {esc(doc.get("date"))}, {esc(t.get("page"))}'
               f' <span class="id">{esc(t["document"])}</span>')
    else:
        raise SystemExit(f"review: {where}: a telling by {t.get('teller')} has neither episode nor document")
    lines = [f'<p class="src">{src} <span class="kind">{esc(t["kind"])}</span></p>',
             f'<blockquote>&ldquo;{esc(t.get("quote"))}&rdquo;</blockquote>']
    cites = [f'{esc(d.person(c, where)["name"])} <span class="id">{esc(c)}</span>' for c in t.get("cites", [])]
    credits = [f'{esc(d.document(x, where)["title"])} <span class="id">{esc(x)}</span>' for x in t.get("documents", [])]
    extra = []
    if cites:
        extra.append(f"<dt>Cites</dt><dd>{', '.join(cites)}</dd>")
    if credits:
        extra.append(f"<dt>Credits</dt><dd>{'; '.join(credits)}</dd>")
    if t.get("replay_of"):
        r = t["replay_of"]
        extra.append(f"<dt>Replay of</dt><dd>{'a recording from outside the corpus' if r.get('outside') else esc(r.get('episode')) + ' at ' + esc(fmt_s(r.get('from_s') or 0))}</dd>")
    if t.get("teller_was"):
        extra.append(f"<dt>Teller was</dt><dd>{esc(t['teller_was'])}</dd>")
    if t.get("difference"):
        extra.append(f"<dt>Difference</dt><dd>{esc(t['difference'])}</dd>")
    if t.get("as_told"):
        a = t["as_told"]
        extra.append(f"<dt>As told</dt><dd>&ldquo;{esc(a.get('title'))}&rdquo;, {esc(years_text(a.get('years')))}, "
                     f"{esc(a.get('place_text'))}, {esc(a.get('story_kind'))}</dd>")
    if extra:
        lines.append(f'<dl class="tmeta">{"".join(extra)}</dl>')
    return f'<li class="telling">{"".join(lines)}</li>'


def tellings_html(d: Data, s: dict) -> str:
    groups: dict[str, list[dict]] = {}
    for t in s["tellings"]:
        groups.setdefault(t["teller"], []).append(t)
    out = []
    for pid, ts in groups.items():
        p = d.person(pid, f"story {s['id']}")
        roles = ", ".join(p.get("roles") or []) or "no role recorded"
        aff = f", {esc(p['affiliation'])}" if p.get("affiliation") else ""
        shot = d.headshots.get(pid)
        pic = figure(d, shot, f"headshot of {pid}", "headshot") if shot else ""
        out.append(f'<div class="teller{" has-shot" if shot else ""}">{pic}<div class="tbody">'
                   f'<h4>{esc(p["name"])} <span class="id">{esc(pid)}</span></h4>'
                   f'<p class="role">{esc(roles)}{aff}; {len(ts)} telling{"s" if len(ts) != 1 else ""}</p>'
                   f'<ol class="tellings">{"".join(telling_html(d, s, t) for t in ts)}</ol></div></div>')
    return f'<section><h3>Tellings, by teller</h3>{"".join(out)}</section>'


def discussion_html(d: Data, s: dict) -> str:
    entries = s.get("discussion", [])
    if not entries:
        return '<section><h3>Discussion</h3><p class="none">No discussion entries.</p></section>'
    items = []
    for e in entries:
        who = esc(e["by"]) + (f", {esc(e['role'])}" if e.get("role") else "") + (f", {esc(e['date'])}" if e.get("date") else "")
        refs = []
        if e.get("source"):
            refs.append(link(e["source"], "Source"))
        if e.get("episode"):
            ep = d.episode(e["episode"], f"story {s['id']} discussion")
            refs.append(link(url_at(ep, seconds(e["time"])) if e.get("time") else ep.get("url"),
                             f'{esc(ep.get("show"))}, &ldquo;{esc(ep.get("title"))}&rdquo;' + (f" at {esc(e['time'])}" if e.get("time") else "")))
        items.append(f'<li><p class="src"><span class="chip dk-{esc(e["kind"])}">{esc(e["kind"])}</span> {who}</p>'
                     f'<p class="dtext">{esc(e["text"])}</p>' + (f'<p class="refs">{" &middot; ".join(refs)}</p>' if refs else "") + "</li>")
    return f'<section><h3>Discussion</h3><ul class="discussion">{"".join(items)}</ul></section>'


def comment_html(sid: str, label: str, rating: bool = True) -> str:
    scale = ""
    if rating:
        opts = "".join(f'<label for="rating-{esc(sid)}-{n}"><input type="radio" id="rating-{esc(sid)}-{n}" name="rating-{esc(sid)}" '
                       f'value="{n}" data-story="{esc(sid)}"><span>{n}</span></label>' for n in range(1, 11))
        scale = f'<div class="scale" role="radiogroup" aria-label="Rating for {esc(sid)}, 1 to 10">{opts}</div>'
    return (f'<fieldset class="comment" data-story="{esc(sid)}"><legend>{label} <span class="id">{esc(sid)}</span></legend>'
            f'{scale}<textarea id="note-{esc(sid)}" data-story="{esc(sid)}" rows="4" '
            f'aria-label="Note on {esc(sid)}" placeholder="What you notice"></textarea>'
            f'<p class="status" id="status-{esc(sid)}" aria-live="polite"></p></fieldset>')


def story_html(d: Data, sid: str) -> str:
    s = d.stories[sid]
    era = d.eras.get(s["era"], {}).get("name") if s.get("era") else None
    if s.get("era") and era is None:
        raise SystemExit(f"review: story {sid} names era {s['era']!r}, which data/eras.json does not hold")
    place = None
    if s.get("place"):
        if s["place"] not in d.places:
            raise SystemExit(f"review: story {sid} names place {s['place']!r}, which data/places.json does not hold")
        place = d.places[s["place"]]["name"]
    where = [esc(years_text(s.get("years"))), esc(era) if era else "no era",
             esc(place) if place else (f"unplaced: {esc(s['place_text'])}" if s.get("place_text") else "no place"),
             esc(s.get("kind"))]
    pics = "".join(figure(d, b, f"story {sid}") for b in d.story_images.get(sid, []))
    plain = (f'<div class="plain">{esc(s["plain"])}</div>' + (' <p class="by">Plain telling written by hand.</p>' if s.get("plain_by") == "hand" else "")
             if s.get("plain") else '<p class="none">No plain telling yet (pipeline.explain has not run on this story).</p>')
    n_open = d.notes_open.get(sid, 0)
    return (f'<article class="story" id="{esc(sid)}"><header><h2>{esc(s["title"])}</h2>'
            f'<p class="where">{" &middot; ".join(where)}</p><p class="id">{esc(sid)}</p></header>'
            f'{score_block(d, s)}<section class="plain-wrap" aria-label="Plain telling">{plain}</section>'
            + (f'<section class="pics" aria-label="Pictures">{pics}</section>' if pics else '<p class="none">No pictures for this story.</p>')
            + tellings_html(d, s) + discussion_html(d, s)
            + f'<p class="notes-open">Open viewer notes: {n_open}</p>'
            + comment_html(sid, "Your review of") + "</article>")


CSS = """
:root{--bg:#fbfaf7;--fg:#1f1d1a;--muted:#6b665e;--rule:#e2ded6;--field:#ffffff;--field-line:#c9c3b8;
--accent:#9a3b1e;--accent-fg:#ffffff;--quote-line:#d8c7b8;--chip-fg:#1f1d1a;
--tier-well:#cfe6d4;--tier-several:#f2e2bd;--tier-once:#e6e3dd;--dk-debunk:#f2d3cc;--dk-rebunk:#d4e0f2;--dk-note:#e6e3dd;--dk-source:#e4dcf0;
--ok:#2f6b3a;--warn:#9a3b1e;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--bg:#171614;--fg:#e9e5dd;--muted:#a19a8e;--rule:#34312c;--field:#201f1c;--field-line:#4a463f;
--accent:#e58a63;--accent-fg:#171614;--quote-line:#5a4a3e;--chip-fg:#e9e5dd;
--tier-well:#28452f;--tier-several:#4d4224;--tier-once:#35322d;--dk-debunk:#552f27;--dk-rebunk:#2b3a52;--dk-note:#35322d;--dk-source:#3e3350;
--ok:#8fcf9b;--warn:#e58a63;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#171614;--fg:#e9e5dd;--muted:#a19a8e;--rule:#34312c;--field:#201f1c;--field-line:#4a463f;
--accent:#e58a63;--accent-fg:#171614;--quote-line:#5a4a3e;--chip-fg:#e9e5dd;
--tier-well:#28452f;--tier-several:#4d4224;--tier-once:#35322d;--dk-debunk:#552f27;--dk-rebunk:#2b3a52;--dk-note:#35322d;--dk-source:#3e3350;
--ok:#8fcf9b;--warn:#e58a63;color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
.page{max-width:46rem;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));padding-block:32px 64px}
.serif,.plain,blockquote,.dtext,h1,h2{font-family:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
h1{font-size:2rem;line-height:1.15;margin:0 0 .5rem;font-weight:600}
h2{font-size:1.55rem;line-height:1.2;margin:0;font-weight:600}
h3{font-size:.78rem;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);margin:2rem 0 .75rem;font-weight:600}
h4{font-size:1rem;margin:0}
p{margin:.4rem 0}
a{color:var(--accent);text-underline-offset:2px}
.lede{font-size:1.05rem;max-width:65ch}
.how{color:var(--muted);max-width:65ch}
.mode{font-size:.85rem;color:var(--muted);border-left:3px solid var(--accent);padding:.2rem .7rem;margin:1rem 0}
nav.toc{margin:1.5rem 0 0;padding:0;border-top:1px solid var(--rule)}
nav.toc ol{margin:.75rem 0 0;padding-left:1.4rem}
nav.toc li{margin:.2rem 0}
.id{font:12px/1.3 ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);word-break:break-all}
.story{border-top:2px solid var(--fg);margin-top:3.5rem;padding-top:1.25rem}
.where{color:var(--muted);margin:.35rem 0 .1rem}
.chip{display:inline-block;font-size:.75rem;line-height:1.5;padding:0 .5rem;border-radius:999px;background:var(--tier-once);color:var(--chip-fg);white-space:nowrap}
.tier-well{background:var(--tier-well)}.tier-several{background:var(--tier-several)}.tier-once{background:var(--tier-once)}
.dk-debunk{background:var(--dk-debunk)}.dk-rebunk{background:var(--dk-rebunk)}.dk-note{background:var(--dk-note)}.dk-source{background:var(--dk-source)}
.scored dl{display:grid;grid-template-columns:repeat(auto-fill,minmax(10.5rem,1fr));gap:.35rem 1rem;margin:0;font-size:.85rem}
.scored dl>div,.scored dt,.scored dd{min-width:0}
.scored dt{color:var(--muted);font-size:.75rem;margin:0}
.scored dd{margin:0 0 .3rem}
.scored dl{grid-auto-flow:row}
.plain{font-size:1.15rem;line-height:1.6;max-width:65ch;margin-top:1.5rem}
.by,.none,.notes-open{color:var(--muted);font-size:.85rem}
.pics{display:flex;flex-direction:column;gap:1.25rem;margin-top:1.5rem}
figure{margin:0;min-width:0}
figure img{max-width:100%;max-height:30rem;width:auto;height:auto;display:block;border-radius:2px}
figcaption{font-size:.82rem;margin-top:.4rem;max-width:65ch}
figcaption .meta{color:var(--muted)}
.teller{border-top:1px solid var(--rule);padding:1rem 0 .25rem}
.teller.has-shot{display:grid;grid-template-columns:72px minmax(0,1fr);gap:1rem;align-items:start}
.tbody{min-width:0}
.headshot img{width:72px;height:auto}
.headshot figcaption{font-size:.65rem;line-height:1.3}
.headshot figcaption .cap{display:none}
.role{color:var(--muted);font-size:.85rem;margin:.1rem 0 .5rem}
ol.tellings{list-style:none;padding:0;margin:0}
.telling{margin:0 0 1.1rem}
.src{font-size:.82rem;color:var(--muted);margin:0}
.kind{display:inline-block;font-size:.72rem;border:1px solid var(--rule);border-radius:3px;padding:0 .3rem;margin-left:.25rem;color:var(--muted)}
blockquote{margin:.35rem 0 .35rem;padding-left:.9rem;border-left:3px solid var(--quote-line);font-size:1.05rem;line-height:1.55;max-width:65ch}
dl.tmeta{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:.15rem .75rem;font-size:.82rem;margin:.35rem 0 0;max-width:65ch}
dl.tmeta dt{color:var(--muted)}
dl.tmeta dd{margin:0;min-width:0}
ul.discussion{list-style:none;padding:0;margin:0}
ul.discussion li{margin:0 0 1rem}
.dtext{font-size:1.02rem;max-width:65ch;margin:.25rem 0}
.refs{font-size:.82rem}
fieldset.comment{border:1px solid var(--field-line);border-radius:6px;padding:1rem;margin:2rem 0 0;background:var(--field);min-width:0}
legend{font-weight:600;padding:0 .4rem}
.scale{display:flex;flex-wrap:wrap;gap:.35rem;margin:.25rem 0 .75rem}
.scale label{position:relative;cursor:pointer}
.scale input{position:absolute;opacity:0;width:1px;height:1px}
.scale span{display:inline-flex;align-items:center;justify-content:center;width:2.25rem;height:2.25rem;border:1px solid var(--field-line);border-radius:4px;font-variant-numeric:tabular-nums;background:var(--bg)}
.scale input:checked+span{background:var(--accent);color:var(--accent-fg);border-color:var(--accent);font-weight:600}
.scale input:focus-visible+span{outline:2px solid var(--accent);outline-offset:2px}
textarea{width:100%;font:inherit;font-size:1rem;color:var(--fg);background:var(--bg);border:1px solid var(--field-line);border-radius:4px;padding:.6rem;resize:vertical}
textarea:focus{outline:2px solid var(--accent);outline-offset:1px}
.status{font-size:.78rem;color:var(--muted);min-height:1.2em;margin:.35rem 0 0}
.status.ok{color:var(--ok)}.status.err{color:var(--warn)}
.general{margin-top:3.5rem;border-top:2px solid var(--fg);padding-top:1rem}
.actions{margin-top:1.5rem;display:flex;flex-wrap:wrap;gap:.75rem;align-items:center}
button{font:inherit;font-weight:600;background:var(--accent);color:var(--accent-fg);border:0;border-radius:4px;padding:.55rem 1rem;cursor:pointer}
button:focus-visible{outline:2px solid var(--fg);outline-offset:2px}
#copy-msg{font-size:.85rem;color:var(--muted)}
#copy-fallback{margin-top:.75rem;font:12px/1.4 ui-monospace,Menlo,monospace}
"""

JS = r"""
(function () {
  const IDS = JSON.parse(document.getElementById('review-ids').textContent);
  const TITLE = JSON.parse(document.getElementById('review-title').textContent);
  const ALL = IDS.concat(['general']);
  const LS_KEY = 'nhi-review:' + TITLE;
  const savers = {};
  ALL.forEach(function (sid) { savers[sid] = { timer: null, inflight: false, again: false, written: null, touched: false, retried: false }; });
  let db = null;
  let resolveReady;
  const ready = new Promise(function (r) { resolveReady = r; });

  function noteEl(sid) { return document.getElementById('note-' + sid); }
  function current(sid) {
    const r = document.querySelector('input[name="rating-' + CSS.escape(sid) + '"]:checked');
    return { rating: r ? Number(r.value) : null, note: noteEl(sid).value };
  }
  function fill(sid, v) {
    if (v.rating != null) {
      const r = document.getElementById('rating-' + sid + '-' + v.rating);
      if (r) r.checked = true;
    }
    if (typeof v.note === 'string') noteEl(sid).value = v.note;
  }
  function setStatus(sid, text, cls) {
    const el = document.getElementById('status-' + sid);
    if (!el) return;
    el.textContent = text;
    el.className = 'status' + (cls ? ' ' + cls : '');
  }
  function lsRead() {
    try { return JSON.parse(localStorage.getItem(LS_KEY) || '{}') || {}; } catch (e) { return {}; }
  }
  async function write(sid, v) {
    const body = { story: sid, rating: v.rating, note: v.note, at: new Date().toISOString() };
    if (db) { await db.collection('comments').doc(sid).set(body); return; }
    const all = lsRead();
    all[sid] = body;
    try { localStorage.setItem(LS_KEY, JSON.stringify(all)); }
    catch (e) { throw { code: 'local', message: 'this browser refused to store it; use Copy comments as text' }; }
  }
  async function flush(sid) {
    await ready;
    const s = savers[sid];
    if (s.inflight) { s.again = true; return; }
    const v = current(sid);
    const key = JSON.stringify(v);
    if (key === s.written) return;
    s.inflight = true;
    setStatus(sid, 'Saving');
    try {
      await write(sid, v);
      s.written = key; s.retried = false;
      setStatus(sid, db ? 'Saved' : 'Kept in this browser', 'ok');
    } catch (e) {
      const code = e && e.code;
      setStatus(sid, 'Not saved: ' + ((e && e.message) || String(e)), 'err');
      if ((code === 'unavailable' || !code) && !s.retried) {
        s.retried = true;
        setTimeout(function () { flush(sid); }, 800 + Math.random() * 1200);
      }
    } finally {
      s.inflight = false;
      if (s.again) { s.again = false; flush(sid); }
    }
  }
  function schedule(sid, delay) {
    const s = savers[sid];
    s.touched = true;
    clearTimeout(s.timer);
    s.timer = setTimeout(function () { flush(sid); }, delay);
  }
  document.addEventListener('input', function (ev) {
    const sid = ev.target && ev.target.dataset ? ev.target.dataset.story : null;
    if (!sid || !savers[sid]) return;
    schedule(sid, ev.target.type === 'radio' ? 150 : 900);
  });
  document.addEventListener('change', function (ev) {
    const sid = ev.target && ev.target.dataset ? ev.target.dataset.story : null;
    if (!sid || !savers[sid] || ev.target.type !== 'radio') return;
    schedule(sid, 150);
  });

  async function start() {
    const mode = document.getElementById('save-mode');
    try {
      db = (window.claude && typeof window.claude.use === 'function') ? await window.claude.use('db') : null;
    } catch (e) { db = null; }
    if (db) {
      mode.textContent = 'Comments are saved to this page as you type, where the review is read back.';
      await Promise.all(ALL.map(async function (sid) {
        try {
          const snap = await db.collection('comments').doc(sid).get();
          if (snap.exists && !savers[sid].touched) {
            const v = snap.data();
            fill(sid, v);
            savers[sid].written = JSON.stringify(current(sid));
            if (v.at) setStatus(sid, 'Saved ' + String(v.at).slice(0, 16).replace('T', ' '), 'ok');
          }
        } catch (e) {
          setStatus(sid, 'Could not read the saved comment: ' + ((e && e.message) || String(e)), 'err');
        }
      }));
    } else {
      mode.textContent = 'Comments are kept in this browser only; use Copy comments as text to send them.';
      const all = lsRead();
      ALL.forEach(function (sid) {
        if (all[sid] && !savers[sid].touched) {
          fill(sid, all[sid]);
          savers[sid].written = JSON.stringify(current(sid));
        }
      });
    }
    resolveReady();
  }
  start();

  function stamp() {
    const d = new Date();
    const p = function (n) { return String(n).padStart(2, '0'); };
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' + p(d.getHours()) + ':' + p(d.getMinutes());
  }
  function markdown() {
    const lines = [];
    ALL.forEach(function (sid) {
      const v = current(sid);
      const note = v.note.replace(/\s+/g, ' ').trim();
      if (v.rating == null && !note) return;
      let line = sid + '.';
      if (sid !== 'general') line += v.rating == null ? ' Rating none.' : ' Rating ' + v.rating + '/10.';
      line += ' Note: ' + (note || 'none');
      lines.push(line);
    });
    return '# Story review: ' + TITLE + ', ' + lines.length + ' comments, ' + stamp() + '\n\n' + lines.join('\n') + '\n';
  }
  const copyBtn = document.getElementById('copy-comments');
  const copyMsg = document.getElementById('copy-msg');
  const fallback = document.getElementById('copy-fallback');
  function showFallback(text) {
    fallback.value = text;
    fallback.hidden = false;
    fallback.focus();
    fallback.select();
    copyMsg.textContent = 'The clipboard was refused: the text is selected below, copy it with Cmd+C.';
  }
  copyBtn.addEventListener('click', function () {
    const text = markdown();
    fallback.hidden = true;
    try {
      if (!navigator.clipboard || !navigator.clipboard.writeText) { showFallback(text); return; }
      navigator.clipboard.writeText(text).then(function () {
        copyMsg.textContent = 'Copied.';
      }, function () { showFallback(text); });
    } catch (e) { showFallback(text); }
  });
})();
"""


def toc_item(d: Data, sid: str) -> str:
    return f'<li><a href="#{esc(sid)}">{esc(d.stories[sid]["title"])}</a></li>'


def ascii_page(text: str) -> str:
    """Every character past ASCII as a character reference, so the page reads the same whatever charset it is served with."""
    return text.encode("ascii", "xmlcharrefreplace").decode("ascii")


def page(d: Data, ids: list[str], title: str, line: str, blocks: dict[str, str] | None = None) -> str:
    """The whole page; `blocks` the stories' rendered blocks when the caller has them already."""
    toc = "".join(toc_item(d, sid) for sid in ids)
    body = "".join(blocks[sid] if blocks is not None else story_html(d, sid) for sid in ids)
    ids_json = json.dumps(ids).replace("</", "<\\/")
    title_json = json.dumps(title).replace("</", "<\\/")
    return (f'<title>{esc(title)}</title>\n<meta name="claude:viewport-fit-sides" content="cover">\n'
            f'<style>{CSS}</style>\n'
            f'<main class="page"><header><h1>{esc(title)}</h1><p class="lede">{esc(line)}</p>'
            f'<p class="how">{esc(INSTRUCTIONS)}</p><p class="mode" id="save-mode">Connecting to the page\'s storage.</p>'
            f'<nav class="toc" aria-label="Stories"><ol>{toc}</ol></nav></header>'
            f'{body}'
            f'<section class="general"><h2>General comment</h2>{comment_html("general", "About the whole set", rating=False)}'
            f'<div class="actions"><button type="button" id="copy-comments" data-story="all">Copy comments as text</button>'
            f'<span id="copy-msg" aria-live="polite"></span></div>'
            f'<textarea id="copy-fallback" data-story="all" rows="8" hidden aria-label="Comments as text"></textarea></section></main>\n'
            f'<script type="application/json" id="review-ids">{ids_json}</script>\n'
            f'<script type="application/json" id="review-title">{title_json}</script>\n'
            f'<script>{JS}</script>\n')


def split_to_fit(d: Data, ids: list[str], blocks: dict[str, str], title: str, line: str) -> tuple[list[list[str]], list[str]]:
    """(the ids cut into lists whose pages each fit ARTIFACT_FILE_BYTES, walking the given order and cutting when
    the running size would pass the limit; the ids whose page alone would not fit). A story's size is its rendered
    block, its contents line and its place in the ids list; the rest of the page is measured with no story."""
    base = len(ascii_page(page(d, [], title, line, {})).encode("utf-8"))
    lists: list[list[str]] = []
    alone: list[str] = []
    run_size = base
    for sid in ids:
        n = len(ascii_page(blocks[sid] + toc_item(d, sid)).encode("utf-8")) + len(json.dumps(sid)) + 2
        if base + n > ARTIFACT_FILE_BYTES:
            alone.append(sid)
            continue
        if not lists or run_size + n > ARTIFACT_FILE_BYTES:
            lists.append([])
            run_size = base
        lists[-1].append(sid)
        run_size += n
    return lists, alone


def oversize_message(d: Data, ids: list[str], blocks: dict[str, str], title: str, line: str, size: int) -> str:
    lists, alone = split_to_fit(d, ids, blocks, title, line)
    msg = [f"review: the page would be {size:,} bytes, over the {ARTIFACT_FILE_BYTES:,} bytes a published artifact allows a file; "
           f"nothing is written. Split the stories into {len(lists)} pages that each fit, one review run per list:"]
    msg += [f"  {i}: {' '.join(ids_)}" for i, ids_ in enumerate(lists, 1)]
    if alone:
        msg.append(f"  too large for a page alone (its pictures): {' '.join(alone)}")
    return "\n".join(msg)


def run(root: Root, ids: list[str], out: Path, title: str, line: str) -> str:
    if not ids:
        raise SystemExit("review: name at least one story id")
    d = Data(root)
    resolved = []
    for sid in ids:
        r = d.story_id(sid)
        if r in resolved:
            raise SystemExit(f"review: story {r} named twice")
        resolved.append(r)
    blocks = {sid: story_html(d, sid) for sid in resolved}
    text = ascii_page(page(d, resolved, title, line, blocks))
    size = len(text.encode("utf-8"))
    if size > ARTIFACT_FILE_BYTES:
        raise SystemExit(oversize_message(d, resolved, blocks, title, line, size))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"review: {len(resolved)} stories -> {out} ({len(text.encode('utf-8')):,} bytes)", file=sys.stderr)
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stories", nargs="+", help="story ids (or aliases), in the order the page shows them")
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--name", default="Stories Review", help="the page's name, two to four words (the <title> and the heading)")
    ap.add_argument("--title", default="", help="one line on what the set is, under the heading")
    ap.add_argument("--root", default=REPO)
    a = ap.parse_args(argv)
    run(Root(a.root), a.stories, a.out.resolve(), a.name, a.title)
    return 0


if __name__ == "__main__":
    sys.exit(main())
