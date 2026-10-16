/* Notes viewers leave on a story. On the published page with the db capability a note is saved to the
   collection "notes" as { story, by, date, text, status: "open" } and the story's open notes are listed;
   anywhere else (from disk, over local http) the note is copied as text for pasting into the chat. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};
  let dbPromise = null, unsubscribe = null, dbWhy = "";   // dbWhy: why this view has no db, when the runtime said
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
  function remembered() { try { return localStorage.getItem("nhi-note-name") || ""; } catch (e) { return ""; } }
  function remember(name) { try { localStorage.setItem("nhi-note-name", name); } catch (e) { /* no storage: the name is asked again */ } }

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

  function mount(box, s, C) {
    const el = C.el;
    if (unsubscribe) { unsubscribe(); unsubscribe = null; }
    box.appendChild(el("h3", null, "Notes"));
    const hint = el("p", { class: "hint" }, "Leave a note on this story: a source, a correction, another telling.");
    box.appendChild(hint);
    const form = el("form", { class: "noteform" });
    const name = el("input", { type: "text", placeholder: "Your name", "aria-label": "Your name", maxlength: "80" });
    name.value = remembered();
    const text = el("textarea", { rows: "3", placeholder: "Your note", "aria-label": "Your note", maxlength: "2000" });
    const btn = el("button", { class: "btn", type: "submit" }, "Copy note");
    const status = el("p", { class: "notestatus", "aria-live": "polite" });
    const manual = el("pre", { class: "manual" }); manual.hidden = true;
    form.appendChild(name); form.appendChild(text); form.appendChild(btn);
    box.appendChild(form); box.appendChild(status); box.appendChild(manual);
    const list = el("ul", { class: "notelist" });
    box.appendChild(list);
    let store = null;
    const local = "This copy of the page cannot save notes: the button copies the note as text, to paste back into the chat.";
    status.textContent = local;

    function asText(n) { return "story: " + n.story + "\nname: " + n.by + "\ndate: " + n.date + "\nnote: " + n.text; }
    function copyOut(n, why) {
      return copy(asText(n)).then(ok => {
        if (ok) { status.textContent = why + " The note is copied: paste it into the chat."; manual.hidden = true; text.value = ""; }
        else { status.textContent = why + " The clipboard refused; copy the note below by hand."; manual.textContent = asText(n); manual.hidden = false; }
      });
    }
    form.addEventListener("submit", e => {
      e.preventDefault();
      const n = { story: s.id, by: name.value.trim(), date: today(), text: text.value.trim(), status: "open" };
      if (!n.by || !n.text) { status.textContent = "A note needs your name and some text."; return; }
      remember(n.by);
      if (!store) { copyOut(n, ""); return; }
      btn.disabled = true;
      store.collection("notes").add(n).then(() => { text.value = ""; status.textContent = "Saved. A person reads open notes into the data later."; },
        err => copyOut(n, "The note could not be saved here (" + ((err && err.code) || "error") + ")."))
        .then(() => { btn.disabled = false; });
    });

    db().then(d => {
      if (!box.isConnected) return;
      if (!d) { if (dbWhy) status.textContent = "Notes cannot be saved here (" + dbWhy + "): the button copies the note as text, to paste back into the chat."; return; }
      store = d;
      btn.textContent = "Save note";
      status.textContent = "Notes are saved with this page and read by a person before anything changes in the data.";
      unsubscribe = d.collection("notes").where("story", "==", s.id).where("status", "==", "open").onSnapshot(snap => {
        list.innerHTML = "";
        const docs = snap.docs.map(x => x.data()).filter(Boolean).sort((a, b) => String(a.date).localeCompare(String(b.date)));
        if (!docs.length) { list.appendChild(el("li", { class: "empty" }, "No open notes on this story yet.")); return; }
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
  }
  NHI.notes = { mount };
})();
