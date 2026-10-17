/* NHI timeline, the 3D page. The controller: it loads the data, builds the model, owns the selection,
   the story panel, the rails, the filters, the institutional-trust knob, search, the keys and the hash,
   and hands the drawing to one of two views, the corridor (default) and the globe.
   A classic script so the page also runs from disk; three.js comes in by dynamic import from the CDN. */
(function () {
  "use strict";
  const NHI = window.NHI;
  const $ = id => document.getElementById(id);

  // ---------- failing loud: the whole screen, never a quiet wrong page ----------
  function fatal(msg) {
    $("fatal-msg").textContent = String(msg);
    $("fatal").style.display = "flex";
    $("loading").hidden = true;
  }
  window.addEventListener("error", e => fatal(e.error ? (e.error.stack || e.error.message) : e.message));
  window.addEventListener("unhandledrejection", e => fatal((e.reason && (e.reason.stack || e.reason.message)) || e.reason));

  function el(tag, attrs, text) {
    const n = document.createElement(tag);
    if (attrs) for (const k in attrs) n.setAttribute(k, attrs[k]);
    if (text != null) n.textContent = text;
    return n;
  }
  const damp = (rate, dt) => 1 - Math.exp(-rate * dt);
  const ease = t => t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

  // ---------- data: data.json over http, data.js from disk, or the page's ?data=<url> ----------
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      delete window.NHI_DATA;
      const sc = document.createElement("script");
      sc.src = src;
      sc.onload = () => window.NHI_DATA ? resolve(window.NHI_DATA) : reject(new Error(src + " loaded but set no window.NHI_DATA. Run pipeline.build."));
      sc.onerror = () => reject(new Error(src + " could not be loaded."));
      document.head.appendChild(sc);
    });
  }
  function fetchJson(url) {
    return fetch(url, { cache: "no-store" }).then(
      r => { if (!r.ok) throw new Error(url + ": HTTP " + r.status + "."); return r.json(); },
      e => { throw new Error(url + " could not be fetched (" + e.message + ")."); });
  }
  // ?data= names a sibling file of the page only: on a published artifact an absolute URL would run
  // a third party's script in the page's origin
  function loadData() {
    const src = new URLSearchParams(location.search).get("data");
    if (src != null) {
      if (!src || /^[a-z][a-z0-9+.-]*:/i.test(src) || /^[\/\\]/.test(src)) return Promise.reject(new Error("the parameter ?data=" + src + " is refused: it must be a relative path to a file beside the page, with no scheme and no leading slash."));
      return /\.js(\?|#|$)/.test(src) ? loadScript(src) : fetchJson(src);
    }
    if (location.protocol === "file:") return loadScript("data.js").catch(e => { throw new Error(e.message + " Opened from disk, the page reads data.js beside index.html; run pipeline.build."); });
    return fetchJson("data.json").catch(e => { throw new Error(e.message + " Over http the page reads data.json beside index.html; run pipeline.build."); });
  }
  function loadThree() {
    const timeout = new Promise((_, reject) => setTimeout(() => reject(new Error("three.js did not load from cdn.jsdelivr.net within 15 seconds. The page needs that CDN to draw.")), 15000));
    return Promise.race([Promise.all([
      import("three"), import("three/addons/controls/OrbitControls.js"), import("three/addons/renderers/CSS2DRenderer.js"),
    ]), timeout]);
  }

  Promise.all([loadData(), loadThree()]).then(([D, mods]) => start(D, mods))
    .catch(e => fatal(e && /^NHI data:|could not be|did not load|HTTP|NHI_DATA|the link|the parameter/.test(e.message) ? e.message : (e && (e.stack || e.message)) || e));

  function start(D, mods) {
    const THREE = mods[0];
    const addons = { OrbitControls: mods[1].OrbitControls, CSS2DRenderer: mods[2].CSS2DRenderer, CSS2DObject: mods[2].CSS2DObject };
    const M = NHI.model.build(D);
    const hash = new URLSearchParams(location.hash.slice(1));


    const canvas = $("scene");
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));

    let selected = null, hoverSid = null, previewSid = null, rail = null, view = null, globe = null;
    const C = {
      THREE, M, canvas, renderer, el, damp, ease,
      select, preview, hover, hoverSid: () => hoverSid, leaveRail, onRail: () => !!rail, usedOnce, placeLabels,
      touch: matchMedia("(pointer: coarse)").matches || hash.has("touch"),   // #touch forces the touch layer on a computer
    };
    const panel = NHI.panel(C);
    const corridor = NHI.corridor(C);
    function getGlobe() { if (!globe) globe = NHI.globe(C, addons); return globe; }

    // ---------- labels and hover ----------
    const labelsEl = $("labels"), labelPool = [];
    for (let i = 0; i < 12; i++) { const l = el("div", { class: "label" }); l.style.display = "none"; labelsEl.appendChild(l); labelPool.push(l); }
    function placeLabels(cands) {
      cands.sort((a, b) => b.rank - a.rank);
      const placed = [];
      let k = 0;
      for (const c of cands) {
        if (k >= labelPool.length) break;
        if (placed.some(p => Math.abs(p.x - c.x) < 170 && Math.abs(p.y - c.y) < 22)) continue;
        placed.push(c);
        const s = M.storyById[c.id], l = labelPool[k++];
        l.className = "label t" + s._tier + (c.id === selected ? " sel" : "");
        l.textContent = s.title; l.style.left = c.x + "px"; l.style.top = c.y + "px"; l.style.display = "block";
      }
      for (; k < labelPool.length; k++) labelPool[k].style.display = "none";
    }
    const hoverEl = $("hover");
    function hover(sid, cx, cy) {
      if (sid !== hoverSid) { hoverSid = sid; canvas.classList.toggle("pointing", !!sid); view.setEmphasis(previewSid || hoverSid); }
      if (!sid) { hoverEl.style.display = "none"; return; }
      const s = M.storyById[sid], shared = M.sharing(sid).size;
      hoverEl.innerHTML = "";
      hoverEl.appendChild(el("b", null, s.title));
      hoverEl.appendChild(el("span", null, M.KIND_NAMES[s.kind] + " · " + M.yearsText(s.years) + " · " + M.TIERS[s._tier].name + ", score " + s._score.toFixed(2) +
        " · " + (shared ? "shares a voice or source with " + shared + (shared === 1 ? " story" : " stories") : "shares no voice or source")));
      hoverEl.style.display = "block";
      hoverEl.style.left = Math.min(cx, window.innerWidth - 180) + "px"; hoverEl.style.top = (cy - 8) + "px";
    }
    function preview(sid) { previewSid = sid; view.setEmphasis(previewSid || hoverSid); }

    // ---------- selection and the panel ----------
    function writeHash() {
      const h = new URLSearchParams();
      if (selected) h.set("story", selected);
      if (view.name === "globe") h.set("mode", "globe");
      if (rail) h.set("rail", rail.type);
      if (Math.abs(M.trust.value - M.trust.def) > 1e-9) h.set("trust", M.trust.value.toFixed(2));
      try { history.replaceState(null, "", h.toString() ? "#" + h.toString().replace(/=(&|$)/g, "$1") : location.pathname + location.search); } catch (e) { /* some browsers refuse on file: */ }
    }
    function select(sid, opts) {
      opts = opts || {};
      if (!sid) { closePanel(); return; }
      selected = sid;
      usedOnce();
      revealStory(sid);
      panel.render(sid);
      document.body.classList.add("panel-open");
      view.setSelected(sid);
      if (opts.fly) {
        if (rail) railFollow(sid, opts.instant);
        else view.flyTo(sid, opts.instant);
      }
      writeHash();
    }
    function closePanel() {
      if (rail) leaveRail();
      selected = null; view.setSelected(null);
      document.body.classList.remove("panel-open");
      writeHash();
    }
    $("panel-close").addEventListener("click", closePanel);

    // ---------- filters: tier, kind, region ----------
    function revealStory(sid) {
      const s = M.storyById[sid];
      if (M.isVisible(s)) return;
      M.hidden.kind.delete(s.kind); M.hidden.region.delete(M.regionOf(s)); M.hidden.tier.delete(s._tierId);
      buildFilters(); view.applyVisibility();
    }
    function filterRow(ul, set, key, label, count, mark) {
      const li = el("li", { title: "Click to hide or show " + label });
      li.appendChild(mark);
      li.appendChild(el("span", null, label));
      li.appendChild(el("span", { class: "n" }, String(count)));
      if (set.has(key)) li.classList.add("off");
      li.addEventListener("click", () => {
        if (set.has(key)) set.delete(key); else set.add(key);
        li.classList.toggle("off", set.has(key));
        view.applyVisibility();
        if (rail) renderRailHud();
      });
      ul.appendChild(li);
    }
    function buildFilters() {
      const tl = $("tiers"); tl.innerHTML = "";
      M.TIERS.forEach((T, i) => {
        const mark = el("span", { class: "tdot" }), dot = el("i");
        const px = [11, 8, 5][i]; dot.style.width = dot.style.height = px + "px"; dot.style.opacity = T.bright;
        mark.appendChild(dot);
        filterRow(tl, M.hidden.tier, T.id, T.name, M.tierCounts[i], mark);
        tl.lastChild.title = T.rule + ". Click to hide or show.";
      });
      const kl = $("kinds"); kl.innerHTML = "";
      M.KINDS.filter(k => M.kindCounts[k]).forEach(k => { const sw = el("span", { class: "sw" }); sw.style.background = M.KIND_COLORS[k]; filterRow(kl, M.hidden.kind, k, M.KIND_NAMES[k], M.kindCounts[k], sw); });
      const rl = $("regions"); rl.innerHTML = "";
      M.regionKeys.forEach(r => filterRow(rl, M.hidden.region, r, r, M.regionCounts.get(r), el("span", { class: "sw reg" })));
    }
    buildFilters();
    $("legend-toggle").addEventListener("click", () => { document.body.classList.toggle("legend-hidden"); $("legend-toggle").classList.toggle("on", !document.body.classList.contains("legend-hidden")); });
    if (window.innerWidth < 760) document.body.classList.add("legend-hidden");
    $("legend-toggle").classList.toggle("on", !document.body.classList.contains("legend-hidden"));

    // ---------- the institutional-trust knob ----------
    const knob = $("trust");
    knob.min = M.trust.min; knob.max = M.trust.max; knob.value = M.trust.def;
    function setTrust(v) {
      v = Math.min(M.trust.max, Math.max(M.trust.min, v));
      knob.value = v;
      M.rescore(v);
      $("trust-val").textContent = v.toFixed(2) + (Math.abs(v - M.trust.def) < 1e-9 ? " (default)" : "");
      $("trust-note").textContent = "An official teller weighs " + (D.scoring.weights.official * v).toFixed(2) + " against a witness at 1.00. Corpus median attestation " +
        M.median.toFixed(2) + "; a score of 1.0 is the typical story here.";
      view.restyle();
      if (selected) panel.render(selected);
      if (rail) renderRailHud();
    }
    knob.addEventListener("input", () => { setTrust(parseFloat(knob.value)); writeHash(); });

    // ---------- rails ----------
    const RAIL_NAMES = { time: "Time", kind: "Kind", strength: "Strength", links: "Links" };
    const RAIL_CODES = { Digit1: "time", Digit2: "kind", Digit3: "strength", Digit4: "links", Numpad1: "time", Numpad2: "kind", Numpad3: "strength", Numpad4: "links" };
    const LINK_ORDER = ["same-event", "variant", "corroborates", "contradicts"];
    const linkRank = r => { const i = LINK_ORDER.indexOf(r); return i < 0 ? LINK_ORDER.length : i; };
    function linkList(sid) {
      const rel = new Map([[sid, "start"]]);
      M.linksOf(sid).slice().sort((a, b) => linkRank(a.relation) - linkRank(b.relation) || M.storyById[a.other]._order - M.storyById[b.other]._order)
        .forEach(x => { if (!rel.has(x.other)) rel.set(x.other, x.relation); });
      return { list: [...rel.keys()], rel };
    }
    function railList() {
      const s = M.storyById[rail.sid], keep = x => M.isVisible(x) || x.id === rail.sid;
      if (rail.type === "time") return M.byTime.filter(keep).map(x => x.id);
      if (rail.type === "kind") return M.byTime.filter(x => x.kind === s.kind && keep(x)).map(x => x.id);
      if (rail.type === "strength") return M.byStrength.filter(keep).map(x => x.id);
      return rail.links.list;
    }
    function goRail(type, sid, instant) {
      if (type === "links" && !M.linksOf(sid).length) {
        railNote("This story has no links; riding " + RAIL_NAMES[rail && rail.type !== "links" ? rail.type : "time"] + ".");
        type = rail && rail.type !== "links" ? rail.type : "time";
      }
      rail = { type, sid, links: type === "links" ? linkList(sid) : null };
      railMoveTo(sid, instant);
    }
    function railMoveTo(sid, instant) {
      rail.sid = sid;
      revealStory(sid);
      if (view.reveal) view.reveal(sid);
      select(sid);
      view.railArrive(sid, instant);
      renderRailHud();
      writeHash();
    }
    // a story chosen while riding (a click, a related story, search): the rail follows it
    function railFollow(sid, instant) {
      if (rail.type === "links" && !rail.links.list.includes(sid)) {
        if (M.linksOf(sid).length) rail.links = linkList(sid); else { rail.type = "time"; rail.links = null; railNote("Left the links; riding Time."); }
      }
      rail.sid = sid;
      view.railArrive(sid, instant);
      renderRailHud();
    }
    function railStep(dir) {
      if (!rail) { snap(); return; }
      const list = railList(), i = list.indexOf(rail.sid), j = i + dir;
      if (i < 0) { railMoveTo(list[0]); return; }
      if (j < 0 || j >= list.length) { railNote(dir > 0 ? "End of the " + RAIL_NAMES[rail.type] + " rail." : "Start of the " + RAIL_NAMES[rail.type] + " rail."); clearHold(); return; }
      railMoveTo(list[j]);
    }
    function snap(type) {
      const sid = (!rail && selected) && type ? selected : view.nearestStory();
      if (sid) goRail(type || (rail ? rail.type : "time"), sid);
    }
    function leaveRail() {
      if (!rail) return;
      rail = null; clearHold(); view.railRelease(); renderRailHud(); writeHash();
    }
    let stepHold = null;
    function clearHold() { if (stepHold) { clearTimeout(stepHold.timer); stepHold = null; } }
    function holdStep(code, dir) {
      if (stepHold && stepHold.code === code) return;
      clearHold(); railStep(dir);
      stepHold = { code, timer: setTimeout(function rep() { railStep(dir); if (stepHold) stepHold.timer = setTimeout(rep, 360); }, 480) };
    }
    const railHud = $("railhud");
    let noteTimer = null;
    function railNote(msg) {
      railHud.querySelector(".rh-note").textContent = msg; railHud.classList.add("noting");
      clearTimeout(noteTimer); noteTimer = setTimeout(() => railHud.classList.remove("noting"), 1800);
    }
    const shortTitle = t => t.length > 46 ? t.slice(0, 44).replace(/\s+\S*$/, "") + "…" : t;
    function renderRailHud() {
      document.body.classList.toggle("on-rail", !!rail);
      if (!rail) return;
      const s = M.storyById[rail.sid], list = railList(), i = list.indexOf(rail.sid);
      const name = rail.type === "kind" ? "Kind: " + M.KIND_NAMES[s.kind] : rail.type === "links" ? "Links of " + shortTitle(M.storyById[rail.links.list[0]].title)
        : rail.type === "strength" ? "Strength, best attested first" : "Time, in order";
      railHud.querySelector(".rh-name").textContent = name;
      railHud.querySelector(".rh-pos").textContent = (i + 1) + " of " + list.length;
      const peek = (j, cls) => {
        const b = railHud.querySelector(cls), id = list[j];
        b.disabled = !id; b.innerHTML = "";
        if (!id) { b.appendChild(el("span", { class: "rh-t" }, j < 0 ? "start of the rail" : "end of the rail")); return; }
        const o = M.storyById[id], sw = el("span", { class: "sw" }); sw.style.background = M.KIND_COLORS[o.kind];
        b.appendChild(sw); b.appendChild(el("span", { class: "rh-t" }, shortTitle(o.title)));
        const extra = rail.type === "strength" ? o._score.toFixed(2) : rail.type === "links" ? rail.links.rel.get(id).replace(/-/g, " ") : M.yearsText(o.years);
        b.appendChild(el("span", { class: "rh-x" }, extra));
      };
      peek(i - 1, ".rh-prev"); peek(i + 1, ".rh-next");
      railHud.querySelectorAll(".rh-rails b").forEach(b => b.classList.toggle("on", b.dataset.r === rail.type));
    }
    railHud.querySelector(".rh-prev").addEventListener("click", () => railStep(-1));
    railHud.querySelector(".rh-next").addEventListener("click", () => railStep(1));
    railHud.querySelectorAll(".rh-rails b[data-r]").forEach(b => b.addEventListener("click", () => { if (rail) goRail(b.dataset.r, rail.sid); }));
    railHud.querySelector(".rh-free").addEventListener("click", leaveRail);

    // ---------- the touch pad: a held button is a held key, so the views' own flight code moves the camera ----------
    document.body.classList.toggle("touch", C.touch);
    const fakeKey = code => ({ code, key: "", repeat: false, preventDefault() {} });
    document.querySelectorAll("#pad .pb[data-key]").forEach(b => {
      const code = b.dataset.key;
      let held = false;
      const up = () => { if (!held) return; held = false; b.classList.remove("held"); view.keyup(fakeKey(code)); };
      b.addEventListener("pointerdown", e => {
        e.preventDefault(); usedOnce();
        if (b.dataset.tap) { view.keydown(fakeKey(code)); return; }
        held = true; b.classList.add("held"); b.setPointerCapture(e.pointerId); view.keydown(fakeKey(code));
      });
      ["pointerup", "pointercancel", "lostpointercapture"].forEach(t => b.addEventListener(t, up));
      b.addEventListener("contextmenu", e => e.preventDefault());
    });
    $("pad-rail").addEventListener("pointerdown", e => { e.preventDefault(); if (rail) leaveRail(); else snap(); usedOnce(); });
    $("pad-rail").addEventListener("contextmenu", e => e.preventDefault());

    // ---------- search ----------
    const searchEl = $("search"), resultsEl = $("results");
    const searchIndex = D.stories.map(s => ({ s, text: [s.title, s.plain || "", s.summary || "", M.placeText(s), M.KIND_NAMES[s.kind], M.regionOf(s), M.yearsText(s.years),
      ...s.tellings.map(t => (t.teller_name || M.personName(t.teller)) + " " + t.cites.map(M.personName).join(" "))].join(" ").toLowerCase() }));
    let resultIds = [], resultHi = 0;
    const closeResults = () => resultsEl.classList.remove("open");
    function renderResults() {
      const q = searchEl.value.trim().toLowerCase();
      resultsEl.innerHTML = "";
      if (!q) { resultIds = []; closeResults(); return; }
      const words = q.split(/\s+/);
      const hits = searchIndex.filter(x => words.every(w => x.text.includes(w)))
        .sort((a, b) => (b.s.title.toLowerCase().includes(q) - a.s.title.toLowerCase().includes(q)) || a.s._tier - b.s._tier || b.s._score - a.s._score).slice(0, 12);
      resultIds = hits.map(h => h.s.id); resultHi = 0;
      if (!hits.length) resultsEl.appendChild(el("li", { class: "none" }, "No story matches."));
      hits.forEach((h, i) => {
        const li = el("li", { role: "option" }), sw = el("span", { class: "sw" }); sw.style.background = M.KIND_COLORS[h.s.kind];
        li.appendChild(sw); li.appendChild(el("span", { class: "t" }, h.s.title)); li.appendChild(el("span", { class: "s" }, M.yearsText(h.s.years) + " · " + M.TIERS[h.s._tier].name));
        li.addEventListener("mousedown", ev => { ev.preventDefault(); chooseResult(i); });
        resultsEl.appendChild(li);
      });
      [...resultsEl.children].forEach((li, i) => li.classList.toggle("hi", i === resultHi && resultIds.length > 0));
      resultsEl.classList.add("open");
    }
    function chooseResult(i) { const sid = resultIds[i]; if (!sid) return; closeResults(); searchEl.blur(); select(sid, { fly: true }); }
    searchEl.addEventListener("input", renderResults);
    searchEl.addEventListener("focus", () => { if (searchEl.value.trim()) renderResults(); });
    searchEl.addEventListener("blur", () => setTimeout(closeResults, 120));
    searchEl.addEventListener("keydown", e => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault(); resultHi = Math.max(0, Math.min(resultIds.length - 1, resultHi + (e.key === "ArrowDown" ? 1 : -1)));
        [...resultsEl.children].forEach((li, i) => li.classList.toggle("hi", i === resultHi));
      } else if (e.key === "Enter") { e.preventDefault(); chooseResult(resultHi); }
      else if (e.key === "Escape") { e.preventDefault(); if (searchEl.value) { searchEl.value = ""; renderResults(); } else searchEl.blur(); }
    });

    // ---------- the keys overlay: shown once per visit, folded after first use, K toggles ----------
    const keysWrap = $("keys-wrap");
    let usedYet = false, seen = false;
    try { seen = sessionStorage.getItem("nhi-keys-seen") === "1"; sessionStorage.setItem("nhi-keys-seen", "1"); } catch (e) { seen = false; }
    const setKeysCollapsed = c => keysWrap.classList.toggle("collapsed", c);
    function usedOnce() { if (usedYet) return; usedYet = true; setTimeout(() => setKeysCollapsed(true), 4000); }
    // a touch device gets the guidance open at the start whatever its width: there is no key to discover
    setKeysCollapsed(seen || hash.has("nohint") || (window.innerWidth < 760 && !C.touch));
    if (C.touch) { keysWrap.querySelector("#keys h2").textContent = "How to move"; $("keys-show").textContent = "How to move"; $("keys-show").title = "Show how to move"; }
    $("keys-hide").addEventListener("click", () => setKeysCollapsed(true));
    $("keys-show").addEventListener("click", () => setKeysCollapsed(false));

    // ---------- modes ----------
    function setMode(name, instant) {
      const next = name === "globe" ? getGlobe() : corridor;
      if (view === next) return;
      if (view) { view.deactivate(); hover(null); }
      view = next;
      document.body.classList.toggle("mode-corridor", name !== "globe");
      document.body.classList.toggle("mode-globe", name === "globe");
      document.querySelectorAll("#mode-seg button").forEach(b => b.classList.toggle("on", b.dataset.mode === name));
      $("subtitle").textContent = name === "globe"
        ? "Regions sized by how many stories they hold, eras as shells above them. Stories as told, not facts."
        : "Time runs ahead of you, stretched where many stories are told. The better attested, the nearer the centre and the brighter. Stories as told, not facts.";
      resize();
      view.activate();
      view.applyVisibility(); view.restyle(); view.setSelected(selected); view.setEmphasis(null);
      if (rail) view.railArrive(rail.sid, true);
      else if (selected) view.flyTo(selected, instant !== false);
      writeHash();
    }
    document.querySelectorAll("#mode-seg button").forEach(b => b.addEventListener("click", () => setMode(b.dataset.mode)));

    // ---------- keys ----------
    const isTyping = t => t && (t.isContentEditable || t.tagName === "TEXTAREA" || (t.tagName === "INPUT" && t.type !== "range" && t.type !== "checkbox" && t.type !== "button"));
    window.addEventListener("keydown", e => {
      if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.target && e.target.type === "range" && /^Arrow/.test(e.code)) return;   // a focused slider keeps its arrows
      const c = e.code;
      if (c === "Escape") {
        if (rail) { leaveRail(); return; }
        if (document.body.classList.contains("panel-open")) { closePanel(); return; }
        view.escape(); return;
      }
      if (c === "Slash" || e.key === "/") { e.preventDefault(); searchEl.focus(); return; }
      if (c === "KeyK") { setKeysCollapsed(!keysWrap.classList.contains("collapsed")); return; }
      if (c === "KeyM") { setMode(view.name === "globe" ? "corridor" : "globe"); return; }
      if (c === "Tab") { e.preventDefault(); snap(); usedOnce(); return; }
      if (RAIL_CODES[c]) { e.preventDefault(); if (rail) goRail(RAIL_CODES[c], rail.sid); else snap(RAIL_CODES[c]); usedOnce(); return; }
      if (c === "BracketRight" || c === "Period" || c === "BracketLeft" || c === "Comma") {
        e.preventDefault(); if (!e.repeat) holdStep(c, c === "BracketRight" || c === "Period" ? 1 : -1); usedOnce(); return;
      }
      view.keydown(e);
    });
    window.addEventListener("keyup", e => { if (stepHold && e.code === stepHold.code) clearHold(); view.keyup(e); });
    window.addEventListener("blur", () => { view.blur(); clearHold(); });
    // a clicked button gives focus back, so Space and the arrows fly instead of pressing it again
    document.addEventListener("click", e => { const b = e.target.closest && e.target.closest("button"); if (b) b.blur(); });

    // ---------- size and loop ----------
    function resize() {
      const w = window.innerWidth, h = window.innerHeight;
      renderer.setSize(w, h, false);
      corridor.resize(w, h);
      if (globe) globe.resize(w, h);
    }
    window.addEventListener("resize", resize);

    // ---------- start from the link: #story=, #mode=globe, #rail=, #trust=, #nohint, #touch (the touch layer on a computer), and each view's own ----------
    if (hash.has("trust")) {
      const t = parseFloat(hash.get("trust"));
      if (!Number.isFinite(t) || t < M.trust.min || t > M.trust.max) throw new Error("the link asks for institutional trust " + JSON.stringify(hash.get("trust")) + "; expected " + M.trust.min + " to " + M.trust.max + ".");
    }
    const startMode = hash.get("mode") || "corridor";
    if (startMode !== "corridor" && startMode !== "globe") throw new Error("the link asks for mode " + JSON.stringify(startMode) + "; expected corridor or globe.");
    const panelEl = $("panel"); panelEl.style.transition = "none";
    requestAnimationFrame(() => requestAnimationFrame(() => { panelEl.style.transition = ""; }));
    setMode(startMode);
    view.applyHash(hash);
    setTrust(hash.has("trust") ? parseFloat(hash.get("trust")) : M.trust.def);
    if (hash.has("story")) {
      const sid = M.resolve(hash.get("story"));
      if (!sid) throw new Error("the link names story " + JSON.stringify(hash.get("story")) + ", which is neither a story nor an alias of one in the data.");
      select(sid, { fly: true, instant: true });
      if (view.setPanelShiftInstant) view.setPanelShiftInstant();
    }
    if (hash.has("rail")) {
      const r = hash.get("rail");
      if (!RAIL_NAMES[r]) throw new Error("the link asks for rail " + JSON.stringify(r) + "; expected time, kind, strength or links.");
      view.syncCamera();
      const sid = selected || view.nearestStory();
      if (sid) goRail(r, sid, true);
    }
    $("subtitle").title = D.stories.length + " stories, corpus of " + (D.corpus_date || "no date") + ", built " + (D.built || "unknown");
    $("loading").hidden = true;

    let last = performance.now();
    function frame(now) {
      const dt = Math.min(0.1, Math.max(0, (now - last) / 1000)); last = now;
      view.frame(dt, now);
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }
})();
