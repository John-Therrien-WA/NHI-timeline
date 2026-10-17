/* The corridor: time runs ahead of the viewer, stretched where many stories are told; the angle around the
   centre line is the kind or the region; the rings, centre out, are the tiers, and inside a ring the
   distance from the centre is the score on a log scale. A story with pictures shows its first one
   as a card in place of its sphere (a well-attested one fans up to three), loaded as the story comes
   near and fading out behind the camera. WASD and QE fly, the arrows look.
   NHI.corridor(C) builds the view; C is the controller from app.js. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};

  NHI.corridor = function (C) {
    const THREE = C.THREE, M = C.M, D = M.D;
    const BANDS = [[0.6, 3.9], [3.9, 6.5], [6.5, 9.3]];   // radial band of each tier, centre out
    const WARN = 0xff4d4d, NEUTRAL = 0x8fa3c8;
    const R = 10;              // corridor wall radius
    const ENTRY = 10;          // entrance length before the first gate
    const STORY_LEN = 3.6;     // corridor length one story adds to its year
    const YEAR_FLOOR = 0.12;   // every year gets this many story-lengths, so empty decades compress but never vanish
    const GAP = 8;             // gap before the undated chamber
    const UNDATED_LEN = 2.7;   // chamber length per undated story
    const FOG_CORRIDOR = 0.017, FOG_OVERVIEW = 0.0012;
    const SPEED = 15, TURN = 1.5, PITCH_MAX = 1.35, GLIDE = 7;
    const el = C.el, KIND_COLORS = M.KIND_COLORS, KIND_NAMES = M.KIND_NAMES;
    function angDelta(a, b) { let d = (b - a) % (2 * Math.PI); if (d > Math.PI) d -= 2 * Math.PI; if (d < -Math.PI) d += 2 * Math.PI; return d; }
    const damp = C.damp, ease = C.ease;

    // ---------- layout: density-warped time ----------
    const Y0 = D.eras[0].from, Y1 = D.eras[D.eras.length - 1].to;
    function eraOfYear(y) { for (let i = 0; i < D.eras.length; i++) if (y >= D.eras[i].from && y <= D.eras[i].to) return i; return -1; }
    const undated = [], yearBins = new Map();
    M.byTime.forEach(s => {
      if (!s.years) { undated.push(s); return; }
      let y = Math.floor((s.years.from + s.years.to) / 2);
      let ei = s.era ? M.eraById[s.era].index : eraOfYear(y);
      if (ei < 0) ei = y < Y0 ? 0 : D.eras.length - 1;   // a year outside every era sits at the nearest end
      const e = D.eras[ei];
      y = Math.min(e.to, Math.max(e.from, y));
      s._year = y;
      if (!yearBins.has(y)) yearBins.set(y, []);
      yearBins.get(y).push(s);
    });
    const yearStart = [], yearLen = [];
    {
      let d = ENTRY;
      for (let y = Y0; y <= Y1; y++) {
        const n = (yearBins.get(y) || []).length;
        yearStart.push(d); yearLen.push(STORY_LEN * (n + YEAR_FLOOR)); d += yearLen[yearLen.length - 1];
      }
    }
    const datedEnd = yearStart[Y1 - Y0] + yearLen[Y1 - Y0];
    const chamberStart = datedEnd + GAP;
    const chamberLen = Math.max(24, undated.length * UNDATED_LEN + 12);
    const totalLen = chamberStart + chamberLen;
    const eraStartD = D.eras.map(e => yearStart[e.from - Y0]);
    function yearToD(yf) {
      const y = Math.floor(yf), i = Math.min(Y1 - Y0, Math.max(0, y - Y0));
      return yearStart[i] + Math.min(1, Math.max(0, yf - y)) * yearLen[i];
    }
    function dToYear(d) {
      let lo = 0, hi = yearStart.length - 1;
      while (lo < hi) { const m = (lo + hi + 1) >> 1; if (yearStart[m] <= d) lo = m; else hi = m - 1; }
      return Y0 + lo;
    }
    function dToReadout(d) {
      if (d < ENTRY) return { year: "Entrance", era: "the corridor begins at " + Y0 };
      if (d >= datedEnd) return d >= chamberStart ? { year: "Undated", era: "the chamber of " + undated.length + " stories without years" } : { year: String(Y1), era: "end of the dated corridor" };
      const y = dToYear(d), e = D.eras[eraOfYear(y)], n = (yearBins.get(y) || []).length;
      return { year: String(y), era: (e ? e.name + " (" + e.from + " to " + e.to + ")" : "") + (n ? ", " + n + (n === 1 ? " story" : " stories") + " told about this year" : "") };
    }
    // within a year the stories share its length evenly, in time order
    yearBins.forEach((list, y) => {
      list.forEach((s, i) => { s._d = yearStart[y - Y0] + (i + 0.5 + YEAR_FLOOR / 2) / (list.length + YEAR_FLOOR) * yearLen[y - Y0]; });
    });
    undated.forEach((s, i) => { s._d = chamberStart + 6 + (i + 0.5) / undated.length * (chamberLen - 12); });

    // ---------- layout: cross-sections ----------
    function makeSectors(keys, weightOf, nameOf) {
      const total = keys.reduce((a, k) => a + weightOf(k), 0), scale = 2 * Math.PI / total;
      const w0 = weightOf(keys[0]) * scale;
      let cum = 0;
      return keys.map(k => {
        const w = weightOf(k) * scale;
        const sec = { key: k, name: nameOf(k), width: w, center: Math.PI / 2 - (cum + w / 2 - w0 / 2), start: Math.PI / 2 + w0 / 2 - cum };
        cum += w; return sec;
      });
    }
    const SECTORS = {
      kind: makeSectors(M.KINDS, () => 1, k => KIND_NAMES[k]),
      region: makeSectors(M.regionKeys, k => M.regionCounts.get(k) + 1.5, k => k),
    };
    const keyOf = { kind: s => s.kind, region: M.regionOf };
    const angleOf = { kind: new Map(), region: new Map() };
    ["kind", "region"].forEach(m => {
      SECTORS[m].forEach(sec => {
        const members = D.stories.filter(s => keyOf[m](s) === sec.key).sort((a, b) => M.hash(a.id + "a" + m) - M.hash(b.id + "a" + m));
        members.forEach((s, i) => angleOf[m].set(s.id, sec.center + ((i + 0.5) / members.length - 0.5) * sec.width * 0.8));
      });
    });
    // inside its tier's band, a story's distance from the centre line is its score on the log scale: nearer is stronger
    function radiusOf(s) {
      const b = BANDS[s._tier], inset = 0.35;
      return b[0] + inset + (1 - s._str) * (b[1] - b[0] - 2 * inset);
    }

    // ---------- three.js scene ----------
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x05070d);
    scene.fog = new THREE.FogExp2(0x05070d, FOG_CORRIDOR);
    const camera = new THREE.PerspectiveCamera(62, 1, 0.1, 2500);

    function canvasTex(w, h, draw) {
      const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h);
      const tex = new THREE.CanvasTexture(c); tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4; return tex;
    }
    function textSprite(text, size, color, weight) {
      const fontPx = 64, pad = 24;
      const meas = document.createElement("canvas").getContext("2d");
      const font = (weight || 600) + " " + fontPx + "px system-ui, -apple-system, Segoe UI, sans-serif";
      meas.font = font;
      const w = Math.ceil(meas.measureText(text).width) + pad * 2, h = fontPx + pad;
      const tex = canvasTex(w, h, (g) => { g.font = font; g.fillStyle = color; g.textBaseline = "middle"; g.fillText(text, pad, h / 2 + 2); });
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
      sp.scale.set(size * w / h, size, 1);
      return sp;
    }
    const haloTex = canvasTex(128, 128, (g, w, h) => {
      const gr = g.createRadialGradient(w / 2, h / 2, 0, w / 2, h / 2, w / 2);
      gr.addColorStop(0, "rgba(255,255,255,0.9)"); gr.addColorStop(0.25, "rgba(255,255,255,0.35)"); gr.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = gr; g.fillRect(0, 0, w, h);
    });

    // centre line and faint wall
    {
      const g = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0, 0, 2), new THREE.Vector3(0, 0, -totalLen)]);
      scene.add(new THREE.Line(g, new THREE.LineBasicMaterial({ color: 0xbfd0ff, transparent: true, opacity: 0.35 })));
      const w = new THREE.CylinderGeometry(R, R, totalLen, 72, 1, true);
      w.rotateX(Math.PI / 2); w.translate(0, 0, -totalLen / 2);
      scene.add(new THREE.Mesh(w, new THREE.MeshBasicMaterial({ color: 0x1a2440, transparent: true, opacity: 0.18, side: THREE.BackSide, depthWrite: false })));
    }
    const gateDepths = [ENTRY - 3].concat(eraStartD.slice(1).map(x => x + 2), [chamberStart + 2]);
    const decadeDepths = [];
    for (let y = Math.ceil((Y0 + 1) / 10) * 10; y <= Y1; y += 10) { const dd = yearStart[y - Y0] + 1.5; if (gateDepths.every(g => Math.abs(g - dd) > 12)) decadeDepths.push(dd); }

    // sector decorations, one group per cross-section, cross-faded on switch
    function buildDeco(m) {
      const grp = new THREE.Group();
      const pts = [];
      SECTORS[m].forEach(sec => { const a = sec.start; pts.push(new THREE.Vector3(R * Math.cos(a), R * Math.sin(a), 0), new THREE.Vector3(R * Math.cos(a), R * Math.sin(a), -totalLen)); });
      grp.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(pts), new THREE.LineBasicMaterial({ color: 0x3a4a78, transparent: true, opacity: 0.55 })));
      SECTORS[m].forEach(sec => {
        const a = sec.center, col = m === "kind" ? KIND_COLORS[sec.key] : "#c9d3ee";
        if (m === "kind") {
          grp.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(R * 0.985 * Math.cos(a), R * 0.985 * Math.sin(a), 0), new THREE.Vector3(R * 0.985 * Math.cos(a), R * 0.985 * Math.sin(a), -totalLen)]),
            new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.22 })));
        }
        const label = m === "region" ? sec.name + " " + M.regionCounts.get(sec.key) : sec.name;
        gateDepths.forEach((dd, j) => {
          const sp = textSprite(label, j === 0 ? 0.6 : 0.5, col, 600);
          sp.position.set((R - 1.0) * Math.cos(a), (R - 1.0) * Math.sin(a), -dd);
          sp.material.opacity = j === 0 ? 0.95 : 0.6;
          grp.add(sp);
        });
        decadeDepths.forEach(dd => {
          const sp = textSprite(label, 0.4, col, 600);
          sp.position.set((R - 0.9) * Math.cos(a), (R - 0.9) * Math.sin(a), -dd);
          sp.material.opacity = 0.38;
          grp.add(sp);
        });
      });
      grp.traverse(o => { if (o.material) o.userData.base = o.material.opacity; });
      scene.add(grp);
      return grp;
    }
    const deco = { kind: buildDeco("kind"), region: buildDeco("region") };
    function setDecoFade(grp, f) { grp.visible = f > 0.01; grp.traverse(o => { if (o.material) o.material.opacity = o.userData.base * f; }); }

    function ring(radius, dd, color, opacity, tube) {
      const m = new THREE.Mesh(new THREE.TorusGeometry(radius, tube, 8, 96), new THREE.MeshBasicMaterial({ color, transparent: true, opacity }));
      m.position.z = -dd; scene.add(m); return m;
    }
    const tierLoopGeo = [BANDS[0][1], BANDS[1][1]].map(r => {
      const p = []; for (let i = 0; i < 128; i++) { const a = i / 128 * 2 * Math.PI; p.push(new THREE.Vector3(r * Math.cos(a), r * Math.sin(a), 0)); }
      return new THREE.BufferGeometry().setFromPoints(p);
    });
    const tierLoopMat = new THREE.LineBasicMaterial({ color: 0x8ea4d8, transparent: true, opacity: 0.16, depthWrite: false });
    const tierLoopMatStrong = new THREE.LineBasicMaterial({ color: 0x9fb8ff, transparent: true, opacity: 0.32, depthWrite: false });
    function tierLoops(dd, strong) { tierLoopGeo.forEach(g => { const l = new THREE.LineLoop(g, strong ? tierLoopMatStrong : tierLoopMat); l.position.z = -dd; scene.add(l); }); }
    function tierLabels(dd, op) {
      M.TIERS.forEach((T, i) => {
        const sp = textSprite(T.name, 0.36, "#aebde6", 500); sp.material.opacity = op;
        const r = (BANDS[i][0] + BANDS[i][1]) / 2, a = -Math.PI / 2 + 0.16;
        sp.position.set(r * Math.cos(a), r * Math.sin(a), -dd); scene.add(sp);
      });
    }
    D.eras.forEach((e, i) => {
      const dd = eraStartD[i];
      ring(R, dd, 0x9fb8ff, 0.85, 0.07);
      ring(R + 0.6, dd, 0x9fb8ff, 0.35, 0.03);
      tierLoops(dd, true);
      tierLabels(dd + 0.01, 0.6);
      const t = textSprite(e.name, 1.3, "#e6ecff", 700); t.position.set(0, R + 1.95, -dd); scene.add(t);
      const n = D.stories.filter(s => s._year != null && s._year >= e.from && s._year <= e.to).length;
      const y = textSprite(e.from + " to " + e.to + ", " + n + (n === 1 ? " story" : " stories"), 0.8, "#9fb0d8", 500); y.position.set(0, R + 0.85, -dd); scene.add(y);
    });
    {
      let lastLabel = -1e9;
      for (let y = Y0 + 1; y <= Y1; y++) {
        const dd = yearStart[y - Y0], dense = (yearBins.get(y) || []).length > 0, decade = y % 10 === 0;
        if (D.eras.some(e => e.from === y)) { lastLabel = dd; continue; }
        if (!decade && !dense) continue;
        ring(R, dd, decade ? 0x3f5285 : 0x2a3760, decade ? 0.7 : 0.55, decade ? 0.03 : 0.02);
        if (decade) tierLoops(dd, false);
        if (dd - lastLabel >= 3.2) {
          const lab = textSprite(String(y), decade ? 0.7 : 0.55, decade ? "#8b99c2" : "#6d7aa3", 500);
          lab.position.set(0, -R - 0.7, -dd); scene.add(lab); lastLabel = dd;
        }
      }
    }
    ring(R, datedEnd, 0x9fb8ff, 0.5, 0.05);
    {
      ring(R, chamberStart, 0xd9a37a, 0.85, 0.08);
      ring(R + 0.6, chamberStart, 0xd9a37a, 0.35, 0.03);
      ring(R, totalLen, 0xd9a37a, 0.6, 0.06);
      tierLoops(chamberStart, true);
      tierLabels(chamberStart + 0.01, 0.6);
      const t = textSprite("Undated stories", 1.3, "#f3dcc8", 700); t.position.set(0, R + 1.95, -chamberStart); scene.add(t);
      const y = textSprite(undated.length + " stories without years", 0.8, "#c9ab92", 500); y.position.set(0, R + 0.85, -chamberStart); scene.add(y);
      const end = new THREE.Mesh(new THREE.CircleGeometry(R, 64), new THREE.MeshBasicMaterial({ color: 0x1a120c, transparent: true, opacity: 0.6 }));
      end.position.z = -totalLen; scene.add(end);
    }

    // stories: size, brightness and halo follow the tier first and the score second
    const sphereGeo = new THREE.SphereGeometry(1, 20, 14);
    const hitMat = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false, colorWrite: false });
    const hitTargets = [];
    const nodes = new Map();
    // a story with pictures shows a card in place of its sphere (the sphere shrinks to a dot, the
    // halo stays as the tier's glow behind the card); the pictures are asked for when the story
    // comes within CARD_AHEAD and fade in over CARD_FADE, out again just behind the camera
    const cards = NHI.cards(THREE);
    const CARD_AHEAD = 90, CARD_FADE = 25, CARD_BEHIND = 4;
    D.stories.forEach(s => {
      const kc = new THREE.Color(KIND_COLORS[s.kind]);
      const mesh = new THREE.Mesh(sphereGeo, new THREE.MeshBasicMaterial({ color: kc.clone(), transparent: true }));
      scene.add(mesh);
      const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: haloTex, color: kc, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      scene.add(halo);
      const hit = new THREE.Mesh(sphereGeo, hitMat);
      hit.userData.sid = s.id; scene.add(hit); hitTargets.push(hit);
      const n = { s, pos: new THREE.Vector3(), mesh, halo, hit, kc, base: new THREE.Color(), size: 1, baseOpacity: 1, baseHalo: 0, haloMul: 3,
        cur: 1, want: 1, r: 0, aK: angleOf.kind.get(s.id), aR: angleOf.region.get(s.id),
        pics: cards.pictures(s), cards: [], asked: false, cardH: 0 };
      n.pics.forEach(() => { const c = cards.card(kc); scene.add(c.pic); scene.add(c.frame); n.cards.push(c); });
      nodes.set(s.id, n);
    });
    function askCards(n) {
      n.asked = true;
      cards.request(n.s, got => got.forEach((entry, i) => { if (!n.cards[i].image) cards.give(n.cards[i], entry); }));
    }
    function placeCards(n) {
      // the first card sits on the story, the sphere a dot at its foot; further cards fan to the
      // right, each past the previous one's edge, a little lower and further back
      let x = n.pos.x, prevHalf = 0;
      n.cards.forEach((c, i) => {
        const w = c.pic.scale.x, h = c.pic.scale.y;
        if (i) x += prevHalf + h * 0.12 + w / 2;
        prevHalf = w / 2;
        c.pic.position.set(x, n.pos.y - i * n.cards[0].pic.scale.y * 0.18, n.pos.z - i * 0.3);
        c.frame.position.copy(c.pic.position); c.frame.position.z -= 0.02;
      });
      n.mesh.position.set(n.pos.x, n.pos.y - n.cards[0].pic.scale.y * 0.5 - n.mesh.scale.y * 0.6, n.pos.z + 0.05);
    }
    function styleNodes() {
      nodes.forEach(n => {
        const s = n.s, T = M.TIERS[s._tier], str = s._str;
        n.size = T.size * (0.17 + 0.36 * Math.pow(str, 1.2));
        n.base.copy(n.kc).multiplyScalar(T.bright * (0.55 + 0.45 * str));
        n.baseOpacity = Math.min(1, T.bright * (0.55 + 0.45 * str) + (s._tier === 0 ? 0.15 : 0));
        n.baseHalo = s._tier === 0 ? 0.45 + 0.4 * str : s._tier === 1 ? 0.18 + 0.3 * str : 0.05 + 0.12 * str;
        n.haloMul = s._tier === 0 ? 4.5 : s._tier === 1 ? 3.2 : 2.4;
        n.cardH = n.pics.length ? (s._tier === 0 ? 2.3 : s._tier === 1 ? 1.7 : 1.25) * (0.75 + 0.25 * str) : 0;
        n.hit.scale.setScalar(Math.max(0.55, n.size * 1.8, n.cardH * 0.6));
      });
    }

    // links as chords bowed toward the centre line
    const linkObjs = [];
    M.links.forEach(l => {
      const warn = l.relation === "contradicts";
      const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.BufferAttribute(new Float32Array(29 * 3), 3));
      const mat = warn ? new THREE.LineDashedMaterial({ color: WARN, dashSize: 0.5, gapSize: 0.3, transparent: true, opacity: 0.9 })
                       : new THREE.LineBasicMaterial({ color: NEUTRAL, transparent: true, opacity: 0.55 });
      const line = new THREE.Line(g, mat);
      scene.add(line); linkObjs.push({ l, line, warn, base: mat.opacity });
    });
    const _mid = new THREE.Vector3(), _curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3());
    function updateLinks() {
      linkObjs.forEach(o => {
        const a = nodes.get(o.l.a).pos, b = nodes.get(o.l.b).pos;
        _mid.copy(a).add(b).multiplyScalar(0.5);
        _curve.v0.copy(a); _curve.v1.set(_mid.x * 0.35, _mid.y * 0.35, _mid.z); _curve.v2.copy(b);
        const pts = _curve.getPoints(28), arr = o.line.geometry.attributes.position.array;
        pts.forEach((p, i) => { arr[i * 3] = p.x; arr[i * 3 + 1] = p.y; arr[i * 3 + 2] = p.z; });
        o.line.geometry.attributes.position.needsUpdate = true;
        o.line.geometry.computeBoundingSphere();
        if (o.warn) o.line.computeLineDistances();
      });
    }

    let angleMode = "kind", angleBlend = 0, angleFrom = 0, angleTo = 0, angleT = 1;
    let selectedSid = null, focusSid = null;
    const selRing = new THREE.Mesh(new THREE.RingGeometry(1.5, 1.6, 64), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, side: THREE.DoubleSide, depthWrite: false }));
    selRing.visible = false; scene.add(selRing);
    function placeNodes() {
      const e = ease(Math.min(1, Math.max(0, angleBlend)));
      nodes.forEach(n => {
        const a = n.aK + angDelta(n.aK, n.aR) * e;
        n.pos.set(n.r * Math.cos(a), n.r * Math.sin(a), -n.s._d);
        n.mesh.position.copy(n.pos); n.halo.position.copy(n.pos); n.hit.position.copy(n.pos);
      });
      updateLinks();
      setDecoFade(deco.kind, 1 - e); setDecoFade(deco.region, e);
      if (selectedSid) selRing.position.copy(nodes.get(selectedSid).pos);
    }
    styleNodes();
    nodes.forEach(n => { n.r = radiusOf(n.s); });
    placeNodes();

    // ---------- legend part: the angle switch and the compass ----------
    const ns = "http://www.w3.org/2000/svg";
    function svgEl(tag, attrs) { const n = document.createElementNS(ns, tag); for (const k in attrs) n.setAttribute(k, attrs[k]); return n; }
    function drawCompass() {
      const svg = document.getElementById("compass");
      svg.innerHTML = "";
      svg.appendChild(svgEl("circle", { r: 34, fill: "none", stroke: "rgba(150,170,220,0.3)" }));
      [BANDS[0][1], BANDS[1][1]].forEach(r => svg.appendChild(svgEl("circle", { r: (34 * r / R).toFixed(1), fill: "none", stroke: "rgba(150,170,220,0.18)", "stroke-dasharray": "2 2" })));
      svg.appendChild(svgEl("circle", { r: 2.5, fill: "#bfd0ff" }));
      SECTORS[angleMode].forEach(sec => {
        const a = sec.start, isKind = angleMode === "kind", n = isKind ? (M.kindCounts[sec.key] || 0) : M.regionCounts.get(sec.key);
        svg.appendChild(svgEl("line", { x1: (30 * Math.cos(a)).toFixed(1), y1: (-30 * Math.sin(a)).toFixed(1), x2: (38 * Math.cos(a)).toFixed(1), y2: (-38 * Math.sin(a)).toFixed(1), stroke: "rgba(150,170,220,0.45)" }));
        const dot = svgEl("circle", { cx: (34 * Math.cos(sec.center)).toFixed(1), cy: (-34 * Math.sin(sec.center)).toFixed(1),
          r: isKind ? 4.5 : (1.8 + 1.1 * Math.sqrt(n)).toFixed(1), fill: isKind ? KIND_COLORS[sec.key] : "#c9d3ee", opacity: isKind ? 1 : 0.8 });
        dot.appendChild(svgEl("title", {})).textContent = sec.name + ", " + n;
        svg.appendChild(dot);
      });
      document.querySelectorAll("#angle-seg button").forEach(b => b.classList.toggle("on", b.dataset.m === angleMode));
      document.getElementById("compass-note").textContent = angleMode === "kind" ? "The angle around you is the kind of story." : "The angle around you is the region; sectors sized by story count.";
    }
    function setAngleMode(m, instant) {
      if (m === angleMode && !instant) return;
      angleMode = m; angleFrom = angleBlend; angleTo = m === "region" ? 1 : 0; angleT = instant ? 1 : 0;
      if (instant) { angleBlend = angleTo; placeNodes(); }
      drawCompass();
    }
    document.querySelectorAll("#angle-seg button").forEach(b => b.addEventListener("click", () => setAngleMode(b.dataset.m)));
    drawCompass();

    // ---------- flight ----------
    const START = { pos: new THREE.Vector3(0, 0, 15) };
    const fl = { pos: START.pos.clone(), yaw: 0, pitch: 0, vel: new THREE.Vector3(), yawV: 0, pitchV: 0 };
    let auto = null, glide = false, pendingScroll = 0, tween = null;
    const ov = { az: Math.PI / 2 - 0.3, el: 0.5, dist: totalLen * 0.74 };
    let mode = "corridor", modeBlend = 0;
    function fwd(yaw, pitch) { return new THREE.Vector3(-Math.sin(yaw) * Math.cos(pitch), Math.sin(pitch), -Math.cos(yaw) * Math.cos(pitch)); }
    function clampFlight() {
      const r = Math.hypot(fl.pos.x, fl.pos.y), rmax = R - 0.7;
      if (r > rmax) {
        fl.pos.x *= rmax / r; fl.pos.y *= rmax / r;
        const nx = fl.pos.x / rmax, ny = fl.pos.y / rmax, vr = fl.vel.x * nx + fl.vel.y * ny;
        if (vr > 0) { fl.vel.x -= vr * nx; fl.vel.y -= vr * ny; }
      }
      const zmin = -(totalLen - 2), zmax = 22;
      if (fl.pos.z < zmin) { fl.pos.z = zmin; fl.vel.z = Math.max(0, fl.vel.z); }
      if (fl.pos.z > zmax) { fl.pos.z = zmax; fl.vel.z = Math.min(0, fl.vel.z); }
      fl.pitch = Math.min(PITCH_MAX, Math.max(-PITCH_MAX, fl.pitch));
      ov.el = Math.min(1.4, Math.max(-0.5, ov.el));
      ov.dist = Math.min(totalLen * 1.7, Math.max(25, ov.dist));
    }
    function setMode(m) { mode = m; document.getElementById("btn-overview").classList.toggle("on", m === "overview"); }
    function startAuto(pos, yaw, pitch, label) { glide = false; tween = null; C.leaveRail(); auto = { pos, yaw, pitch, label }; setMode("corridor"); }
    function stopAuto() { auto = null; tween = null; }
    function storyPose(sid) {
      const p = nodes.get(sid).pos, pos = new THREE.Vector3(p.x * 0.4, p.y * 0.4, p.z + 9);
      const dx = p.x - pos.x, dy = p.y - pos.y, dz = p.z - pos.z;
      // the yaw stays continuous so the turn takes the short way round
      return { pos, yaw: fl.yaw + angDelta(fl.yaw, Math.atan2(-dx, -dz)), pitch: Math.atan2(dy, Math.hypot(dx, dz)) };
    }
    function flyTo(sid, instant) {
      const P = storyPose(sid);
      if (instant) { stopAuto(); fl.pos.copy(P.pos); fl.yaw = P.yaw; fl.pitch = P.pitch; fl.vel.set(0, 0, 0); setMode("corridor"); return; }
      startAuto(P.pos, P.yaw, P.pitch, "flying to the story");
    }
    function flyToDepth(d) { startAuto(new THREE.Vector3(0, 0, -(d - 8)), fl.yaw + angDelta(fl.yaw, 0), 0, "flying"); }
    function resetStart() { startAuto(START.pos.clone(), fl.yaw + angDelta(fl.yaw, 0), 0, "returning to the start"); }

    // rails: a cubic Hermite move whose start tangent is the free-flight velocity, so the handoff has no jolt
    function herm(p0, p1, m0, s) { const s2 = s * s, s3 = s2 * s; return (2 * s3 - 3 * s2 + 1) * p0 + (s3 - 2 * s2 + s) * m0 + (3 * s2 - 2 * s3) * p1; }
    function hermD(p0, p1, m0, s, dur) { const s2 = s * s; return ((6 * s2 - 6 * s) * p0 + (3 * s2 - 4 * s + 1) * m0 + (6 * s - 6 * s2) * p1) / dur; }
    function railArrive(sid, instant) {
      const pose = storyPose(sid);
      if (instant) { tween = null; auto = null; fl.pos.copy(pose.pos); fl.yaw = pose.yaw; fl.pitch = pose.pitch; fl.vel.set(0, 0, 0); fl.yawV = fl.pitchV = 0; setMode("corridor"); return; }
      const dist = fl.pos.distanceTo(pose.pos), dur = 0.7 + Math.min(0.5, dist / 500);
      // the velocity term peaks at a third of the move, so free-flight momentum fades out over about 0.3 s
      const m0 = fl.vel.clone().multiplyScalar(dur); const cap = 2 + dist * 0.6; if (m0.length() > cap) m0.setLength(cap);
      tween = { p0: fl.pos.clone(), p1: pose.pos, m0, y0: fl.yaw, y1: pose.yaw, my: fl.yawV * dur, q0: fl.pitch, q1: pose.pitch, mq: fl.pitchV * dur, t: 0, dur };
      auto = null; glide = false; pendingScroll = 0; setMode("corridor");
    }
    function stepTween(dt) {
      const T = tween; T.t += dt; const s = Math.min(1, T.t / T.dur);
      fl.pos.set(herm(T.p0.x, T.p1.x, T.m0.x, s), herm(T.p0.y, T.p1.y, T.m0.y, s), herm(T.p0.z, T.p1.z, T.m0.z, s));
      fl.vel.set(hermD(T.p0.x, T.p1.x, T.m0.x, s, T.dur), hermD(T.p0.y, T.p1.y, T.m0.y, s, T.dur), hermD(T.p0.z, T.p1.z, T.m0.z, s, T.dur));
      fl.yaw = herm(T.y0, T.y1, T.my, s); fl.yawV = hermD(T.y0, T.y1, T.my, s, T.dur);
      fl.pitch = herm(T.q0, T.q1, T.mq, s); fl.pitchV = hermD(T.q0, T.q1, T.mq, s, T.dur);
      if (s >= 1) { tween = null; fl.vel.set(0, 0, 0); fl.yawV = fl.pitchV = 0; }
    }
    // releasing keeps the tween's instantaneous velocity in fl.vel, so free flight starts from it
    function railRelease() { tween = null; }
    function nearestStory() {
      const dir = new THREE.Vector3(); camera.getWorldDirection(dir);
      const v = new THREE.Vector3();
      let best = null, bs = Infinity, near = null, nd = Infinity;
      nodes.forEach((n, id) => {
        if (!n.mesh.visible) return;
        v.copy(n.pos).sub(camera.position);
        const dist = v.length(); if (dist < nd) { nd = dist; near = id; }
        const along = v.dot(dir); if (along < 1) return;
        const score = v.addScaledVector(dir, -along).length() + 0.12 * along;
        if (score < bs) { bs = score; best = id; }
      });
      return best || near;
    }

    // ---------- input ----------
    const canvas = C.canvas;
    let active = false, dragging = null;
    const ndc = new THREE.Vector2(), raycaster = new THREE.Raycaster();
    function pick(cx, cy) {
      const rect = canvas.getBoundingClientRect();
      ndc.set((cx - rect.left) / rect.width * 2 - 1, -(cy - rect.top) / rect.height * 2 + 1);
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObjects(hitTargets.filter(h => h.visible), false);
      return hits.length ? hits[0].object.userData.sid : null;
    }
    // touch: one finger looks (and taps a story), two fingers dragged up or down move along time in the
    // corridor and pinch the overview's distance; a second finger ends the one-finger drag and its tap
    const touches = new Map();   // pointerId to its last point
    let twoF = null;
    function twoFingers() { const [a, b] = [...touches.values()]; return { my: (a.y + b.y) / 2, dist: Math.max(1, Math.hypot(a.x - b.x, a.y - b.y)) }; }
    canvas.addEventListener("pointerdown", e => {
      if (!active) return;
      canvas.setPointerCapture(e.pointerId);
      if (e.pointerType === "touch") {
        touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (touches.size >= 2) { dragging = null; canvas.classList.remove("dragging"); C.hover(null); twoF = touches.size === 2 ? twoFingers() : null; return; }
      }
      dragging = { x: e.clientX, y: e.clientY, sx: e.clientX, sy: e.clientY, moved: false };
    });
    canvas.addEventListener("pointermove", e => {
      if (!active) return;
      if (touches.has(e.pointerId)) {
        touches.set(e.pointerId, { x: e.clientX, y: e.clientY });
        if (touches.size >= 2) {
          if (twoF && touches.size === 2) {
            const s = twoFingers(), dy = s.my - twoF.my;
            if (mode === "corridor") { auto = null; tween = null; C.leaveRail(); pendingScroll -= dy * 0.06; }
            else { ov.dist *= twoF.dist / s.dist; clampFlight(); }
            twoF = s; C.usedOnce();
          }
          return;
        }
      }
      if (dragging) {
        const dx = e.clientX - dragging.x, dy = e.clientY - dragging.y;
        dragging.x = e.clientX; dragging.y = e.clientY;
        if (Math.hypot(e.clientX - dragging.sx, e.clientY - dragging.sy) > 5) { dragging.moved = true; canvas.classList.add("dragging"); }
        if (dragging.moved) {
          if (mode === "corridor") { auto = null; tween = null; fl.yaw -= dx * 0.0042; fl.pitch -= dy * 0.0042; }
          else { ov.az -= dx * 0.005; ov.el += dy * 0.004; }
          clampFlight(); C.usedOnce();
        }
        return;
      }
      C.hover(pick(e.clientX, e.clientY), e.clientX, e.clientY);
    });
    function release(e, mayClick) {
      touches.delete(e.pointerId);
      if (touches.size < 2) twoF = null;
      if (!active) return;
      const wasClick = mayClick && dragging && !dragging.moved;
      dragging = null; canvas.classList.remove("dragging");
      if (wasClick) { const sid = pick(e.clientX, e.clientY); if (sid) C.select(sid, { fly: true }); }
    }
    canvas.addEventListener("pointerup", e => release(e, true));
    canvas.addEventListener("pointercancel", e => release(e, false));
    canvas.addEventListener("pointerleave", () => { if (active && !dragging) C.hover(null); });
    canvas.addEventListener("wheel", e => {
      if (!active) return;
      e.preventDefault();
      const dy = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaMode === 2 ? e.deltaY * 400 : e.deltaY;
      if (mode === "corridor") { auto = null; tween = null; C.leaveRail(); pendingScroll += dy * 0.045; C.usedOnce(); }
      else { ov.dist *= Math.exp(dy * 0.0012); clampFlight(); }
    }, { passive: false });

    const keys = new Set();
    const MOVE_CODES = ["KeyW", "KeyA", "KeyS", "KeyD", "KeyQ", "KeyE", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"];
    function keydown(e) {
      const c = e.code;
      if (c === "Home" || c === "KeyR") { e.preventDefault(); resetStart(); C.usedOnce(); return true; }
      if (c === "KeyO") { setMode(mode === "overview" ? "corridor" : "overview"); stopAuto(); return true; }
      if (c === "KeyC") { setAngleMode(angleMode === "kind" ? "region" : "kind"); return true; }
      if (c === "Space") {
        e.preventDefault();
        if (auto || tween) { stopAuto(); glide = false; } else if (!C.onRail()) glide = !glide;
        if (glide) setMode("corridor");
        C.usedOnce(); return true;
      }
      if (c === "PageDown" || c === "PageUp") {
        e.preventDefault();
        const marks = eraStartD.concat([chamberStart]), cur = -fl.pos.z + 8;
        const d = c === "PageDown" ? (marks.find(m => m > cur + 1) ?? cur) : ([...marks].reverse().find(m => m < cur - 1) ?? 0);
        flyToDepth(d); return true;
      }
      if (c === "ShiftLeft" || c === "ShiftRight") { keys.add("Shift"); return true; }
      if (MOVE_CODES.includes(c)) {
        e.preventDefault(); keys.add(c); C.usedOnce();
        auto = null; tween = null;
        if (!c.startsWith("Arrow")) C.leaveRail();   // a flight key leaves the rail; the arrows only look around
        if (c === "KeyW" || c === "KeyS") glide = false;
        return true;
      }
      return false;
    }
    function keyup(e) { keys.delete(e.code); if (e.key === "Shift") keys.delete("Shift"); }
    function escape() { if (mode === "overview") { setMode("corridor"); return true; } return false; }
    document.getElementById("btn-start").addEventListener("click", resetStart);
    document.getElementById("btn-overview").addEventListener("click", () => { stopAuto(); setMode(mode === "overview" ? "corridor" : "overview"); });

    // ---------- emphasis, filters, knob ----------
    function setEmphasis(focus) {
      focusSid = focus;
      const lit = focus ? M.sharing(focus) : null;
      const linked = new Set(focus ? M.linksOf(focus).map(r => r.other) : []);
      nodes.forEach((n, id) => {
        if (!focus) n.want = 1;
        else if (id === focus) n.want = 2.2;
        else if (lit.has(id) || linked.has(id)) n.want = 1.9;
        else n.want = 0.25;
      });
      linkObjs.forEach(o => { o.line.material.opacity = !focus ? o.base : (o.l.a === focus || o.l.b === focus) ? 1 : o.base * 0.25; });
    }
    function applyVisibility() {
      nodes.forEach(n => { const v = M.isVisible(n.s); n.mesh.visible = n.halo.visible = n.hit.visible = v; n.shown = v; });
      linkObjs.forEach(o => { o.line.visible = M.isVisible(M.storyById[o.l.a]) && M.isVisible(M.storyById[o.l.b]); });
      drawMinimapStatic();
    }
    function restyle() { styleNodes(); drawMinimapStatic(); }   // the radii follow s._str through the frame loop
    function setSelected(sid) {
      selectedSid = sid;
      if (!sid) { selRing.visible = false; return; }
      const n = nodes.get(sid);
      selRing.visible = true; selRing.position.copy(n.pos); selRing.scale.setScalar(Math.max(0.45, n.size * 1.35, n.cardH * 0.5));
    }

    // ---------- minimap ----------
    const mm = document.getElementById("minimap"), mmTip = document.getElementById("mm-tip");
    const mmStatic = document.createElement("canvas");
    let mmW = 0, mmH = 0, mmDpr = 1;
    const MM_PAD = 4;
    function mmX(d) { return MM_PAD + d / totalLen * (mmW - 2 * MM_PAD); }
    function mmD(x) { return Math.min(totalLen - 4, Math.max(0, (x - MM_PAD) / (mmW - 2 * MM_PAD) * totalLen)); }
    function drawMinimapStatic() {
      if (!mmW) return;
      mmStatic.width = mmW * mmDpr; mmStatic.height = mmH * mmDpr;
      const g = mmStatic.getContext("2d"); g.setTransform(mmDpr, 0, 0, mmDpr, 0, 0);
      g.clearRect(0, 0, mmW, mmH);
      const laneTop = 15, laneH = mmH - laneTop - 13;
      g.fillStyle = "rgba(255,255,255,0.03)"; g.fillRect(mmX(0), laneTop, mmX(totalLen) - mmX(0), laneH);
      D.eras.forEach((e, i) => {
        const x0 = mmX(eraStartD[i]), x1 = mmX(i + 1 < D.eras.length ? eraStartD[i + 1] : datedEnd);
        g.fillStyle = i % 2 ? "rgba(159,184,255,0.06)" : "rgba(159,184,255,0.12)"; g.fillRect(x0, laneTop, x1 - x0, laneH);
        g.fillStyle = "rgba(159,184,255,0.8)"; g.fillRect(x0, laneTop - 2, 1, laneH + 2);
        g.font = "600 10.5px system-ui, sans-serif"; g.fillStyle = "#b6c3e8"; g.textBaseline = "alphabetic";
        const name = e.name, room = x1 - x0 - 6;
        let txt = name; while (txt.length > 3 && g.measureText(txt).width > room) txt = txt.slice(0, -2);
        if (txt !== name) txt = txt.replace(/\s+$/, "") + "…";
        if (room > 18) g.fillText(txt, x0 + 4, laneTop - 4);
      });
      { const x0 = mmX(chamberStart), x1 = mmX(totalLen);
        g.fillStyle = "rgba(217,163,122,0.12)"; g.fillRect(x0, laneTop, x1 - x0, laneH);
        g.fillStyle = "rgba(217,163,122,0.9)"; g.fillRect(x0, laneTop - 2, 1, laneH + 2);
        g.font = "600 10.5px system-ui, sans-serif"; g.fillStyle = "#e5c6ad"; g.fillText("Undated", x0 + 4, laneTop - 4); }
      // tier lanes: well attested on top
      for (let i = 1; i < 3; i++) { g.fillStyle = "rgba(150,170,220,0.08)"; g.fillRect(mmX(0), laneTop + laneH * i / 3, mmX(totalLen) - mmX(0), 1); }
      D.stories.forEach(s => {
        if (!M.isVisible(s)) return;
        const x = mmX(s._d), y = laneTop + laneH * (s._tier + 0.5) / 3 + (M.hash(s.id + "m") - 0.5) * laneH / 3 * 0.6;
        g.fillStyle = KIND_COLORS[s.kind]; g.globalAlpha = M.TIERS[s._tier].bright * (0.6 + 0.4 * s._str);
        g.beginPath(); g.arc(x, y, M.TIERS[s._tier].size * (1.3 + 1.4 * s._str), 0, 2 * Math.PI); g.fill();
      });
      g.globalAlpha = 1;
      g.font = "10px system-ui, sans-serif"; g.fillStyle = "#6f7ca3"; g.textBaseline = "top";
      let lastX = -1e9;
      for (let y = Math.ceil(Y0 / 10) * 10; y <= Y1; y += 10) {
        const x = mmX(yearStart[y - Y0]);
        g.fillStyle = "rgba(150,170,220,0.35)"; g.fillRect(x, laneTop + laneH, 1, 3);
        if (x - lastX > 30) { g.fillStyle = "#6f7ca3"; g.fillText(String(y), x - 11, laneTop + laneH + 2); lastX = x; }
      }
      mmLast = "";
    }
    let mmLast = "";
    function drawMinimap() {
      if (!mmW) return;
      const camD = -camera.position.z, look = new THREE.Vector3(); camera.getWorldDirection(look);
      const key = camD.toFixed(1) + "|" + look.z.toFixed(2) + "|" + mode + "|" + (auto ? 1 : 0);
      if (key === mmLast) return; mmLast = key;
      const g = mm.getContext("2d"); g.setTransform(1, 0, 0, 1, 0, 0);
      g.clearRect(0, 0, mm.width, mm.height); g.drawImage(mmStatic, 0, 0);
      g.setTransform(mmDpr, 0, 0, mmDpr, 0, 0);
      const laneTop = 15, laneH = mmH - laneTop - 13;
      if (mode === "overview") { g.fillStyle = "rgba(255,255,255,0.06)"; g.fillRect(mmX(0), laneTop, mmX(totalLen) - mmX(0), laneH); return; }
      const x = mmX(Math.max(0, Math.min(totalLen, camD)));
      const reach = 40 * Math.max(0.15, Math.abs(look.z)) / totalLen * (mmW - 2 * MM_PAD), dir = look.z <= 0 ? 1 : -1;
      const grad = g.createLinearGradient(x, 0, x + dir * reach, 0);
      grad.addColorStop(0, "rgba(255,255,255,0.28)"); grad.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = grad; g.fillRect(Math.min(x, x + dir * reach), laneTop, reach, laneH);
      g.fillStyle = "#ffffff"; g.fillRect(x - 1, laneTop - 3, 2, laneH + 6);
      g.beginPath(); g.moveTo(x - 5, laneTop - 7); g.lineTo(x + 5, laneTop - 7); g.lineTo(x, laneTop - 1); g.closePath(); g.fill();
    }
    function resizeMinimap() {
      const r = mm.getBoundingClientRect(); mmDpr = Math.min(2, window.devicePixelRatio || 1);
      if (!r.width) return;
      mmW = Math.max(50, Math.round(r.width)); mmH = Math.round(r.height);
      mm.width = mmW * mmDpr; mm.height = mmH * mmDpr;
      drawMinimapStatic(); drawMinimap();
    }
    let mmDrag = false;
    function mmJump(e) { const r = mm.getBoundingClientRect(); flyToDepth(mmD(e.clientX - r.left)); C.usedOnce(); }
    mm.addEventListener("pointerdown", e => { mmDrag = true; mm.setPointerCapture(e.pointerId); mmJump(e); });
    mm.addEventListener("pointermove", e => {
      const r = mm.getBoundingClientRect(), ro = dToReadout(mmD(e.clientX - r.left));
      mmTip.textContent = ro.year + (/^\d/.test(ro.year) ? ", " + ro.era.split(" (")[0] : "");
      mmTip.style.display = "block"; mmTip.style.left = e.clientX + "px"; mmTip.style.top = (r.top - 6) + "px";
      if (mmDrag) mmJump(e);
    });
    mm.addEventListener("pointerup", () => { mmDrag = false; });
    mm.addEventListener("pointerleave", () => { mmTip.style.display = "none"; });

    // ---------- labels: well attested from afar, told once only near ----------
    const tmpV = new THREE.Vector3(), camDir = new THREE.Vector3();
    function labelCandidates(w, h) {
      camera.getWorldDirection(camDir);
      const out = [], overview = modeBlend > 0.5;
      nodes.forEach((n, id) => {
        if (!n.mesh.visible || id === C.hoverSid()) return;
        const T = M.TIERS[n.s._tier];
        const ahead = tmpV.copy(n.pos).sub(camera.position).dot(camDir);
        const sel = id === selectedSid;
        if (!sel) {
          if (overview) { if (n.s._tier !== 0) return; }
          else if (ahead < 1.5 || ahead > T.labelAt) return;
        }
        tmpV.copy(n.pos);
        if (n.cards.length && n.cards[0].pic.visible) tmpV.y -= n.cards[0].pic.scale.y * 0.5 + 0.1;
        tmpV.project(camera);
        if (tmpV.z > 1 || Math.abs(tmpV.x) > 0.95 || Math.abs(tmpV.y) > 0.92) return;
        out.push({ id, x: (tmpV.x + 1) / 2 * w, y: (1 - tmpV.y) / 2 * h, rank: (sel ? 100 : 0) + (3 - n.s._tier) * 10 + n.s._str * 5 - (overview ? 0 : ahead * 0.05) });
      });
      return out;
    }

    // ---------- frame ----------
    const vTarget = new THREE.Vector3(), fwdH = new THREE.Vector3(), rightH = new THREE.Vector3();
    const flightLook = new THREE.Vector3(), ovPos = new THREE.Vector3(), ovLook = new THREE.Vector3(), camLook = new THREE.Vector3();
    const yearEl = document.getElementById("year"), eraEl = document.getElementById("era-name"), statusEl = document.getElementById("status");
    let lastReadout = "", lastStatus = "";
    function frame(dt, now) {
      const k = (c) => keys.has(c) ? 1 : 0;
      if (mode === "corridor") {
        const yawIn = k("ArrowLeft") - k("ArrowRight"), pitchIn = k("ArrowUp") - k("ArrowDown");
        fl.yawV += (yawIn * TURN - fl.yawV) * damp(10, dt);
        fl.pitchV += (pitchIn * TURN * 0.8 - fl.pitchV) * damp(10, dt);
        fl.yaw += fl.yawV * dt; fl.pitch += fl.pitchV * dt;
        fwdH.set(-Math.sin(fl.yaw), 0, -Math.cos(fl.yaw)); rightH.set(Math.cos(fl.yaw), 0, -Math.sin(fl.yaw));
        vTarget.set(0, 0, 0).addScaledVector(fwdH, k("KeyW") - k("KeyS")).addScaledVector(rightH, k("KeyD") - k("KeyA"));
        vTarget.y += k("KeyQ") - k("KeyE");
        if (vTarget.lengthSq() > 1) vTarget.normalize();
        vTarget.multiplyScalar(SPEED * (keys.has("Shift") ? 2 : 1));
        if (glide && !auto) vTarget.z -= GLIDE * (keys.has("Shift") ? 2 : 1);
        fl.vel.lerp(vTarget, damp(6, dt));
        fl.pos.addScaledVector(fl.vel, dt);
        const take = pendingScroll * damp(9, dt); pendingScroll -= take; fl.pos.z -= take;
        if (auto) {
          const a = damp(3.2, dt);
          fl.pos.lerp(auto.pos, a); fl.yaw += (auto.yaw - fl.yaw) * a; fl.pitch += (auto.pitch - fl.pitch) * a;
          if (fl.pos.distanceTo(auto.pos) < 0.04 && Math.abs(auto.yaw - fl.yaw) < 0.002 && Math.abs(auto.pitch - fl.pitch) < 0.002) auto = null;
        }
        if (tween) stepTween(dt);
        clampFlight();
        if (glide && fl.pos.z <= -(totalLen - 2.5)) glide = false;
      } else {
        const orb = k("ArrowLeft") + k("KeyA") - k("ArrowRight") - k("KeyD"), elv = k("ArrowUp") + k("KeyQ") - k("ArrowDown") - k("KeyE"), zm = k("KeyS") - k("KeyW");
        ov.az += orb * 0.9 * dt; ov.el += elv * 0.6 * dt; ov.dist *= Math.exp(zm * 0.9 * dt);
        clampFlight();
      }
      modeBlend += ((mode === "overview" ? 1 : 0) - modeBlend) * damp(3.5, dt);
      const mb = ease(Math.min(1, Math.max(0, modeBlend)));
      flightLook.copy(fl.pos).add(fwd(fl.yaw, fl.pitch).multiplyScalar(10));
      const cz = -totalLen / 2;
      ovLook.set(0, -8, cz + totalLen * 0.17);
      ovPos.set(ov.dist * Math.sin(ov.az) * Math.cos(ov.el), ov.dist * Math.sin(ov.el), cz + ov.dist * Math.cos(ov.az) * Math.cos(ov.el));
      camera.position.copy(fl.pos).lerp(ovPos, mb);
      camLook.copy(flightLook).lerp(ovLook, mb);
      camera.lookAt(camLook);
      scene.fog.density = FOG_CORRIDOR + (FOG_OVERVIEW - FOG_CORRIDOR) * mb;
      const boost = 1 + 2.4 * mb;

      if (angleT < 1) { angleT = Math.min(1, angleT + dt / 1.1); angleBlend = angleFrom + (angleTo - angleFrom) * angleT; placeNodes(); }
      // the knob moves a story's radius inside its tier's band; the move is animated
      let moved = false;
      nodes.forEach(n => { const want = radiusOf(n.s), d = want - n.r; if (Math.abs(d) > 1e-3) { n.r += d * damp(6, dt); moved = true; } else n.r = want; });
      if (moved) placeNodes();

      const camZ = camera.position.z;
      nodes.forEach(n => {
        n.cur += (n.want - n.cur) * damp(10, dt);
        const e = n.cur;
        let dot = 1;   // a story whose card is up shrinks its sphere to a dot
        if (n.cards.length) {
          const ahead = camZ - n.pos.z;   // distance along the corridor, positive ahead of the camera
          if (!n.asked && ahead < CARD_AHEAD + 30 && ahead > -CARD_BEHIND * 2) askCards(n);
          const zone = mb > 0.5 ? 1 : Math.min(1, Math.max(0, (CARD_AHEAD - ahead) / CARD_FADE)) * Math.min(1, Math.max(0, (ahead + CARD_BEHIND) / CARD_BEHIND));
          const op = (n.shown === false ? 0 : zone) * Math.min(1, n.baseOpacity * 0.5 + 0.5) * (e < 1 ? 0.35 + 0.65 * e : 1);
          const h = boost * n.cardH * (e > 1 ? 1 + (e - 1) * 0.35 : 1);
          n.cards.forEach((c, i) => cards.setCard(c, h * (i ? 0.62 : 1), c.image ? op * (i ? 0.85 : 1) : 0));
          if (n.cards[0].image && op > 0.01) dot = 0.35 + 0.65 * (1 - op);
        }
        n.mesh.scale.setScalar(boost * n.size * dot * (e > 1 ? 1 + (e - 1) * 0.45 : 1));
        if (n.cards.length) { if (dot < 1) placeCards(n); else n.mesh.position.copy(n.pos); }
        n.halo.scale.setScalar(boost * n.size * n.haloMul);
        n.mesh.material.opacity = Math.min(1, n.baseOpacity * (e < 1 ? e : 1) + (e > 1 ? (e - 1) * 0.6 : 0));
        n.mesh.material.color.copy(n.base);
        if (e > 1) n.mesh.material.color.lerp(n.kc, Math.min(1, e - 1));
        n.halo.material.opacity = Math.min(1, n.baseHalo * (e < 1 ? e : 1) + (e > 1 ? (e - 1) * 0.5 : 0));
      });
      if (selRing.visible) { selRing.lookAt(camera.position); selRing.material.opacity = 0.6 + 0.3 * Math.sin(now / 300); }

      const ro = mode === "overview" ? { year: "Overview", era: "the whole corridor from the side; " + (C.touch ? "drag to orbit, pinch to zoom, Overview to return" : "drag or arrows to orbit, scroll or W and S to zoom, O to return") } : dToReadout(-camera.position.z + 6);
      const rk = ro.year + ro.era;
      if (rk !== lastReadout) { yearEl.textContent = ro.year; eraEl.textContent = ro.era; lastReadout = rk; }
      const stop = C.touch ? "Glide" : "Space";
      const st = auto ? auto.label + ", " + stop + " stops" : glide ? "gliding, " + stop + " pauses" : "";
      if (st !== lastStatus) { statusEl.textContent = st; statusEl.style.display = st ? "inline-block" : "none"; lastStatus = st; }

      C.renderer.render(scene, camera);
      C.placeLabels(labelCandidates(C.canvas.clientWidth, C.canvas.clientHeight));
      drawMinimap();
    }

    function resize(w, h) { camera.aspect = w / h; camera.updateProjectionMatrix(); requestAnimationFrame(resizeMinimap); }

    // hash keys this view reads: d, year, yaw, pitch, angle, overview
    function applyHash(h) {
      if (h.has("angle")) { const a = h.get("angle"); if (a !== "kind" && a !== "region") throw new Error("the link asks for angle " + JSON.stringify(a) + "; expected kind or region."); setAngleMode(a, true); }
      if (h.has("d")) fl.pos.z = -(parseFloat(h.get("d")) - 8);
      if (h.has("year")) fl.pos.z = -(yearToD(parseFloat(h.get("year"))) - 8);
      if (h.has("yaw")) fl.yaw = parseFloat(h.get("yaw"));
      if (h.has("pitch")) fl.pitch = parseFloat(h.get("pitch"));
      clampFlight();
      if (h.has("overview")) { setMode("overview"); modeBlend = 1; }
    }
    function syncCamera() {   // used before a rail snap from a fresh hash, so nearestStory sees the pose
      camera.position.copy(fl.pos); camera.lookAt(fl.pos.clone().add(fwd(fl.yaw, fl.pitch))); camera.updateMatrixWorld();
    }

    return {
      name: "corridor",
      activate() { active = true; requestAnimationFrame(resizeMinimap); },
      deactivate() { active = false; keys.clear(); dragging = null; touches.clear(); twoF = null; },
      blur() { keys.clear(); },
      frame, resize, keydown, keyup, escape, flyTo, railArrive, railRelease, nearestStory, setEmphasis,
      applyVisibility, restyle, setSelected, applyHash, syncCamera, reveal() {},
    };
  };
})();
