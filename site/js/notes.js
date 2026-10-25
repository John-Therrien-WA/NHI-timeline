/* Notes viewers leave, in two boxes that share one form: on a story (the panel's Notes) and on the page as a whole
   (the About overlay). On the published page with the db capability a story note is saved to the collection
   "notes" as { story, by, date, text, status: "open" } and a page note to the collection "feedback" as
   { by, date, text, status: "open", where }, and each box lists its open notes; anywhere else (from disk, over
   local http) the note is copied as text for pasting into the chat. The name is remembered once for both boxes. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};
  let dbPromise = null, dbWhy = "";   // dbWhy: why this view has no db, when the runtime said
  function db() {
    if (!dbPromise) {
      const c = window.claude;
      dbPromise = c && typeof c.use === "function"
        ? Promise.resolve(c.use("db")).catch(e => { dbWhy = (e && (e.code || e.message)) || String(e); return null; })
        : Promise.resolve(null);
    }
    return dbPromise;
  }
  function today() { return new Date().toISOString().slice(0, 10); }
  const NAME_KEY = "nhi-note-name";
  function remembered() { try { return localStorage.getItem(NAME_KEY) || ""; } catch (e) { return ""; } }
  function remember(name) { try { localStorage.setItem(NAME_KEY, name); } catch (e) { /* no storage: the name is asked again */ } }

  // the clipboard, then the old copy command, then the text shown to copy by hand
  function copy(text) {
    const legacy = () => {
      const ta = document.createElement("textarea"); ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      let ok = false; try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
      ta.remove(); return ok;
    };
    if (navigator.clipboard && navigator.clipboard.writeText) return navigator.clipboard.writeText(text).then(() => true, () => legacy());
    return Promise.resolve(legacy());
  }

  /* One notes box. spec: { el, title, hint, collection, fields() (the note's own fields beside by, date, text,
     status), asText(note), query(collection) (the open notes this box lists), empty (the empty list's line) }.
     Returns stop(), which ends the box's live list. */
  function box(root, spec) {
    const el = spec.el;
    let stopped = false, unsubscribe = null;
    if (spec.title) root.appendChild(el("h3", null, spec.title));
    root.appendChild(el("p", { class: "hint" }, spec.hint));
    const form = el("form", { class: "noteform" });
    const name = el("input", { type: "text", placeholder: "Your name", "aria-label": "Your name", maxlength: "80" });
    name.value = remembered();
    const text = el("textarea", { rows: "3", placeholder: "Your note", "aria-label": "Your note", maxlength: "2000" });
    const btn = el("button", { class: "btn", type: "submit" }, "Copy note");
    const status = el("p", { class: "notestatus", "aria-live": "polite" });
    const manual = el("pre", { class: "manual" }); manual.hidden = true;
    form.appendChild(name); form.appendChild(text); form.appendChild(btn);
    root.appendChild(form); root.appendChild(status); root.appendChild(manual);
    const list = el("ul", { class: "notelist" });
    root.appendChild(list);
    let store = null;
    status.textContent = "This copy of the page cannot save notes: the button copies the note as text, to paste back into the chat.";

    function copyOut(n, why) {
      const t = spec.asText(n);
      return copy(t).then(ok => {
        if (ok) { status.textContent = (why ? why + " " : "") + "The note is copied: paste it into the chat."; manual.hidden = true; text.value = ""; }
        else { status.textContent = (why ? why + " " : "") + "The clipboard refused; copy the note below by hand."; manual.textContent = t; manual.hidden = false; }
      });
    }
    form.addEventListener("submit", e => {
      e.preventDefault();
      const n = Object.assign(spec.fields(), { by: name.value.trim(), date: today(), text: text.value.trim(), status: "open" });
      if (!n.by || !n.text) { status.textContent = "A note needs your name and some text."; return; }
      remember(n.by);
      if (!store) { copyOut(n, ""); return; }
      btn.disabled = true;
      store.collection(spec.collection).add(n).then(() => { text.value = ""; status.textContent = "Saved. A person reads the open notes before anything changes."; },
        err => copyOut(n, "The note could not be saved here (" + ((err && err.code) || "error") + ")."))
        .then(() => { btn.disabled = false; });
    });
    // the name typed in one box is the name in the other when it is next drawn
    name.addEventListener("change", () => { if (name.value.trim()) remember(name.value.trim()); });
    form.addEventListener("focusin", () => { if (!name.value) name.value = remembered(); });

    db().then(d => {
      if (stopped || !root.isConnected) return;
      if (!d) { if (dbWhy) status.textContent = "Notes cannot be saved here (" + dbWhy + "): the button copies the note as text, to paste back into the chat."; return; }
      store = d;
      btn.textContent = "Save note";
      status.textContent = "Notes are saved with this page and read by a person before anything changes.";
      unsubscribe = spec.query(d.collection(spec.collection)).onSnapshot(snap => {
        list.innerHTML = "";
        const docs = snap.docs.map(x => x.data()).filter(Boolean).sort((a, b) => String(a.date).localeCompare(String(b.date)));
        if (!docs.length) { list.appendChild(el("li", { class: "empty" }, spec.empty)); return; }
        docs.forEach(n => {
          const li = el("li");
          const head = el("div", { class: "who" });
          head.appendChild(el("b", null, String(n.by || "someone")));
          head.appendChild(el("span", { class: "when" }, String(n.date || "")));
          li.appendChild(head);
          li.appendChild(el("p", null, String(n.text || "")));
          list.appendChild(li);
        });
      }, err => { list.innerHTML = ""; list.appendChild(el("li", { class: "empty" }, "The notes could not be read (" + ((err && err.code) || "error") + ").")); });
    });
    return () => { stopped = true; if (unsubscribe) { unsubscribe(); unsubscribe = null; } };
  }

  // the story panel's box: one at a time, the last one's live list ended when the panel draws the next
  let stopStory = null;
  function mount(root, s, C) {
    if (stopStory) { stopStory(); stopStory = null; }
    stopStory = box(root, {
      el: C.el, title: "Notes", collection: "notes",
      hint: "Leave a note on this story: a source, a correction, another telling, or what you think of it.",
      fields: () => ({ story: s.id }),
      asText: n => "story: " + n.story + "\nname: " + n.by + "\ndate: " + n.date + "\nnote: " + n.text,
      query: col => col.where("story", "==", s.id).where("status", "==", "open"),
      empty: "No open notes on this story yet.",
    });
  }

  // the page's box, in the About overlay; where() names the view the reader is in
  function mountPage(root, C, where) {
    return box(root, {
      el: C.el, title: null, collection: "feedback",
      hint: "On the page as a whole: what is unclear, what is missing, what works.",
      fields: () => ({ where: where() }),
      asText: n => "page note\nname: " + n.by + "\ndate: " + n.date + "\nwhere: " + n.where + "\nnote: " + n.text,
      query: col => col.where("status", "==", "open"),
      empty: "No open notes on the page yet.",
    });
  }
  NHI.notes = { mount, mountPage };
})();
