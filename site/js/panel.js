/* The story panel: what is told, by whom, where to hear it, how well it is attested at the reader's
   institutional trust, what it is linked to, the back and forth about it, and a box for notes.
   A story's photographs (objects and places) sit under the plain telling; a teller's headshot sits only
   beside that teller's own tellings, never as the story's picture.
   NHI.panel(C) returns { render(sid) }. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};

  NHI.panel = function (C) {
    const M = C.M, D = M.D, el = C.el;
    const body = document.getElementById("panel-body");
    const PROFILE_LABELS = { independent_tellers: ["independent teller", "independent tellers"], firsthand: ["first-hand", "first-hand"],
      official_records: ["official record", "official records"], official_conclusions: ["official conclusion", "official conclusions"],
      journalist: ["journalist", "journalists"], secondhand: ["second-hand", "second-hand"], researcher: ["researcher", "researchers"],
      host: ["host framing", "host framings"], documents: ["document told", "documents told"], credited_documents: ["document credited", "documents credited"],
      repetitions: ["repetition", "repetitions"] };
    const SHOWN = ["independent_tellers", "firsthand", "official_records", "official_conclusions", "journalist", "secondhand", "researcher", "host", "documents", "credited_documents", "repetitions"];
    const swatch = (color, cls) => { const s = el("span", { class: cls || "sw" }); s.style.background = color; return s; };
    const num = (label, value) => { const n = el("span", { class: "num" }); n.appendChild(document.createTextNode(label + " ")); n.appendChild(el("b", null, value)); return n; };

    const IMAGE_KINDS = { "object": "object", "place-then": "the place then", "place-now": "the place today" };
    const creditText = x => x.credit + ", " + x.licence + (x.licence_kind === "fair-use" ? ", fair use" : "");
    const headshotOf = id => (D.people[id] && D.people[id].image) || null;

    function imageStrip(s) {
      const strip = el("div", { class: "imgstrip" + (s.images.length === 1 ? " one" : "") });
      s.images.forEach(x => {
        const fig = el("figure", { class: "img" + (x.licence_kind === "fair-use" ? " fair" : "") });
        const open = el("a", { href: x.file, target: "_blank", rel: "noopener", title: "open the image" });
        open.appendChild(el("img", { src: x.file, alt: x.caption, loading: "lazy" }));
        fig.appendChild(open);
        const cap = el("figcaption");
        const kindText = x.kind === "person" ? (D.people[x.person] ? D.people[x.person].name : x.person) : IMAGE_KINDS[x.kind];
        cap.appendChild(el("span", { class: "ik" }, kindText + (x.date ? ", " + x.date : "")));
        cap.appendChild(document.createTextNode(" " + x.caption));
        fig.appendChild(cap);
        const cr = el("div", { class: "credit" });
        cr.appendChild(el("a", { href: x.source, target: "_blank", rel: "noopener" }, creditText(x)));
        fig.appendChild(cr);
        strip.appendChild(fig);
      });
      return strip;
    }

    function headshot(id, name) {
      const x = headshotOf(id);
      if (!x) return null;
      const a = el("a", { class: "headshot", href: x.source, target: "_blank", rel: "noopener", title: name + ". Photograph: " + creditText(x) });
      a.appendChild(el("img", { src: x.file, alt: "Photograph of " + name, loading: "lazy" }));
      return a;
    }

    function relRow(sid, note, warn) {
      const o = M.storyById[sid];
      const b = el("button", { class: "rel", type: "button" });
      b.appendChild(swatch(M.KIND_COLORS[o.kind]));
      b.appendChild(el("span", { class: "t" }, o.title));
      if (note) b.appendChild(el("span", { class: "r" + (warn ? " warn" : "") }, note));
      b.appendChild(el("span", { class: "s" }, M.yearsText(o.years) + " · " + M.TIERS[o._tier].name));
      b.addEventListener("click", () => C.select(sid, { fly: true }));
      b.addEventListener("mouseenter", () => C.preview(sid));
      b.addEventListener("mouseleave", () => C.preview(null));
      return b;
    }

    function evidence(s) {
      const p = s.profile, box = el("div", { class: "evidence" });
      const top = el("div", { class: "ev-top" });
      top.appendChild(el("span", { class: "tierpill t" + s._tier }, M.TIERS[s._tier].name));
      top.appendChild(num("score", s._score.toFixed(2)));
      top.appendChild(num("attestation", s._att.toFixed(2)));
      if (p.strongest_kind) top.appendChild(num("strongest", M.TELLING_KINDS[p.strongest_kind] || String(p.strongest_kind).replace(/_/g, " ")));
      box.appendChild(top);
      // the score on the log scale, 1.0 is the corpus median at this knob
      const lo = Math.log(M.S_MIN), span = Math.log(M.S_MAX) - lo, at = v => (Math.min(1, Math.max(0, (Math.log(v) - lo) / span)) * 100) + "%";
      const wrap = el("div", { class: "scorebar-wrap" }), bar = el("div", { class: "scorebar" });
      wrap.appendChild(bar);
      const med = el("div", { class: "med", title: "1.0: as well attested as the typical story in this corpus" }); med.style.left = at(1); wrap.appendChild(med);
      const mk = el("div", { class: "mk", title: "score " + s._score.toFixed(2) }); mk.style.left = at(Math.max(M.S_MIN, s._score)); wrap.appendChild(mk);
      const ticks = el("div", { class: "ticks" }); ["0.2", "1, the median", "10"].forEach(t => ticks.appendChild(el("span", null, t))); wrap.appendChild(ticks);
      box.appendChild(wrap);
      const grid = el("div", { class: "ev-grid" });
      SHOWN.forEach(k => {
        const v = p[k];
        if (v === 0 && k !== "independent_tellers" && k !== "documents") return;
        const c = el("span", { class: "c" + (v === 0 ? " zero" : "") });
        c.appendChild(el("b", null, String(v))); c.appendChild(document.createTextNode(PROFILE_LABELS[k][v === 1 ? 0 : 1]));
        grid.appendChild(c);
      });
      if (p.contradicted) grid.appendChild(el("span", { class: "c warn" }, "contradicted by another story"));
      box.appendChild(grid);
      const t = M.trust.value;
      box.appendChild(el("div", { class: "ev-src" }, "At institutional trust " + t.toFixed(2) + " an official teller weighs " + (D.scoring.weights.official * t).toFixed(2) +
        "; the corpus median attestation is " + M.median.toFixed(2) + ". The score counts tellers and documents; it does not judge truth."));
      return box;
    }

    function telling(s, t) {
      const box = el("div", { class: "telling" });
      const who = el("div", { class: "who" });
      const name = t.teller_name || M.personName(t.teller);
      const face = headshot(t.teller, name);
      if (face) who.appendChild(face);
      who.appendChild(el("b", null, name));
      who.appendChild(el("span", { class: "badge" }, M.TELLING_KINDS[t.kind] || t.kind));
      if (t.repetition) who.appendChild(el("span", { class: "badge" }, "repetition"));
      const n = s.shared_teller_by && s.shared_teller_by[t.teller];
      if (n) who.appendChild(el("span", { class: "badge", title: "a shared teller is a count, never a link" }, "also told by this teller: " + n + (n === 1 ? " story" : " stories")));
      box.appendChild(who);
      box.appendChild(el("blockquote", null, "“" + t.quote + "”"));
      const src = el("div", { class: "src" });
      if (t.episode) {
        const ep = D.episodes[t.episode] || {};
        src.appendChild(el("a", { href: M.youtube(t.episode, t.from_s), target: "_blank", rel: "noopener" }, "watch at " + M.hms(t.from_s)));
        const show = t.show || ep.show, title = t.episode_title || ep.title || t.episode;
        src.appendChild(document.createTextNode(" " + (show ? show + ": " : "") + title + (t.published || ep.published ? ", " + (t.published || ep.published) : "")));
      } else {
        const doc = (s.documents || []).find(x => x.id === t.document);
        src.appendChild(document.createTextNode("Document: " + (doc ? doc.title : M.docTitle.get(t.document) || t.document) + (t.page ? ", page " + t.page : "")));
        if (doc && doc.url) { src.appendChild(document.createTextNode(" ")); src.appendChild(el("a", { href: doc.url, target: "_blank", rel: "noopener" }, "open")); }
      }
      box.appendChild(src);
      if (t.repeats.length) box.appendChild(el("div", { class: "cites" }, "repeats " + t.repeats.map(M.personName).join(", ")));
      const cited = t.cites.filter(c => !t.repeats.includes(c));
      if (cited.length) box.appendChild(el("div", { class: "cites" }, "cites " + cited.map(M.personName).join(", ")));
      if ((t.documents || []).length) box.appendChild(el("div", { class: "cites" }, "credits " + t.documents.map(x => M.docTitle.get(x) || x).join(", ")));
      if (t.difference) box.appendChild(el("div", { class: "cites" }, "told differently: " + t.difference));
      return box;
    }

    function discussion(s) {
      const wrap = el("div", { class: "thread" });
      s.discussion.forEach(x => {
        const item = el("div", { class: "turn " + x.kind });
        const head = el("div", { class: "who" });
        head.appendChild(el("span", { class: "dk " + x.kind }, x.kind));
        head.appendChild(el("b", null, x.by));
        if (x.role) head.appendChild(el("span", { class: "badge" }, x.role));
        if (x.date) head.appendChild(el("span", { class: "when" }, x.date));
        item.appendChild(head);
        item.appendChild(el("p", null, x.text));
        const links = el("div", { class: "src" });
        if (x.source) links.appendChild(el("a", { href: x.source, target: "_blank", rel: "noopener" }, "source"));
        if (x.episode) {
          const ep = D.episodes[x.episode] || {};
          if (links.childNodes.length) links.appendChild(document.createTextNode(" · "));
          if (x.url) links.appendChild(el("a", { href: x.url, target: "_blank", rel: "noopener" }, "watch" + (x.time ? " at " + x.time : "")));
          else links.appendChild(document.createTextNode("episode " + x.episode + (x.time ? " at " + x.time : "")));
          if (ep.show || ep.title) links.appendChild(document.createTextNode(" " + [ep.show, ep.title].filter(Boolean).join(": ")));
        }
        if (links.childNodes.length) item.appendChild(links);
        wrap.appendChild(item);
      });
      return wrap;
    }

    function render(sid) {
      const s = M.storyById[sid];
      const keepScroll = body.dataset.sid === sid ? document.getElementById("panel").scrollTop : 0;
      body.dataset.sid = sid;
      body.innerHTML = "";
      const tag = el("div", { class: "kindtag" });
      tag.appendChild(swatch(M.KIND_COLORS[s.kind])); tag.appendChild(el("span", null, M.KIND_NAMES[s.kind]));
      tag.appendChild(el("span", { class: "tierpill t" + s._tier }, M.TIERS[s._tier].name));
      if (s.notes_open) tag.appendChild(el("span", { class: "notebadge", title: "notes viewers left that are not yet read into the data" }, s.notes_open + (s.notes_open === 1 ? " open note" : " open notes")));
      body.appendChild(tag);
      body.appendChild(el("h2", null, s.title));
      if (s.plain) body.appendChild(el("p", { class: "plain" }, s.plain));
      if ((s.images || []).length) body.appendChild(imageStrip(s));
      const dl = el("dl");
      const era = s.era ? M.eraById[s.era].era : null;
      [["Years", M.yearsText(s.years)], ["Era", era ? era.name + " (" + era.from + " to " + era.to + ")" : "no era"], ["Place", M.placeText(s)], ["Region", M.regionOf(s)]]
        .forEach(([k, v]) => { dl.appendChild(el("dt", null, k)); dl.appendChild(el("dd", null, v)); });
      body.appendChild(dl);

      body.appendChild(el("h3", null, "Evidence"));
      body.appendChild(evidence(s));

      body.appendChild(el("h3", null, "Tellings (" + s.tellings.length + ")"));
      s.tellings.forEach(t => body.appendChild(telling(s, t)));
      const by = s.shared_teller_by || {}, ids = Object.keys(by);
      if (ids.length > 1) {
        const p = el("p", { class: "group-h" }, "Also told by these tellers: " + ids.map(id => M.personName(id) + " " + by[id] + (by[id] === 1 ? " story" : " stories")).join(", ") + ".");
        body.appendChild(p);
      }
      const faces = [...new Set(s.tellings.map(t => t.teller))].filter(headshotOf);
      if (faces.length) {
        const p = el("p", { class: "group-h portraits" }, "Portraits beside the tellings: ");
        faces.forEach((id, i) => {
          const x = headshotOf(id);
          if (i) p.appendChild(document.createTextNode("; "));
          p.appendChild(document.createTextNode(M.personName(id) + ", "));
          p.appendChild(el("a", { href: x.source, target: "_blank", rel: "noopener" }, creditText(x)));
        });
        p.appendChild(document.createTextNode("."));
        body.appendChild(p);
      }

      if ((s.documents || []).length) {
        body.appendChild(el("h3", null, "Documents (" + s.documents.length + ")"));
        const ul = el("ul", { class: "docs" });
        s.documents.forEach(x => {
          const li = el("li");
          if (x.url) li.appendChild(el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.title || x.id)); else li.appendChild(el("span", null, x.title || x.id));
          if (x.date) li.appendChild(el("span", { class: "muted" }, " (" + x.date + ")"));
          ul.appendChild(li);
        });
        body.appendChild(ul);
      }

      const rel = M.linksOf(sid);
      body.appendChild(el("h3", null, "Linked stories (" + rel.length + ")"));
      if (!rel.length) body.appendChild(el("div", { class: "empty" }, "No same-event, variant, corroborating, contradicting or shared-document link yet."));
      rel.forEach(l => body.appendChild(relRow(l.other, l.relation.replace(/-/g, " "), l.relation === "contradicts")));

      if (Array.isArray(s.discussion) && s.discussion.length) {
        body.appendChild(el("h3", null, "Back and forth (" + s.discussion.length + ")"));
        body.appendChild(el("p", { class: "hint" }, "These are tellings about the story, not a verdict."));
        body.appendChild(discussion(s));
      }

      const notesBox = el("div", { class: "notes" });
      body.appendChild(notesBox);
      NHI.notes.mount(notesBox, s, C);

      body.appendChild(el("p", { class: "disclaim" }, "Stories, not facts: this page records who tells what, and where (corpus of " + (D.corpus_date || "no date") + "). Nothing here is asserted true."));
      document.getElementById("panel").scrollTop = keepScroll;
    }
    return { render };
  };
})();
