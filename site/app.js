/* NHI timeline: eras across, places down, each story a dot sized by its score. Plain JS, no build. */
(function () {
  "use strict";
  var SVGNS = "http://www.w3.org/2000/svg";
  var TOP = 44;          // era header height
  var ROW = 44;          // place row height
  var BAND = 24;         // region band height
  var MINCOL = 120;      // narrowest era column
  var GUTTER = 150;      // place label column
  var state = { data: null, selected: null, pos: {}, groups: {} };

  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    for (var k in attrs || {}) e.setAttribute(k, attrs[k]);
    if (text != null) e.textContent = text;
    return e;
  }
  function svgEl(tag, attrs) {
    var e = document.createElementNS(SVGNS, tag);
    for (var k in attrs || {}) e.setAttribute(k, attrs[k]);
    return e;
  }
  function fmt(s) {
    s = Math.floor(s);
    var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return h + ":" + (m < 10 ? "0" : "") + m + ":" + (x < 10 ? "0" : "") + x;
  }
  function yearsText(y) {
    if (!y) return "undated";
    return y.from === y.to ? String(y.from) : y.from + " to " + y.to;
  }
  function radius(score) {
    return Math.max(4, Math.min(18, 4 + 7 * Math.sqrt(Math.max(0, score))));
  }

  // Theme: follows the system unless the viewer chose; the choice is a per-viewer convenience.
  function themeInit() {
    var saved = null;
    try { saved = localStorage.getItem("nhi-theme"); } catch (e) { saved = null; }
    if (saved) document.documentElement.setAttribute("data-theme", saved);
    document.getElementById("theme").addEventListener("click", function () {
      var dark = document.documentElement.getAttribute("data-theme") === "dark" ||
        (!document.documentElement.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
      var next = dark ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("nhi-theme", next); } catch (e) { /* no storage: the toggle still works for this page */ }
    });
  }

  // Same-event pairs are drawn as one marker: union the stories joined by same-event links.
  function groupsOf(data) {
    var parent = {};
    function find(x) { while (parent[x] !== x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; }
    data.stories.forEach(function (s) { parent[s.id] = s.id; });
    data.links.forEach(function (l) {
      if (l.relation === "same-event" && parent[l.a] && parent[l.b]) parent[find(l.a)] = find(l.b);
    });
    var groups = {};
    data.stories.forEach(function (s) { var r = find(s.id); (groups[r] = groups[r] || []).push(s); });
    var byStory = {};
    Object.keys(groups).forEach(function (r) {
      groups[r].sort(function (a, b) { return b.score - a.score || (a.id < b.id ? -1 : 1); });
      groups[r].forEach(function (s) { byStory[s.id] = r; });
    });
    return { groups: groups, byStory: byStory };
  }

  function render(data) {
    document.getElementById("corpus-date").textContent = data.corpus_date || "no dated episode";
    document.getElementById("story-count").textContent = String(data.stories.length);
    document.getElementById("median").textContent = Number(data.median_attestation).toFixed(2);

    var grid = document.getElementById("grid");
    grid.textContent = "";
    var phone = window.innerWidth < 720;
    var gutter = phone ? 110 : GUTTER;
    var eras = data.eras.slice();
    var undated = data.stories.some(function (s) { return !s.years || s.era == null; });
    if (undated) eras.push({ id: "__undated", name: "Undated", from: null, to: null });
    var avail = grid.clientWidth - gutter - 2;
    var colw = Math.max(MINCOL, Math.floor(avail / eras.length));
    var eraIndex = {};
    eras.forEach(function (e, i) { eraIndex[e.id] = i; });

    // rows: regions in the order of places.json, each with its places; an Unplaced row at the end when needed
    var regions = [], byRegion = {};
    data.places.forEach(function (p) {
      var r = p.region || "Elsewhere";
      if (!byRegion[r]) { byRegion[r] = []; regions.push(r); }
      byRegion[r].push(p);
    });
    var storiesByPlace = {};
    data.stories.forEach(function (s) { var k = s.place || "__unplaced"; (storiesByPlace[k] = storiesByPlace[k] || []).push(s); });
    if (storiesByPlace.__unplaced) { regions.push("Unplaced"); byRegion.Unplaced = [{ id: "__unplaced", name: "Place not resolved", region: "Unplaced" }]; }
    var rows = [], y = TOP;
    regions.forEach(function (r) {
      rows.push({ kind: "region", name: r, y: y, h: BAND }); y += BAND;
      byRegion[r].forEach(function (p) { rows.push({ kind: "place", place: p, y: y, h: ROW }); y += ROW; });
    });
    var height = y + 8, width = eras.length * colw + 1;
    var rowOf = {};
    rows.forEach(function (r) { if (r.kind === "place") rowOf[r.place.id] = r; });

    var inner = el("div", { class: "grid-inner" });
    var labels = el("div", { class: "labels", style: "width:" + gutter + "px;height:" + height + "px" });
    rows.forEach(function (r) {
      var d = el("div", { class: r.kind === "region" ? "region" : "place" + (storiesByPlace[r.place.id] ? " has-stories" : ""),
        style: "top:" + r.y + "px;height:" + r.h + "px;line-height:" + r.h + "px" }, r.kind === "region" ? r.name : r.place.name);
      if (r.kind === "place") d.title = r.place.name;
      labels.appendChild(d);
    });
    inner.appendChild(labels);

    var svg = svgEl("svg", { class: "chart", width: width, height: height, viewBox: "0 0 " + width + " " + height, role: "img" });
    svg.appendChild(svgEl("title")).textContent = "Stories by era and place";
    // cells and bands
    rows.forEach(function (r, ri) {
      if (r.kind === "region") { svg.appendChild(svgEl("rect", { class: "region-band", x: 0, y: r.y, width: width, height: r.h })); return; }
      eras.forEach(function (e, ci) {
        svg.appendChild(svgEl("rect", { class: "cell" + ((ri + ci) % 2 ? " alt" : ""), x: ci * colw, y: r.y, width: colw, height: r.h }));
      });
    });
    eras.forEach(function (e, ci) {
      var x = ci * colw;
      svg.appendChild(svgEl("line", { class: "gridline", x1: x, y1: 0, x2: x, y2: height }));
      var t = svgEl("text", { class: "era-label", x: x + 8, y: 18 }); t.textContent = e.name; svg.appendChild(t);
      var yrs = svgEl("text", { class: "era-years", x: x + 8, y: 34 }); yrs.textContent = e.from == null ? "" : e.from + " to " + e.to; svg.appendChild(yrs);
    });
    svg.appendChild(svgEl("line", { class: "gridline", x1: width - 1, y1: 0, x2: width - 1, y2: height }));

    // positions: x from the year within its era, y from the place row; stories in the same cell spread vertically
    var g = groupsOf(data);
    state.groups = g;
    var pos = {}, cellCount = {};
    function xOf(s) {
      var e = s.era != null && eraIndex[s.era] != null ? eras[eraIndex[s.era]] : null;
      if (!e || !s.years) return eraIndex.__undated * colw + colw / 2;
      var mid = (s.years.from + s.years.to) / 2;
      var f = (mid - e.from) / (e.to - e.from + 1);
      return eraIndex[e.id] * colw + 10 + Math.max(0, Math.min(1, f)) * (colw - 20);
    }
    function xYear(yr, s) {
      var e = eras[eraIndex[s.era]];
      return eraIndex[e.id] * colw + 10 + Math.max(0, Math.min(1, (yr - e.from) / (e.to - e.from + 1))) * (colw - 20);
    }
    var reps = Object.keys(g.groups).map(function (r) { return g.groups[r][0]; });
    reps.forEach(function (s) {
      var row = rowOf[s.place || "__unplaced"] || rowOf.__unplaced;
      var key = (s.place || "__unplaced") + "|" + (s.era == null ? "__undated" : s.era);
      cellCount[key] = (cellCount[key] || 0) + 1;
    });
    var seen = {};
    reps.forEach(function (s) {
      var row = rowOf[s.place || "__unplaced"];
      var key = (s.place || "__unplaced") + "|" + (s.era == null ? "__undated" : s.era);
      var n = cellCount[key], i = (seen[key] = (seen[key] || 0) + 1) - 1;
      // several stories in one cell: fan them out sideways, alternating a little up and down
      var dx = n > 1 ? (i - (n - 1) / 2) * 44 : 0, dy = n > 1 ? (i % 2 ? 9 : -9) : 0;
      pos[g.byStory[s.id]] = { x: Math.max(14, Math.min(colw * eras.length - 14, xOf(s) + dx)), y: row.y + row.h / 2 + dy, dx: dx, s: s };
    });
    state.pos = pos;

    // links between groups (never inside one)
    var linkLayer = svgEl("g"), warnLayer = svgEl("g", { class: "warn-layer" }), pairCount = {};
    data.links.forEach(function (l) {
      var a = g.byStory[l.a], b = g.byStory[l.b];
      if (!a || !b || a === b) return;
      // a slight arc, so a link between two neighbouring dots is still seen; several links on one pair alternate sides
      var key = a < b ? a + "|" + b : b + "|" + a, i = pairCount[key] = (pairCount[key] || 0) + 1;
      var side = (i % 2 ? 1 : -1) * Math.ceil(i / 2);
      var ax = pos[a].x, ay = pos[a].y, bx = pos[b].x, by = pos[b].y, len = Math.hypot(bx - ax, by - ay) || 1;
      var bulge = Math.max(18, 0.12 * len) * side, nx = -(by - ay) / len * bulge, ny = (bx - ax) / len * bulge;
      var line = svgEl("path", { class: "link " + l.relation, d: "M" + ax + " " + ay + " Q" + ((ax + bx) / 2 + nx) + " " + ((ay + by) / 2 + ny) + " " + bx + " " + by });
      var t = svgEl("title"); t.textContent = l.relation + (l.note ? ": " + l.note : ""); line.appendChild(t);
      (l.relation === "contradicts" ? warnLayer : linkLayer).appendChild(line);
    });
    svg.appendChild(linkLayer);

    // the dots
    var dotLayer = svgEl("g");
    Object.keys(pos).forEach(function (root) {
      var p = pos[root], members = g.groups[root], s = members[0];
      var r = radius(s.score), repCount = members.reduce(function (n, m) { return n + m.repetitions.length; }, 0);
      var node = svgEl("g", { class: "story", tabindex: "0", role: "button", "data-group": root });
      var t = svgEl("title"); t.textContent = members.map(function (m) { return m.title; }).join(" / ") + " (" + yearsText(s.years) + ")"; node.appendChild(t);
      if (s.years && s.years.to > s.years.from && s.era != null && eraIndex[s.era] != null) {
        node.appendChild(svgEl("line", { class: "span", x1: xYear(s.years.from, s) + p.dx, y1: p.y, x2: xYear(s.years.to, s) + p.dx, y2: p.y }));
      }
      if (repCount) node.appendChild(svgEl("circle", { class: "halo", cx: p.x, cy: p.y, r: r + 5 + 3 * repCount }));
      node.appendChild(svgEl("circle", { class: "hit", cx: p.x, cy: p.y, r: r + 6 }));
      node.appendChild(svgEl("circle", { class: "dot", cx: p.x, cy: p.y, r: r }));
      for (var k = 1; k < members.length; k++) node.appendChild(svgEl("circle", { class: "ring", cx: p.x, cy: p.y, r: r + 3.5 * k + 1 }));
      node.addEventListener("click", function () { select(root); });
      node.addEventListener("keydown", function (ev) { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); select(root); } });
      dotLayer.appendChild(node);
    });
    svg.appendChild(dotLayer);
    svg.appendChild(warnLayer);
    inner.appendChild(svg);
    grid.appendChild(inner);
    if (state.selected && pos[state.selected]) select(state.selected);
  }

  function select(root) {
    state.selected = root;
    try { history.replaceState(null, "", "#story=" + encodeURIComponent(state.groups.groups[root][0].id)); } catch (e) { /* file: pages may refuse */ }
    var members = state.groups.groups[root];
    var panel = document.getElementById("panel"), body = document.getElementById("panel-body");
    body.textContent = "";
    document.querySelectorAll(".story.selected").forEach(function (n) { n.classList.remove("selected"); });
    var node = document.querySelector('.story[data-group="' + root + '"]');
    if (node) node.classList.add("selected");
    if (members.length > 1) {
      var head = el("p", { class: "meta" }); head.appendChild(el("b", {}, "One event, " + members.length + " stories")); body.appendChild(head);
      members.forEach(function (s) { var box = el("div", { class: "pair" }); storyInto(box, s); body.appendChild(box); });
    } else {
      storyInto(body, members[0]);
    }
    panel.hidden = false;
  }

  function storyInto(box, s) {
    var d = state.data;
    box.appendChild(el("h2", {}, s.title));
    var meta = el("p", { class: "meta" });
    var place = s.place ? (d.places.filter(function (p) { return p.id === s.place; })[0] || {}).name : "place not resolved";
    var era = s.era ? (d.eras.filter(function (e) { return e.id === s.era; })[0] || {}).name : "no era";
    [["years", yearsText(s.years)], ["era", era], ["place", place], ["kind", s.kind || "unset"],
     ["score", Number(s.score).toFixed(2)], ["attestation", Number(s.attestation).toFixed(2)],
     ["independent tellers", String(s.independent.length)], ["repetitions", String(s.repetitions.length)]
    ].forEach(function (kv) { var sp = el("span", {}, kv[0] + " "); sp.appendChild(el("b", {}, kv[1])); meta.appendChild(sp); });
    box.appendChild(meta);
    box.appendChild(el("p", { class: "summary" }, s.summary));
    box.appendChild(el("h3", {}, "Tellings"));
    s.tellings.forEach(function (t) {
      var tl = el("div", { class: "telling" });
      var who = el("div", { class: "who" }); who.appendChild(el("b", {}, t.teller_name));
      who.appendChild(el("span", { class: "kind" }, t.kind));
      if (t.repetition) who.appendChild(el("span", { class: "rep" }, "repeats " + t.cites.map(function (c) { return (d.people[c] || {}).name || c; }).join(", ")));
      tl.appendChild(who);
      if (t.quote) tl.appendChild(el("blockquote", {}, "“" + t.quote + "”"));
      var where = el("div", { class: "where" });
      if (t.episode) {
        var label = fmt(t.from_s || 0) + (t.to_s != null ? " to " + fmt(t.to_s) : "");
        if (t.url) where.appendChild(el("a", { href: t.url, target: "_blank", rel: "noopener" }, label)); else where.appendChild(el("span", {}, label));
        where.appendChild(el("span", { class: "show" }, " " + [t.show, t.episode_title, t.published].filter(Boolean).join(", ")));
      } else if (t.document) {
        var doc = s.documents.filter(function (x) { return x.id === t.document; })[0] || { title: t.document };
        where.appendChild(el("span", { class: "show" }, "document: " + doc.title + (t.page ? ", p. " + t.page : "")));
      }
      tl.appendChild(where);
      if (t.cites.length && !t.repetition) tl.appendChild(el("div", { class: "cites" }, "cites " + t.cites.map(function (c) { return (d.people[c] || {}).name || c; }).join(", ")));
      if (t.documents.length) tl.appendChild(el("div", { class: "cites" }, "credits " + t.documents.map(function (x) { return (s.documents.filter(function (y) { return y.id === x; })[0] || { title: x }).title; }).join(", ")));
      box.appendChild(tl);
    });
    if (s.documents.length) {
      box.appendChild(el("h3", {}, "Documents"));
      var ul = el("ul", { class: "docs" });
      s.documents.forEach(function (x) {
        var li = el("li");
        if (x.url) li.appendChild(el("a", { href: x.url, target: "_blank", rel: "noopener" }, x.title)); else li.appendChild(el("span", {}, x.title));
        if (x.date) li.appendChild(el("span", { class: "show" }, " (" + x.date + ")"));
        ul.appendChild(li);
      });
      box.appendChild(ul);
    }
    var rel = d.links.filter(function (l) { return l.a === s.id || l.b === s.id; });
    if (rel.length) {
      box.appendChild(el("h3", {}, "Overlaps"));
      var ul2 = el("ul", { class: "related" });
      rel.forEach(function (l) {
        var other = l.a === s.id ? l.b : l.a;
        var os = d.stories.filter(function (x) { return x.id === other; })[0];
        if (!os) return;
        var li = el("li"); li.appendChild(el("span", { class: "rel " + l.relation }, l.relation));
        var b = el("button", { type: "button" }, os.title);
        b.addEventListener("click", function () { select(state.groups.byStory[other]); });
        li.appendChild(b);
        if (l.note) li.appendChild(el("span", { class: "show" }, " (" + l.note + ")"));
        ul2.appendChild(li);
      });
      box.appendChild(ul2);
    }
  }

  function fail(msg) {
    var st = document.getElementById("status"); st.textContent = msg; st.hidden = false;
  }

  function start(data) {
    if (!data || !Array.isArray(data.stories) || !Array.isArray(data.eras) || !Array.isArray(data.places)) {
      fail("data.json is not a build of pipeline.build (stories, eras and places expected)"); return;
    }
    state.data = data;
    render(data);
    var want = window.NHI_SELECT || (location.hash.indexOf("#story=") === 0 ? decodeURIComponent(location.hash.slice(7)) : null);
    if (want && state.groups.byStory[want]) select(state.groups.byStory[want]);
    var timer = null;
    window.addEventListener("resize", function () { clearTimeout(timer); timer = setTimeout(function () { render(data); }, 150); });
  }

  themeInit();
  document.getElementById("close").addEventListener("click", function () {
    document.getElementById("panel").hidden = true; state.selected = null;
    document.querySelectorAll(".story.selected").forEach(function (n) { n.classList.remove("selected"); });
  });
  if (location.protocol === "file:") {
    // a page opened from disk cannot fetch: build.py writes the same object as data.js
    var sc = document.createElement("script");
    sc.src = "data.js";
    sc.onload = function () { if (window.NHI_DATA) start(window.NHI_DATA); else fail("data.js loaded but set no NHI_DATA: run pipeline.build"); };
    sc.onerror = function () { fail("data.js not found beside index.html: run pipeline.build"); };
    document.head.appendChild(sc);
  } else {
    fetch("data.json", { cache: "no-store" }).then(function (r) {
      if (!r.ok) throw new Error("data.json: HTTP " + r.status);
      return r.json();
    }).then(start).catch(function (e) { fail(String(e && e.message || e) + " (run pipeline.build)"); });
  }
})();
