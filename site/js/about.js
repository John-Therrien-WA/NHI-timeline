/* The About overlay: what the page is, how to read it, how to move, how to leave a note, and a box for notes on
   the page as a whole. Shown on a reader's first visit (remembered in localStorage as "nhi-about-seen"; without
   storage it shows on every visit), reopened by the About button, closed by Close, Escape or a click outside the
   card. While it is open the controller passes no key to the scene. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};
  const SEEN_KEY = "nhi-about-seen";
  function seen() { try { return localStorage.getItem(SEEN_KEY) === "1"; } catch (e) { return false; } }
  function markSeen() { try { localStorage.setItem(SEEN_KEY, "1"); } catch (e) { /* no storage: shown again next visit */ } }

  /* opts: { start: "open" | "closed" | "first" (open unless seen), where() the reader's view, onOpen() } */
  function about(C, opts) {
    const layer = document.getElementById("about"), card = document.getElementById("about-card");
    // the facts that have a home elsewhere are read from it: the episode count from the data, the tiers from the model
    document.getElementById("about-episodes").textContent = String(Object.keys(C.D.episodes).length);
    const tiers = document.getElementById("about-tiers");
    C.M.TIERS.forEach(T => { const li = C.el("li"); li.appendChild(C.el("b", null, T.name)); li.appendChild(document.createTextNode(": " + T.rule + ".")); tiers.appendChild(li); });
    NHI.notes.mountPage(document.getElementById("about-notes"), C, opts.where);
    function isOpen() { return !layer.hidden; }
    // while the overlay is open the rest of the page is inert, so Tab and Shift+Tab stay inside the card
    let inerted = [];
    function open() {
      if (isOpen()) return;
      inerted = Array.from(document.body.children).filter(n => n !== layer && !n.inert);
      inerted.forEach(n => { n.inert = true; });
      layer.hidden = false; document.body.classList.add("about-open");
      card.scrollTop = 0; card.focus({ preventScroll: true });
      if (opts.onOpen) opts.onOpen();
    }
    function close() {
      if (!isOpen()) return;
      layer.hidden = true; document.body.classList.remove("about-open");
      inerted.forEach(n => { n.inert = false; }); inerted = [];
      markSeen();
    }
    document.getElementById("about-close").addEventListener("click", close);
    document.getElementById("btn-about").addEventListener("click", open);
    layer.addEventListener("click", e => { if (e.target === layer) close(); });
    if (opts.start === "open" || (opts.start === "first" && !seen())) open();
    return { open, close, isOpen };
  }
  NHI.about = about;
})();
