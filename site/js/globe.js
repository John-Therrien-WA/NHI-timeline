/* The globe: each region a circular patch on a sphere, sized by how many stories it holds, not by its
   geography; height above a patch is time, with one shell per era, thicker where more stories fall.
   Flatten collapses the altitude and paints time as colour. NHI.globe(C, addons) builds the view. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};

  NHI.globe = function (C, addons) {
    const THREE = C.THREE, M = C.M, D = M.D, el = C.el;
    const { OrbitControls, CSS2DRenderer, CSS2DObject } = addons;
    const R = 10;                 // globe radius
    const H = 6.4;                // total altitude of all shells above the surface
    const LIFT = 0.22;            // gap between the surface and the lowest story
    const FLOOR_PATCH = 3;        // the floor added to each region's story count for its patch area
    const FLOOR_SHELL = 4;        // the floor added to each era's story count for its shell thickness
    const MARGIN = 0.016;         // angular gap between touching patches (rad)
    const ERAS = D.eras, Y0 = ERAS[0].from, Y1 = ERAS[ERAS.length - 1].to;
    const WARN = 0xff4d4d, NEUTRAL = 0x9fb3c8, HL = 0xffd27a;
    const isNum = x => typeof x === "number" && isFinite(x);
    const ease = C.ease;
    function fail(msg) { throw new Error("globe: " + msg); }

    // ---- small vector kit on plain arrays (unit sphere work); y is north, longitude 0 faces +z, east is +x ----
    const dot3 = (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
    const norm3 = a => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
    const cross3 = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    const angle3 = (a, b) => Math.acos(Math.max(-1, Math.min(1, dot3(a, b))));
    function llDir(lat, lon) { const la = lat * Math.PI / 180, lo = lon * Math.PI / 180; return [Math.cos(la) * Math.sin(lo), Math.sin(la), Math.cos(la) * Math.cos(lo)]; }
    function frameAt(c) {
      let east = cross3([0, 1, 0], c);
      if (Math.hypot(...east) < 1e-6) east = [1, 0, 0];
      east = norm3(east);
      return { east, north: norm3(cross3(c, east)) };
    }
    function offsetDir(c, rho, beta) {
      const f = frameAt(c);
      const t = [0, 1, 2].map(k => f.north[k] * Math.cos(beta) + f.east[k] * Math.sin(beta));
      return norm3([0, 1, 2].map(k => c[k] * Math.cos(rho) + t[k] * Math.sin(rho)));
    }
    function polarOf(c, p) { const f = frameAt(c); return { rho: angle3(c, p), beta: Math.atan2(dot3(p, f.east), dot3(p, f.north)) }; }
    function slide(c, o, amt) {
      let t = [c[0] - o[0] * dot3(c, o), c[1] - o[1] * dot3(c, o), c[2] - o[2] * dot3(c, o)];
      if (Math.hypot(...t) < 1e-9) t = frameAt(c).east;
      t = norm3(t);
      return norm3([0, 1, 2].map(k => c[k] * Math.cos(amt) + t[k] * Math.sin(amt)));
    }

    // ================= the cartogram: regions as touching circular patches =================
    const regionNames = [];
    D.places.forEach(p => { if (!regionNames.includes(p.region) && M.regionCounts.has(p.region)) regionNames.push(p.region); });
    if (M.regionCounts.has(M.UNPLACED)) regionNames.push(M.UNPLACED);
    const REGIONS = regionNames.map(name => {
      const stories = D.stories.filter(s => M.regionOf(s) === name);
      const places = D.places.filter(p => p.region === name);
      return { name, stories, places, n: stories.length, w: stories.length + FLOOR_PATCH };
    });
    REGIONS.forEach(r => {
      const geo = r.places.filter(p => isNum(p.lat));
      if (r.name === "Off Earth") r.anchor = llDir(78, -10);
      else if (r.name === M.UNPLACED) r.anchor = llDir(-12, 78);
      else if (geo.length) { const m = [0, 0, 0]; geo.forEach(p => { const v = llDir(p.lat, p.lon); m[0] += v[0]; m[1] += v[1]; m[2] += v[2]; }); r.anchor = norm3(m); }
      else fail("region " + r.name + " has no place with coordinates to anchor it");
      r.geoCenter = r.anchor;
    });
    function relax(cover) {
      const W = REGIONS.reduce((a, r) => a + r.w, 0);
      REGIONS.forEach(r => { r.theta = Math.acos(1 - 2 * cover * r.w / W); r.c = norm3(r.anchor.map((v, k) => v + (M.hash(r.name + k) - 0.5) * 0.02)); });
      const N = REGIONS.length;
      let maxOv = 0;
      for (let it = 0; it < 2200; it++) {
        const phase = it < 500 ? "spread" : (it < 1700 ? "gather" : "clean");
        maxOv = 0;
        for (let i = 0; i < N; i++) for (let j = i + 1; j < N; j++) {
          const A = REGIONS[i], B = REGIONS[j];
          const ov = A.theta + B.theta + MARGIN - angle3(A.c, B.c);
          if (ov > 0) {
            maxOv = Math.max(maxOv, ov);
            const shA = B.theta / (A.theta + B.theta), shB = 1 - shA;   // the small patch moves more
            A.c = slide(A.c, B.c, ov * shA * 0.6); B.c = slide(B.c, A.c, ov * shB * 0.6);
          } else if (phase === "gather" && -ov < 0.35) {
            const g = -ov * 0.04;
            A.c = slide(A.c, B.c, -g * 0.5); B.c = slide(B.c, A.c, -g * 0.5);
          }
        }
        if (phase === "spread") REGIONS.forEach(r => { r.c = norm3(r.c.map((v, k) => v + (r.anchor[k] - v) * 0.015)); });
      }
      return maxOv;
    }
    let COVER = 0.9, packOv = 1;
    for (; COVER > 0.4; COVER -= 0.01) { packOv = relax(COVER); if (packOv < 0.0015) break; }
    if (packOv >= 0.0015) fail("the region patches could not be packed without overlap (residual " + packOv.toFixed(4) + " rad)");

    // places inside each patch: local offsets rescaled to the patch, then spread apart
    const storyCountByPlace = new Map();
    D.stories.forEach(s => { if (s.place) storyCountByPlace.set(s.place, (storyCountByPlace.get(s.place) || 0) + 1); });
    const SPIRAL = 0.026;
    const placeDir = new Map(), unplacedGroups = new Map();
    REGIONS.forEach(r => {
      let pts;
      if (r.name === M.UNPLACED) {
        r.stories.forEach(s => { const k = M.unplacedKey(s); if (!unplacedGroups.has(k)) unplacedGroups.set(k, []); unplacedGroups.get(k).push(s); });
        const keys = Array.from(unplacedGroups.keys()).sort((a, b) => unplacedGroups.get(b).length - unplacedGroups.get(a).length || (a < b ? -1 : 1));
        pts = keys.map((k, i) => ({ key: "u:" + k, rho: i === 0 ? 0 : 0.9 * Math.sqrt(i / keys.length), beta: i * 2.39996323, n: unplacedGroups.get(k).length, label: k }));
      } else if (r.name === "Off Earth") {
        pts = r.places.map((p, i) => ({ key: p.id, rho: r.places.length > 1 ? 0.5 : 0, beta: i * 2 * Math.PI / r.places.length, n: storyCountByPlace.get(p.id) || 0 }));
      } else {
        const raw = r.places.map(p => Object.assign({ key: p.id, n: storyCountByPlace.get(p.id) || 0 }, polarOf(r.geoCenter, llDir(p.lat, p.lon))));
        const rmax = Math.max(...raw.map(p => p.rho), 1e-9);
        // a square-root radial rescale opens the dense core and keeps the bearings
        pts = raw.map(p => Object.assign({}, p, { rho: rmax < 1e-6 ? 0 : Math.sqrt(p.rho / rmax) }));
      }
      const lim = r.theta * 0.8;
      pts.forEach(p => { p.d = offsetDir(r.c, p.rho * lim * 0.92, p.beta); });
      for (let it = 0; it < 220; it++) {
        for (let i = 0; i < pts.length; i++) for (let j = i + 1; j < pts.length; j++) {
          const A = pts[i], B = pts[j];
          const need = 0.035 + SPIRAL * 1.15 * (Math.sqrt(A.n) + Math.sqrt(B.n));
          const d = angle3(A.d, B.d);
          if (d < need) { A.d = slide(A.d, B.d, (need - d) * 0.5); B.d = slide(B.d, A.d, (need - d) * 0.5); }
        }
        pts.forEach(p => { const rho = angle3(r.c, p.d), room = r.theta - 0.03 - SPIRAL * Math.sqrt(p.n); if (rho > room) p.d = slide(p.d, r.c, -(rho - room)); });
      }
      pts.forEach(p => placeDir.set(p.key, p));
      r.pts = pts;
    });

    // shells: an undated layer on the surface, then one shell per era, thickness by story count
    const LAYERS = [{ id: "_undated", name: "Undated", from: null, to: null }].concat(ERAS.map(e => ({ id: e.id, name: e.name, from: e.from, to: e.to })));
    LAYERS.forEach(L => { L.n = D.stories.filter(s => (L.id === "_undated" ? !s.years : s.years && s.era === L.id)).length; });
    {
      const W = LAYERS.reduce((a, L) => a + L.n + FLOOR_SHELL, 0);
      let a = 0;
      LAYERS.forEach(L => { L.a = a; L.t = H * (L.n + FLOOR_SHELL) / W; a += L.t; L.b = a; });
    }
    function altOfYear(yr) {
      if (yr < Y0) return LAYERS[1].a;
      for (let i = 1; i < LAYERS.length; i++) {
        const L = LAYERS[i];
        if (yr < L.from) return L.a;
        if (yr <= L.to) return L.a + L.t * (0.06 + 0.88 * (yr - L.from) / Math.max(1, L.to + 1 - L.from));
      }
      return LAYERS[LAYERS.length - 1].b;
    }
    const ALT_DATED0 = LAYERS[1].a, ALT_TOP = LAYERS[LAYERS.length - 1].b;
    const timeFrac = yr => (altOfYear(yr) - ALT_DATED0) / (ALT_TOP - ALT_DATED0);
    const RAMP = ["#6f6cff", "#3fb6e0", "#5fe0a8", "#e8dc6a", "#ff8a4c"].map(c => new THREE.Color(c));
    const UNDATED_COL = new THREE.Color("#a5adb9");
    function rampColor(f, out) { f = Math.max(0, Math.min(1, f)) * (RAMP.length - 1); const i = Math.min(RAMP.length - 2, Math.floor(f)); return out.copy(RAMP[i]).lerp(RAMP[i + 1], f - i); }

    // each story's direction and altitude
    const groupsByKey = new Map();
    D.stories.forEach(s => {
      const key = s.place || "u:" + M.unplacedKey(s);
      if (!placeDir.has(key)) fail("story " + s.id + " has no slot on the globe (" + key + ")");
      if (!groupsByKey.has(key)) groupsByKey.set(key, []);
      groupsByKey.get(key).push(s);
    });
    groupsByKey.forEach((list, key) => {
      list.sort((a, b) => a._tier - b._tier || b._score - a._score || (a.id < b.id ? -1 : 1));
      const c = placeDir.get(key).d;
      list.forEach((s, i) => { s._dir = i === 0 ? c : offsetDir(c, SPIRAL * Math.sqrt(i + 0.3), i * 2.39996323); });
    });
    D.stories.forEach(s => {
      if (s.years) { s._alt = altOfYear(s.years.from); s._alt2 = altOfYear(s.years.to); s._tf = timeFrac(s.years.from); }
      else { const L = LAYERS[0]; s._alt = L.a + L.t * (0.12 + 0.76 * M.hash(s.id)); s._alt2 = s._alt; s._tf = null; }
    });

    // ================= three.js scene =================
    const canvas = C.canvas;
    const labelRenderer = new CSS2DRenderer({ element: document.getElementById("glabels") });
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x060a11);
    const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 800);
    const controls = new OrbitControls(camera, canvas);
    controls.enableDamping = true; controls.dampingFactor = 0.08; controls.enablePan = false;
    controls.minDistance = R + 2.5; controls.maxDistance = 140; controls.rotateSpeed = 0.6;
    controls.enabled = false;
    function label(text, cls, pos, html, parent) {
      const div = el("div", { class: "l3 " + cls });
      if (html) div.innerHTML = html; else div.textContent = text;
      const o = new CSS2DObject(div);
      o.position.copy(pos);
      (parent || scene).add(o);
      return o;
    }
    const V = a => new THREE.Vector3(a[0], a[1], a[2]);

    { // faint star dust for depth while orbiting
      const pts = [];
      for (let i = 0; i < 900; i++) {
        const d = llDir(Math.asin(2 * M.hash("sa" + i) - 1) * 180 / Math.PI, 360 * M.hash("so" + i) - 180), r = 220 + 160 * M.hash("sr" + i);
        pts.push(d[0] * r, d[1] * r, d[2] * r);
      }
      const g = new THREE.BufferGeometry(); g.setAttribute("position", new THREE.Float32BufferAttribute(pts, 3));
      scene.add(new THREE.Points(g, new THREE.PointsMaterial({ color: 0x4a5a72, size: 1.1, sizeAttenuation: false, transparent: true, opacity: 0.6 })));
    }

    // the surface: one shader draws every patch as a cap with a rim, the gaps stay dark
    const PATCH_HUES = { "North America": "#3d6fa8", "Unplaced": "#6b6584", "Pacific": "#2f8a9a", "Atlantic": "#3a7f9e", "Europe": "#5b74b8", "Middle East": "#a07a4a",
      "Africa": "#9a8040", "Asia": "#7a5aa6", "South America": "#4f9a6a", "Antarctica": "#7f9cb5", "Off Earth": "#a89150" };
    const EXTRA_HUES = ["#5d8a8a", "#8a5d7a", "#7a8a5d", "#5d6a8a"];
    REGIONS.forEach((r, i) => { r.color = new THREE.Color(PATCH_HUES[r.name] || EXTRA_HUES[i % EXTRA_HUES.length]); });
    const MAXP = 16;
    if (REGIONS.length > MAXP) fail("more than " + MAXP + " regions; the surface shader holds " + MAXP);
    const globeUniforms = {
      uC: { value: Array.from({ length: MAXP }, (_, i) => REGIONS[i] ? V(REGIONS[i].c) : new THREE.Vector3(0, 1, 0)) },
      uTh: { value: Array.from({ length: MAXP }, (_, i) => REGIONS[i] ? REGIONS[i].theta : 0) },
      uCol: { value: Array.from({ length: MAXP }, (_, i) => REGIONS[i] ? REGIONS[i].color.clone() : new THREE.Color()) },
      uN: { value: REGIONS.length }, uHot: { value: -1 }, uLight: { value: new THREE.Vector3(0.4, 0.7, 0.6).normalize() }
    };
    scene.add(new THREE.Mesh(new THREE.SphereGeometry(R, 160, 120), new THREE.ShaderMaterial({
      uniforms: globeUniforms,
      vertexShader: `
        varying vec3 vDir; varying vec3 vN; varying vec3 vV;
        void main() {
          vDir = normalize(position);
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz);
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        #define MAXP ${MAXP}
        uniform vec3 uC[MAXP]; uniform float uTh[MAXP]; uniform vec3 uCol[MAXP]; uniform int uN; uniform int uHot; uniform vec3 uLight;
        varying vec3 vDir; varying vec3 vN; varying vec3 vV;
        void main() {
          vec3 col = vec3(0.028, 0.042, 0.065);
          for (int i = 0; i < MAXP; i++) {
            if (i >= uN) break;
            float a = acos(clamp(dot(vDir, uC[i]), -1.0, 1.0));
            float e = uTh[i] - a;
            if (e > 0.0) {
              float u = a / uTh[i];
              vec3 fill = uCol[i] * (0.34 + 0.16 * (1.0 - u * u));
              float rim = smoothstep(0.018, 0.0, e);
              float hot = (i == uHot) ? 1.0 : 0.0;
              col = fill * (1.0 + 0.45 * hot) + mix(uCol[i] * 1.1, vec3(0.85, 0.92, 1.0), 0.35 + 0.4 * hot) * rim * (0.8 + 0.6 * hot);
            }
          }
          float lam = 0.55 + 0.45 * max(dot(vN, normalize(uLight)), 0.0);
          float fres = pow(1.0 - max(dot(vN, vV), 0.0), 3.0);
          col = col * lam + vec3(0.10, 0.18, 0.30) * fres * 0.6;
          gl_FragColor = vec4(col, 1.0);
        }`
    })));

    // era shells and their camera-facing rings with the era name
    const SHELL_COL = new THREE.Color("#5d86b8"), UNDATED_SHELL = new THREE.Color("#a89150"), WIN_COL = new THREE.Color("#7fd3ff");
    const shells = LAYERS.map((L, i) => {
      const mat = new THREE.ShaderMaterial({
        uniforms: { uCol: { value: (i === 0 ? UNDATED_SHELL : SHELL_COL).clone() }, uOp: { value: 1 } },
        vertexShader: `varying vec3 vN; varying vec3 vV;
          void main() { vec4 mv = modelViewMatrix * vec4(position, 1.0); vN = normalize(normalMatrix * normal); vV = normalize(-mv.xyz); gl_Position = projectionMatrix * mv; }`,
        fragmentShader: `uniform vec3 uCol; uniform float uOp; varying vec3 vN; varying vec3 vV;
          void main() { float f = 1.0 - abs(dot(normalize(vN), normalize(vV))); float a = (0.004 + 0.26 * pow(f, 7.0)) * uOp; gl_FragColor = vec4(uCol, a); }`,
        transparent: true, depthWrite: false, side: THREE.FrontSide, blending: THREE.AdditiveBlending
      });
      const m = new THREE.Mesh(new THREE.SphereGeometry(R + LIFT + L.b, 96, 64), mat);
      m.renderOrder = 2; scene.add(m);
      return { L, m, op: 1, target: 1 };
    });
    const ringGroup = new THREE.Group(); scene.add(ringGroup);
    const circlePts = [];
    for (let i = 0; i <= 128; i++) { const a = i / 128 * Math.PI * 2; circlePts.push(new THREE.Vector3(Math.cos(a), Math.sin(a), 0)); }
    const circleGeo = new THREE.BufferGeometry().setFromPoints(circlePts);
    const eraRings = LAYERS.map((L, i) => {
      const line = new THREE.Line(circleGeo, new THREE.LineBasicMaterial({ color: i === 0 ? 0x8a7a52 : 0x3d5a80, transparent: true, opacity: 0.55, depthWrite: false }));
      ringGroup.add(line);
      const lbl = label("", "era" + (i === 0 ? " undated" : ""), new THREE.Vector3(), "<b></b> <span></span>", ringGroup);
      lbl.element.querySelector("b").textContent = L.name;
      lbl.element.querySelector("span").textContent = L.from == null ? "no years given" : L.from + " to " + L.to;
      return { L, line, lbl };
    });

    // region names and place markers
    const regionLabels = REGIONS.map((r, i) => {
      const at = offsetDir(r.c, r.theta * 0.55, 0);
      const o = label("", "region", V(at).multiplyScalar(R + 0.05), "<span></span><small></small>");
      o.element.querySelector("span").textContent = r.name;
      o.element.querySelector("small").textContent = r.n + (r.n === 1 ? " story" : " stories");
      o.element.style.fontSize = Math.max(10, Math.min(19, 7 + r.theta * 13)) + "px";
      o.element.addEventListener("click", () => flyToRegion(r));
      o.element.addEventListener("mouseenter", () => { globeUniforms.uHot.value = i; });
      o.element.addEventListener("mouseleave", () => { globeUniforms.uHot.value = -1; });
      o.userData.dir = V(at);
      return o;
    });
    const placeLabels = [];
    {
      const markers = [];
      REGIONS.forEach(r => r.pts.forEach(p => {
        markers.push(V(p.d).multiplyScalar(R + 0.02));
        if (p.n > 0) {
          const name = p.label || (M.placeById[p.key] ? M.placeById[p.key].name : p.key);
          const o = label(name, "place", V(p.d).multiplyScalar(R + 0.04));
          o.center.set(0.5, -0.4);
          Object.assign(o.userData, { dir: V(p.d), n: p.n, w: name.length * 5.5 + 8 });
          o.visible = false;
          placeLabels.push(o);
        }
      }));
      scene.add(new THREE.Points(new THREE.BufferGeometry().setFromPoints(markers), new THREE.PointsMaterial({ color: 0x8fb0d4, size: 0.1, transparent: true, opacity: 0.75, depthWrite: false })));
    }

    // story sprites: softness, size and brightness follow the tier first and the score second
    const SOFT_LEVELS = 6;
    function drawSprite(g, S, soft) {
      g.clearRect(0, 0, S, S);
      const c = S / 2, r0 = c * (0.42 - 0.38 * soft), r1 = c * (0.5 + 0.48 * soft);
      const grd = g.createRadialGradient(c, c, 0, c, c, c);
      grd.addColorStop(0, "rgba(255,255,255,1)");
      grd.addColorStop(r0 / c, "rgba(255,255,255," + (0.95 - 0.35 * soft) + ")");
      grd.addColorStop(Math.min(0.999, r1 / c), "rgba(255,255,255,0)");
      grd.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = grd; g.fillRect(0, 0, S, S);
      if (soft < 0.35) {
        g.beginPath(); g.arc(c, c, c * 0.44, 0, Math.PI * 2);
        g.lineWidth = Math.max(1, S * 0.03); g.strokeStyle = "rgba(255,255,255," + (0.9 - soft * 2) + ")"; g.stroke();
        const core = g.createRadialGradient(c, c, 0, c, c, c * 0.18);
        core.addColorStop(0, "rgba(255,255,255,1)"); core.addColorStop(1, "rgba(255,255,255,0)");
        g.fillStyle = core; g.fillRect(0, 0, S, S);
      }
    }
    function canvasTex(draw, S) { const c = document.createElement("canvas"); c.width = c.height = S || 128; draw(c.getContext("2d"), c.width); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t; }
    const spriteTex = Array.from({ length: SOFT_LEVELS }, (_, i) => canvasTex((g, S) => drawSprite(g, S, i / (SOFT_LEVELS - 1))));
    const glowTex = canvasTex(g => {
      const r = g.createRadialGradient(64, 64, 0, 64, 64, 64);
      r.addColorStop(0, "rgba(255,255,255,0.9)"); r.addColorStop(0.25, "rgba(255,255,255,0.3)"); r.addColorStop(0.6, "rgba(255,255,255,0.06)"); r.addColorStop(1, "rgba(255,255,255,0)");
      g.fillStyle = r; g.fillRect(0, 0, 128, 128);
    });
    const ringTex = canvasTex(g => { g.strokeStyle = "#fff"; g.lineWidth = 7; g.beginPath(); g.arc(64, 64, 52, 0, Math.PI * 2); g.stroke(); });
    // the tier sets the floor: a well-attested story is always crisp and large, a told-once story soft and small
    const looks = [{ soft: 0.05, size: 0.95, bright: 1.0 }, { soft: 0.45, size: 0.62, bright: 0.82 }, { soft: 0.85, size: 0.4, bright: 0.58 }];
    function sizeOf(s) { const L = looks[s._tier]; return L.size * (0.65 + 0.6 * s._str); }
    function lineMat(color, opacity) { return new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthWrite: false }); }
    const storyObjs = D.stories.map(s => {
      const kc = new THREE.Color(M.KIND_COLORS[s.kind]);
      const tc = s._tf == null ? UNDATED_COL.clone() : rampColor(s._tf, new THREE.Color());
      const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: spriteTex[0], color: kc.clone(), transparent: true, depthWrite: false }));
      sprite.renderOrder = 4; scene.add(sprite);
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTex, color: kc.clone(), blending: THREE.AdditiveBlending, transparent: true, depthWrite: false }));
      glow.renderOrder = 3; scene.add(glow);
      const ring = new THREE.Sprite(new THREE.SpriteMaterial({ map: ringTex, color: 0xffffff, transparent: true, depthWrite: false, depthTest: false }));
      ring.visible = false; ring.renderOrder = 10; scene.add(ring);
      const stem = new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]), lineMat(kc.clone().multiplyScalar(0.8), 1));
      scene.add(stem);
      const span = s.years && s._alt2 > s._alt + 0.02 ? new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]), lineMat(kc.clone(), 1)) : null;
      if (span) scene.add(span);
      const o = { s, sprite, glow, ring, stem, span, kc, tc, col: new THREE.Color(), base: {}, f: 1, target: 1, pos: new THREE.Vector3(), dir: V(s._dir) };
      s._gobj = o;
      return o;
    });
    function styleStories() {
      storyObjs.forEach(o => {
        const s = o.s, L = looks[s._tier], t = s._str;
        const soft = Math.min(1, Math.max(0, L.soft + 0.25 * (0.5 - t)));
        o.sprite.material.map = spriteTex[Math.round(soft * (SOFT_LEVELS - 1))];
        o.sprite.scale.setScalar(sizeOf(s));
        o.glow.scale.setScalar(sizeOf(s) * (s._tier === 0 ? 4.5 : s._tier === 1 ? 3 : 2.2));
        o.base = { op: Math.min(1, L.bright * (0.7 + 0.3 * t)), bright: L.bright * (0.75 + 0.25 * t),
          glow: s._tier === 0 ? 0.35 + 0.4 * t : s._tier === 1 ? 0.1 + 0.15 * t : 0, stem: (s._tier === 0 ? 0.3 : 0.08) + 0.25 * t, span: 0.4 + 0.5 * t };
      });
    }

    const linkObjs = M.links.map(l => {
      const warn = l.relation === "contradicts";
      const mat = warn ? new THREE.LineDashedMaterial({ color: WARN, dashSize: 0.3, gapSize: 0.18, transparent: true, opacity: 0.95, depthWrite: false })
                       : new THREE.LineBasicMaterial({ color: NEUTRAL, transparent: true, opacity: 0.3, depthWrite: false });
      const line = new THREE.Line(new THREE.BufferGeometry(), mat);
      scene.add(line);
      return { l, line, warn, baseOp: mat.opacity };
    });

    // ================= state =================
    const state = { ts: 1, tsTarget: 1, win: [Y0, Y1], showUndated: true };
    let active = false, selected = null, focus = null;
    function radiusOf(s, ts) { return R + LIFT * (0.55 + 0.45 * ts) + s._alt * ts; }
    function placeAll() {
      const ts = state.ts;
      storyObjs.forEach(o => {
        const s = o.s, r = radiusOf(s, ts);
        o.pos.copy(o.dir).multiplyScalar(r);
        o.sprite.position.copy(o.pos); o.glow.position.copy(o.pos); o.ring.position.copy(o.pos);
        const sp = o.stem.geometry.attributes.position;
        sp.setXYZ(0, o.pos.x, o.pos.y, o.pos.z); sp.setXYZ(1, o.dir.x * (R + 0.01), o.dir.y * (R + 0.01), o.dir.z * (R + 0.01));
        sp.needsUpdate = true; o.stem.geometry.computeBoundingSphere();
        if (o.span) {
          const pp = o.span.geometry.attributes.position, r2 = R + LIFT + s._alt2 * ts;
          pp.setXYZ(0, o.pos.x, o.pos.y, o.pos.z); pp.setXYZ(1, o.dir.x * r2, o.dir.y * r2, o.dir.z * r2);
          pp.needsUpdate = true; o.span.geometry.computeBoundingSphere();
        }
        o.col.copy(o.kc).lerp(o.tc, 1 - ts);
      });
      linkObjs.forEach(L => {
        const A = M.storyById[L.l.a]._gobj, B = M.storyById[L.l.b]._gobj;
        const ra = A.pos.length(), rb = B.pos.length(), ang = A.dir.angleTo(B.dir);
        // arcs stay inside the shells: a lift that grows with the angle but tops out just above the present
        const ceil = R + LIFT + (ALT_TOP + 0.8) * state.ts + 1.4 * (1 - state.ts);
        const bump = Math.min(0.45 + ang * R * 0.12, Math.max(0.35, ceil - Math.max(ra, rb)));
        const pts = [], side = new THREE.Vector3().crossVectors(A.dir, new THREE.Vector3(0, 1, 0)).normalize();
        for (let k = 0; k <= 48; k++) {
          const u = k / 48;
          let d;
          if (ang > 1e-3) { const sa = Math.sin((1 - u) * ang) / Math.sin(ang), sb = Math.sin(u * ang) / Math.sin(ang); d = A.dir.clone().multiplyScalar(sa).add(B.dir.clone().multiplyScalar(sb)); }
          else d = A.dir.clone().addScaledVector(side, Math.sin(Math.PI * u) * 0.04).normalize();
          pts.push(d.normalize().multiplyScalar(ra + (rb - ra) * u + bump * Math.sin(Math.PI * u)));
        }
        L.line.geometry.dispose();
        L.line.geometry = new THREE.BufferGeometry().setFromPoints(pts);
        if (L.warn) L.line.computeLineDistances();
      });
      shells.forEach(S => { S.m.scale.setScalar(Math.max(0.0001, ((R + LIFT + S.L.b) * ts + R * (1 - ts)) / (R + LIFT + S.L.b))); });
    }
    function inWindow(s) { if (!s.years) return state.showUndated; return s.years.to >= state.win[0] && s.years.from <= state.win[1]; }
    function layerInWindow(L) { if (L.from == null) return state.showUndated; return L.to >= state.win[0] && L.from <= state.win[1]; }
    const fullWindow = () => state.win[0] === Y0 && state.win[1] === Y1;
    function computeTargets() {
      const f0 = focus || selected;
      const conn = f0 ? M.sharing(f0) : null;
      const linked = f0 ? new Set(M.linksOf(f0).map(r => r.other)) : null;
      storyObjs.forEach(o => {
        const s = o.s;
        let f = inWindow(s) ? 1 : 0.05;
        if (!M.isVisible(s)) f = 0;
        if (f0 && s.id !== f0 && !conn.has(s.id) && !linked.has(s.id)) f *= 0.2;
        o.target = f;
        const isFocus = s.id === f0, isConn = !!f0 && (conn.has(s.id) || linked.has(s.id)), isSel = s.id === selected;
        o.ring.visible = Boolean((isFocus || isSel || isConn) && f > 0.05);
        o.ring.material.color.set(isFocus || isSel ? 0xffffff : HL);
        o.ring.material.opacity = isFocus || isSel ? 0.95 : 0.7;
      });
      const full = fullWindow();
      shells.forEach((S, i) => {
        const inW = layerInWindow(S.L);
        let t = 1;
        if (!full || !state.showUndated) t = inW ? 1.6 : (S.L.from != null && S.L.from > state.win[1] ? 0.04 : 0.35);
        S.target = t;
        S.m.material.uniforms.uCol.value.copy(i === 0 ? UNDATED_SHELL : SHELL_COL);
        if (inW && !full) S.m.material.uniforms.uCol.value.lerp(WIN_COL, 0.6);
        eraRings[i].lbl.element.classList.toggle("out", !inW);
        eraRings[i].line.material.color.set(inW && !full ? 0x7fd3ff : (i === 0 ? 0x8a7a52 : 0x3d5a80));
        eraRings[i].line.userData.base = inW ? (full ? 0.5 : 0.9) : (S.L.from != null && S.L.from > state.win[1] ? 0.06 : 0.25);
      });
    }
    function applyFades(dt) {
      const k = 1 - Math.exp(-dt * 9), ts = state.ts;
      storyObjs.forEach(o => {
        o.f += (o.target - o.f) * k;
        const f = o.f, vis = f > 0.01;
        o.sprite.visible = o.glow.visible = vis;
        o.stem.visible = vis && ts > 0.05;
        o.sprite.material.color.copy(o.col).multiplyScalar(o.base.bright);
        o.sprite.material.opacity = o.base.op * f;
        o.glow.material.color.copy(o.col);
        o.glow.material.opacity = o.base.glow * f;
        o.stem.material.opacity = o.base.stem * f * ts;
        if (o.span) { o.span.visible = vis && ts > 0.3; o.span.material.opacity = o.base.span * f * ts; }
      });
      const f0 = focus || selected;
      linkObjs.forEach(L => {
        const f = Math.min(M.storyById[L.l.a]._gobj.f, M.storyById[L.l.b]._gobj.f);
        const lit = f0 && (L.l.a === f0 || L.l.b === f0);
        L.line.visible = (lit && f > 0.01) || f > 0.02;
        L.line.material.opacity = lit ? 0.95 : L.baseOp * f;
      });
      shells.forEach(S => { S.op += (S.target - S.op) * k; S.m.material.uniforms.uOp.value = S.op * ts; S.m.visible = ts > 0.02; });
    }

    // ================= camera =================
    let fly = null;
    function flyCam(pos, target, ms) { fly = { p0: camera.position.clone(), t0: controls.target.clone(), p1: pos.clone(), t1: target.clone(), start: performance.now(), ms: ms || 900 }; }
    const NA = REGIONS.slice().sort((a, b) => b.n - a.n)[0];
    function homeCam() {
      const d = V(NA.c), f = frameAt(NA.c);
      const dir = d.clone().addScaledVector(V(f.north), 0.35).normalize();
      const fit = (R + LIFT + H + 0.6) / Math.sin(THREE.MathUtils.degToRad(camera.fov / 2) * 0.8) * Math.max(1, 1.1 / camera.aspect);
      return { pos: dir.multiplyScalar(fit), target: new THREE.Vector3() };
    }
    function flyToRegion(r) {
      const d = V(r.c), f = frameAt(r.c);
      flyCam(d.clone().addScaledVector(V(f.north), 0.25).normalize().multiplyScalar(R + H + 2 + r.theta * 9), new THREE.Vector3(), 1100);
    }
    function flyTo(sid, instant) {
      railRelease(); rail.tween = null;
      const o = M.storyById[sid]._gobj;
      const dist = Math.max(o.pos.length() + 8, Math.min(camera.position.length(), o.pos.length() + 16));
      const p = o.pos.clone().normalize().multiplyScalar(dist);
      if (instant) { fly = null; controls.target.set(0, 0, 0); camera.position.copy(p); return; }
      flyCam(p, new THREE.Vector3(), 950);
    }
    // keep the selected story out from under the panel on a wide screen
    let viewShift = 0, viewShiftTarget = 0;
    function applyViewOffset() {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      if (Math.abs(viewShift) < 0.5) camera.clearViewOffset(); else camera.setViewOffset(w, h, viewShift, 0, w, h);
      camera.updateProjectionMatrix();
    }

    // ================= picking =================
    const tmpV = new THREE.Vector3();
    function occluded(p) {
      const c = camera.position, v = tmpV.copy(p).sub(c);
      const a = v.dot(v), b = 2 * c.dot(v), cc = c.dot(c) - R * R * 0.998;
      const disc = b * b - 4 * a * cc;
      if (disc < 0) return false;
      const t = (-b - Math.sqrt(disc)) / (2 * a);
      return t > 0 && t < 1;
    }
    function pick(clientX, clientY) {
      const w = canvas.clientWidth, h = canvas.clientHeight;
      const fovK = (h / 2) / Math.tan(THREE.MathUtils.degToRad(camera.fov / 2));
      let best = null, bestScore = Infinity;
      storyObjs.forEach(o => {
        if (o.target < 0.2 || occluded(o.pos)) return;
        const p = o.pos.clone().project(camera);
        if (p.z > 1 || p.z < -1) return;
        const sx = (p.x + 1) / 2 * w, sy = (1 - p.y) / 2 * h;
        const dist = camera.position.distanceTo(o.pos);
        const reach = Math.max(8, sizeOf(o.s) * 0.5 * fovK / dist + 3);
        const d = Math.hypot(sx - clientX, sy - clientY);
        if (d <= reach) { const sc = d / reach + dist * 0.004; if (sc < bestScore) { bestScore = sc; best = o.s.id; } }
      });
      return best;
    }
    let down = null, fingers = 0;
    canvas.addEventListener("pointerdown", e => { if (!active) return; fingers++; down = fingers === 1 ? { x: e.clientX, y: e.clientY } : null; fly = null; keyOrbit.az = keyOrbit.po = 0; cancelTween(); });
    canvas.addEventListener("pointercancel", () => { fingers = Math.max(0, fingers - 1); down = null; });
    canvas.addEventListener("wheel", () => { if (active) cancelTween(); }, { passive: true });
    canvas.addEventListener("pointermove", e => {
      if (!active) return;
      if (e.buttons) { C.hover(null); return; }
      const sid = pick(e.clientX, e.clientY);
      canvas.style.cursor = sid ? "pointer" : "grab";
      C.hover(sid, e.clientX, e.clientY);
    });
    canvas.addEventListener("pointerleave", () => { if (active) C.hover(null); });
    canvas.addEventListener("pointerup", e => {
      fingers = Math.max(0, fingers - 1);
      if (!active || !down || Math.hypot(e.clientX - down.x, e.clientY - down.y) > 5) return;
      const sid = pick(e.clientX, e.clientY);
      if (sid) C.select(sid, { fly: true }); else C.select(null);
    });

    // ================= time window, flatten, reset =================
    const winA = document.getElementById("win-a"), winB = document.getElementById("win-b");
    function syncWindow() {
      let lo = +winA.value, hi = +winB.value;
      if (lo > hi) { const m = lo; lo = hi; hi = m; winA.value = lo; winB.value = hi; }
      state.win = [lo, hi];
      document.getElementById("yr-a").textContent = lo; document.getElementById("yr-b").textContent = hi;
      document.querySelectorAll("#eras button").forEach(btn => btn.classList.toggle("on", +btn.dataset.from === lo && +btn.dataset.to === hi));
      computeTargets();
    }
    function setWindow(lo, hi) { winA.value = lo; winB.value = hi; syncWindow(); }
    {
      [winA, winB].forEach(x => { x.min = Y0; x.max = Y1; x.step = 1; x.addEventListener("input", syncWindow); });
      winA.value = Y0; winB.value = Y1;
      const eraBox = document.getElementById("eras");
      const eraBtn = (name, from, to) => {
        const btn = el("button", { class: "btn small", title: from + " to " + to }, name);
        btn.dataset.from = from; btn.dataset.to = to;
        btn.addEventListener("click", () => setWindow(from, to));
        eraBox.appendChild(btn);
      };
      eraBtn("All", Y0, Y1);
      ERAS.forEach(e => eraBtn(e.name, e.from, e.to));
      document.getElementById("undated").addEventListener("change", e => { state.showUndated = e.target.checked; computeTargets(); });
    }
    // Q and E step era by era; from the full window, E starts at the oldest era and Q at the newest
    function stepWindow(dir) {
      const [lo, hi] = state.win;
      const idx = ERAS.findIndex(e => e.from === lo && e.to === hi);
      if (fullWindow()) { const e = dir > 0 ? ERAS[0] : ERAS[ERAS.length - 1]; setWindow(e.from, e.to); return; }
      if (idx >= 0) { const j = idx + dir; if (j < 0 || j >= ERAS.length) setWindow(Y0, Y1); else setWindow(ERAS[j].from, ERAS[j].to); return; }
      const w = hi - lo + 1, nlo = Math.max(Y0, Math.min(Y1 - w + 1, lo + Math.max(1, Math.round(w / 2)) * dir));
      setWindow(nlo, nlo + w - 1);
    }
    const flatBtn = document.getElementById("b-flat");
    const FLAT_ZOOM = (R + 3.2) / (R + LIFT + H + 0.6);
    function setFlat(on, instant) {
      const was = state.tsTarget === 0;
      state.tsTarget = on ? 0 : 1;
      if (was !== on && !instant) {
        const d = camera.position.length() * (on ? FLAT_ZOOM : 1 / FLAT_ZOOM);
        flyCam(camera.position.clone().setLength(Math.max(controls.minDistance + 0.5, Math.min(controls.maxDistance, d))), controls.target, 900);
      }
      flatBtn.classList.toggle("on", on);
      flatBtn.textContent = on ? "Altitude" : "Flatten";
      document.getElementById("ramp-wrap").hidden = !on;
    }
    flatBtn.addEventListener("click", () => setFlat(state.tsTarget !== 0));
    function resetAll() { C.select(null); setFlat(false, true); setWindow(Y0, Y1); const c = homeCam(); flyCam(c.pos, c.target, 1000); }
    document.getElementById("b-reset").addEventListener("click", resetAll);
    {
      const ramp = document.getElementById("ramp");
      ramp.style.background = "linear-gradient(90deg," + RAMP.map(c => "#" + c.getHexString()).join(",") + ")";
      const ax = document.getElementById("rampax");
      [String(Y0), String(ERAS[Math.floor(ERAS.length / 2)].from), String(Y1), "undated grey"].forEach(t => ax.appendChild(el("span", null, t)));
    }

    // ================= keys =================
    const keyOrbit = { az: 0, po: 0, zoom: 0 };
    const held = new Set();
    const ORBIT = { ArrowLeft: 1, ArrowRight: 1, ArrowUp: 1, ArrowDown: 1, KeyW: 1, KeyS: 1 };
    function keydown(e) {
      const c = e.code;
      if (ORBIT[c]) { C.leaveRail(); held.add(c); fly = null; e.preventDefault(); C.usedOnce(); return true; }
      if (c === "KeyQ") { stepWindow(-1); e.preventDefault(); return true; }
      if (c === "KeyE") { stepWindow(1); e.preventDefault(); return true; }
      if (c === "KeyR" || c === "Home") { resetAll(); return true; }
      if (c === "KeyF") { setFlat(state.tsTarget !== 0); return true; }
      return false;
    }
    function keyup(e) { held.delete(e.code); }
    const sph = new THREE.Spherical();
    function keyMotion(dt) {
      const az = (held.has("ArrowLeft") ? -1 : 0) + (held.has("ArrowRight") ? 1 : 0);
      const po = (held.has("ArrowUp") ? -1 : 0) + (held.has("ArrowDown") ? 1 : 0);
      const zm = (held.has("KeyW") ? -1 : 0) + (held.has("KeyS") ? 1 : 0);
      const k = 1 - Math.exp(-dt * 10);
      keyOrbit.az += (az - keyOrbit.az) * k; keyOrbit.po += (po - keyOrbit.po) * k; keyOrbit.zoom += (zm - keyOrbit.zoom) * k;
      // the coast: a cancelled tween's velocity, decaying, so free motion starts where the tween was going
      const c = rail.coast, dec = Math.exp(-dt / 0.35);
      c.th *= dec; c.ph *= dec; c.lr *= dec;
      const coasting = Math.abs(c.th) + Math.abs(c.ph) + Math.abs(c.lr) > 1e-3;
      if (!coasting) c.th = c.ph = c.lr = 0;
      if (Math.abs(keyOrbit.az) + Math.abs(keyOrbit.po) + Math.abs(keyOrbit.zoom) < 1e-3 && !coasting) return;
      sph.setFromVector3(camera.position.clone().sub(controls.target));
      sph.theta += keyOrbit.az * dt * 1.4 + c.th * dt;
      sph.phi = Math.max(0.12, Math.min(Math.PI - 0.12, sph.phi + keyOrbit.po * dt * 1.1 + c.ph * dt));
      sph.radius = Math.max(controls.minDistance, Math.min(controls.maxDistance, sph.radius * Math.exp(keyOrbit.zoom * dt * 1.3 + c.lr * dt)));
      camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(sph));
    }

    // ================= rails: the framing pose orbits the story itself =================
    const rail = { tween: null, vel: { th: 0, ph: 0, lr: 0 }, coast: { th: 0, ph: 0, lr: 0 }, prevSph: null };
    const tsph = new THREE.Spherical();
    function zeroControlInertia() {
      if (controls._sphericalDelta) controls._sphericalDelta.set(0, 0, 0);
      if (controls._panOffset) controls._panOffset.set(0, 0, 0);
      if (typeof controls._scale === "number") controls._scale = 1;
    }
    function railArrive(sid, instant) {
      fly = null; keyOrbit.az = keyOrbit.po = keyOrbit.zoom = 0;
      rail.coast.th = rail.coast.ph = rail.coast.lr = 0;
      zeroControlInertia();
      const o = M.storyById[sid]._gobj, t1 = o.pos.clone();
      const view = camera.position.clone().sub(t1).normalize();
      const endDir = o.dir.clone().addScaledVector(view, 0.5).normalize();
      const dist = state.ts < 0.5 ? 7.5 : 9.5;
      tsph.setFromVector3(endDir.multiplyScalar(dist));
      const s0 = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
      let th1 = tsph.theta;
      while (th1 - s0.theta > Math.PI) th1 -= 2 * Math.PI;
      while (th1 - s0.theta < -Math.PI) th1 += 2 * Math.PI;
      rail.tween = {
        t0: controls.target.clone(), t1,
        a: { r: Math.log(s0.radius), th: s0.theta, ph: s0.phi }, b: { r: Math.log(dist), th: th1, ph: Math.max(0.12, Math.min(Math.PI - 0.12, tsph.phi)) },
        v0: Object.assign({}, rail.vel), start: performance.now(), ms: instant ? 0 : 700
      };
      if (instant) applyTween(performance.now() + 1);
    }
    function applyTween(now) {
      const T = rail.tween;
      const u = T.ms ? Math.min(1, (now - T.start) / T.ms) : 1, e = ease(u);
      // the free-orbit inertia carries on and blends out over 0.3 s, fading to nothing as the tween lands
      const t = (now - T.start) / 1000, drift = (t < 0.3 ? t - t * t / 0.6 : 0.15) * (1 - e);
      controls.target.lerpVectors(T.t0, T.t1, e);
      tsph.radius = Math.exp(T.a.r + (T.b.r - T.a.r) * e + T.v0.lr * drift);
      tsph.theta = T.a.th + (T.b.th - T.a.th) * e + T.v0.th * drift;
      tsph.phi = Math.max(0.05, Math.min(Math.PI - 0.05, T.a.ph + (T.b.ph - T.a.ph) * e + T.v0.ph * drift));
      camera.position.copy(controls.target).add(new THREE.Vector3().setFromSpherical(tsph));
      camera.lookAt(controls.target);
      if (u >= 1) { rail.tween = null; zeroControlInertia(); }
    }
    function cancelTween() {
      if (!rail.tween) return;
      rail.tween = null;
      rail.coast.th = rail.vel.th; rail.coast.ph = rail.vel.ph; rail.coast.lr = rail.vel.lr;
      zeroControlInertia();
    }
    function railRelease() { cancelTween(); }
    function measureVelocity(dt) {
      const sp = new THREE.Spherical().setFromVector3(camera.position.clone().sub(controls.target));
      const p = rail.prevSph;
      if (p && dt > 0) {
        let dth = sp.theta - p.theta;
        if (dth > Math.PI) dth -= 2 * Math.PI; else if (dth < -Math.PI) dth += 2 * Math.PI;
        rail.vel.th += (dth / dt - rail.vel.th) * 0.5;
        rail.vel.ph += ((sp.phi - p.phi) / dt - rail.vel.ph) * 0.5;
        rail.vel.lr += ((Math.log(Math.max(1e-3, sp.radius)) - Math.log(Math.max(1e-3, p.radius))) / dt - rail.vel.lr) * 0.5;
      }
      rail.prevSph = sp;
    }
    function nearestStory() {
      const w = canvas.clientWidth, h = canvas.clientHeight, cx = w / 2 - viewShift, cy = h / 2;
      let best = null, bs = Infinity;
      storyObjs.forEach(o => {
        if (o.target < 0.2 || occluded(o.pos)) return;
        const p = o.pos.clone().project(camera);
        if (p.z > 1 || p.z < -1 || Math.abs(p.x) > 1.05 || Math.abs(p.y) > 1.05) return;
        const sc = Math.hypot((p.x + 1) / 2 * w - cx, (1 - p.y) / 2 * h - cy) + 6 * camera.position.distanceTo(o.pos);
        if (sc < bs) { bs = sc; best = o.s.id; }
      });
      return best;
    }
    // the rail never moves the window on its own, but it widens it to take in a story it steps to
    function reveal(sid) {
      const s = M.storyById[sid];
      if (s.years && !(s.years.to >= state.win[0] && s.years.from <= state.win[1])) setWindow(Math.max(Y0, Math.min(state.win[0], s.years.from)), Math.min(Y1, Math.max(state.win[1], s.years.to)));
      if (!s.years && !state.showUndated) { state.showUndated = true; document.getElementById("undated").checked = true; computeTargets(); }
    }

    // ================= labels =================
    const pv = new THREE.Vector3();
    function rectOf(o, w, h, cx, cy) {
      pv.copy(o.position).project(camera);
      const x = (pv.x + 1) / 2 * canvas.clientWidth, y = (1 - pv.y) / 2 * canvas.clientHeight, x0 = x - w * cx, y0 = y - h * cy;
      return { x0, x1: x0 + w, y0, y1: y0 + h };
    }
    const placeSorted = placeLabels.slice().sort((a, b) => b.userData.n - a.userData.n);
    function declutter() {
      const taken = [];
      const hit = r => taken.some(t => r.x0 < t.x1 && r.x1 > t.x0 && r.y0 < t.y1 && r.y1 > t.y0);
      regionLabels.forEach(o => { if (o.visible) taken.push(rectOf(o, o.element.offsetWidth || 80, o.element.offsetHeight || 28, 0.5, 0.5)); });
      placeSorted.forEach(o => { if (!o.visible) return; const r = rectOf(o, o.userData.w, 14, 0.5, -0.4); if (hit(r)) o.visible = false; else taken.push(r); });
    }
    function labelCandidates(w, h) {
      const out = [];
      storyObjs.forEach(o => {
        const s = o.s, sel = s.id === selected;
        if (o.f < 0.5 || s.id === C.hoverSid()) return;
        const dist = camera.position.distanceTo(o.pos);
        const reach = M.TIERS[s._tier].labelAt * 0.6;
        if (!sel && dist > reach) return;
        if (occluded(o.pos)) return;
        pv.copy(o.pos).project(camera);
        if (pv.z > 1 || Math.abs(pv.x) > 0.95 || Math.abs(pv.y) > 0.92) return;
        out.push({ id: s.id, x: (pv.x + 1) / 2 * w, y: (1 - pv.y) / 2 * h, rank: (sel ? 100 : 0) + (3 - s._tier) * 10 + s._str * 5 - dist * 0.02 });
      });
      return out;
    }

    // ================= frame =================
    const camDir = new THREE.Vector3();
    let lastTs = -1;
    function frame(dt, now) {
      if (fly) {
        const x = Math.min(1, (now - fly.start) / fly.ms), e = ease(x);
        camera.position.lerpVectors(fly.p0, fly.p1, e);
        controls.target.lerpVectors(fly.t0, fly.t1, e);
        if (x >= 1) fly = null;
      }
      if (rail.tween) applyTween(now); else keyMotion(dt);
      state.ts += (state.tsTarget - state.ts) * (1 - Math.exp(-dt * 4));
      if (Math.abs(state.ts - state.tsTarget) < 0.001) state.ts = state.tsTarget;
      if (state.ts !== lastTs) { placeAll(); lastTs = state.ts; }
      const vs = viewShift + (viewShiftTarget - viewShift) * (1 - Math.exp(-dt * 6));
      if (Math.abs(vs - viewShift) > 0.05 || (viewShift !== 0 && Math.abs(vs) < 0.5)) { viewShift = Math.abs(vs - viewShiftTarget) < 0.5 ? viewShiftTarget : vs; applyViewOffset(); }
      controls.minDistance = controls.target.lengthSq() < 0.25 ? R + 2.5 : 3;
      if (!rail.tween) controls.update();
      if (camera.position.length() < R + 0.8) camera.position.setLength(R + 0.8);
      measureVelocity(dt);

      const dist = camera.position.length();
      camDir.copy(camera.position).normalize();
      ringGroup.lookAt(camera.position);
      const ts = state.ts, narrow = canvas.clientWidth < 760;
      eraRings.forEach((E, i) => {
        const r = ((R + LIFT + E.L.b) * ts + R * (1 - ts));
        E.line.scale.setScalar(r * Math.sqrt(Math.max(0, 1 - (r * r) / (dist * dist))));
        E.line.position.set(0, 0, r * r / dist);
        E.line.material.opacity = (E.line.userData.base != null ? E.line.userData.base : 0.5) * ts;
        E.line.visible = ts > 0.05;
        const rm = (R + LIFT + (E.L.a + E.L.b) / 2), rmm = rm * Math.sqrt(Math.max(0, 1 - (rm * rm) / (dist * dist)));
        const ang = THREE.MathUtils.degToRad(-38 + i * (78 / Math.max(1, LAYERS.length - 1)));
        E.lbl.position.set(Math.cos(ang) * rmm, Math.sin(ang) * rmm, rm * rm / dist);
        E.lbl.visible = ts > 0.6;
        E.lbl.center.set(narrow ? 1 : 0, 0.5);
      });
      regionLabels.forEach(o => { const f = o.userData.dir.dot(camDir); o.visible = f > 0.12; o.element.style.opacity = Math.min(1, (f - 0.12) * 3).toFixed(2); });
      placeLabels.forEach(o => { o.visible = o.userData.dir.dot(camDir) > 0.5 && camera.position.distanceTo(o.position) < 21; });
      declutter();
      const f0 = focus || selected;
      storyObjs.forEach(o => { if (o.ring.visible) o.ring.scale.setScalar(Math.max(sizeOf(o.s) * 1.6, camera.position.distanceTo(o.pos) * (o.s.id === f0 ? 0.034 : 0.024))); });
      applyFades(dt);
      C.renderer.render(scene, camera);
      labelRenderer.render(scene, camera);
      C.placeLabels(labelCandidates(canvas.clientWidth, canvas.clientHeight));
    }
    function resize(w, h) { camera.aspect = w / h; labelRenderer.setSize(w, h); applyViewOffset(); }

    styleStories();
    { const c = homeCam(); camera.position.copy(c.pos); controls.target.copy(c.target); }
    syncWindow();
    placeAll();
    storyObjs.forEach(o => { o.f = o.target; });
    shells.forEach(S => { S.op = S.target; });

    function applyHash(h) {
      if (h.get("flat") === "1") { setFlat(true, true); state.ts = 0; camera.position.multiplyScalar(FLAT_ZOOM); placeAll(); }
      if (h.get("from") || h.get("to")) setWindow(+(h.get("from") || Y0), +(h.get("to") || Y1));
      if (h.get("era")) { const e = M.eraById[h.get("era")]; if (!e) throw new Error("#era=" + h.get("era") + " names no era in the data"); setWindow(e.era.from, e.era.to); }
      if (h.get("region")) {
        const r = REGIONS.find(x => x.name === h.get("region"));
        if (!r) throw new Error("#region=" + h.get("region") + " names no region on the globe");
        flyToRegion(r); camera.position.copy(fly.p1); fly = null;
      }
    }

    return {
      name: "globe",
      activate() {
        active = true; controls.enabled = true;
        document.getElementById("glabels").hidden = false;
        resize(canvas.clientWidth, canvas.clientHeight);
      },
      deactivate() { active = false; controls.enabled = false; held.clear(); document.getElementById("glabels").hidden = true; },
      blur() { held.clear(); },
      frame, resize, keydown, keyup, escape: () => false, flyTo, railArrive, railRelease, nearestStory, reveal, applyHash,
      syncCamera() { camera.updateMatrixWorld(); },
      setEmphasis(sid) { focus = sid; computeTargets(); },
      applyVisibility() { computeTargets(); },
      restyle() { styleStories(); },
      setSelected(sid) {
        selected = sid;
        viewShiftTarget = sid && canvas.clientWidth > 760 ? 210 : 0;
        computeTargets();
      },
      setPanelShiftInstant() { viewShift = viewShiftTarget; applyViewOffset(); },
    };
  };
})();
