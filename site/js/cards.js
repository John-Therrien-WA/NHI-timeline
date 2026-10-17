/* Picture cards: a story's photograph standing in for its sphere in the corridor and above its marker
   on the globe. A story with `images` shows its first picture (the place at the time preferred,
   then an object, then the place today) as a camera-facing card with a thin frame in the kind's
   colour; a well-attested story with more pictures fans one or two smaller ones beside it. The
   textures are loaded lazily, when a view asks for a story that has come near, and downscaled
   through a canvas to CARD_PX on the long side, so a phone is never asked for the full image
   folder at once. A picture that cannot be drawn (a page opened from disk cannot put its own images
   into WebGL) is reported once on the console and the story keeps its sphere.
   NHI.cards(THREE) returns { pictures(s), request(s, onReady), card(kc), setCard(card, tex, h, op) }. */
(function () {
  const NHI = window.NHI = window.NHI || {};
  const CARD_PX = 384;
  const KIND_RANK = { "place-then": 0, object: 1, "place-now": 2 };
  const FAN = [3, 2, 1];                  // pictures shown per tier (well-attested, told-by-several, told-once)

  NHI.cards = function (THREE) {
    const textures = new Map();           // file -> { tex, aspect } | "loading" | "failed"
    const waiting = new Map();            // file -> [callbacks]
    let frameTex = null;

    function pictures(s) {
      if (!Array.isArray(s.images) || !s.images.length) return [];
      return s.images.slice().sort((a, b) => (KIND_RANK[a.kind] ?? 9) - (KIND_RANK[b.kind] ?? 9)).slice(0, FAN[s._tier]);
    }

    function load(file, cb) {
      const have = textures.get(file);
      if (have && have !== "loading") { if (have !== "failed") cb(have); return; }
      if (have === "loading") { waiting.get(file).push(cb); return; }
      textures.set(file, "loading"); waiting.set(file, [cb]);
      const img = new Image();
      const done = (res) => {
        textures.set(file, res);
        const cbs = waiting.get(file) || []; waiting.delete(file);
        if (res !== "failed") cbs.forEach(f => f(res));
      };
      img.onload = () => {
        try {
          const k = CARD_PX / Math.max(img.naturalWidth, img.naturalHeight);
          const w = Math.max(1, Math.round(img.naturalWidth * Math.min(1, k))), h = Math.max(1, Math.round(img.naturalHeight * Math.min(1, k)));
          const c = document.createElement("canvas"); c.width = w; c.height = h;
          c.getContext("2d").drawImage(img, 0, 0, w, h);
          const tex = new THREE.CanvasTexture(c);
          tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
          done({ tex, aspect: w / h });
        } catch (e) {
          console.warn("cards: " + file + " cannot be drawn (" + e.message + "); the story keeps its sphere");
          done("failed");
        }
      };
      img.onerror = () => { console.warn("cards: " + file + " did not load; the story keeps its sphere"); done("failed"); };
      img.src = file;
    }

    /* Ask for a story's pictures once; onReady(list) gets [{ tex, aspect, image }] in picture order as
       soon as the first one is drawn and again as each further one arrives. */
    function request(s, onReady) {
      const pics = pictures(s);
      if (!pics.length) return;
      const got = new Array(pics.length).fill(null);
      pics.forEach((image, i) => load(image.file, (res) => {
        got[i] = { tex: res.tex, aspect: res.aspect, image };
        onReady(got.filter(Boolean));
      }));
    }

    function frameTexture() {
      if (frameTex) return frameTex;
      const c = document.createElement("canvas"); c.width = c.height = 32;
      const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, 32, 32);
      frameTex = new THREE.CanvasTexture(c); frameTex.colorSpace = THREE.SRGBColorSpace;
      return frameTex;
    }

    /* A card: the picture sprite and, behind it, a frame sprite in the kind's colour. Both start
       invisible; setCard sizes and shows them. */
    function card(kc) {
      const pic = new THREE.Sprite(new THREE.SpriteMaterial({ map: null, transparent: true, depthWrite: false }));
      const frame = new THREE.Sprite(new THREE.SpriteMaterial({ map: frameTexture(), color: kc.clone(), transparent: true, depthWrite: false }));
      pic.visible = frame.visible = false;
      pic.renderOrder = 6; frame.renderOrder = 5;
      return { pic, frame, aspect: 1, image: null };
    }

    function setCard(c, h, op) {
      const w = h * c.aspect, pad = h * 0.045;
      c.pic.scale.set(w, h, 1); c.frame.scale.set(w + 2 * pad, h + 2 * pad, 1);
      c.pic.material.opacity = op; c.frame.material.opacity = op * 0.85;
      c.pic.visible = c.frame.visible = op > 0.01;
    }

    function give(c, entry) { c.pic.material.map = entry.tex; c.pic.material.needsUpdate = true; c.aspect = entry.aspect; c.image = entry.image; }

    return { pictures, request, card, setCard, give, CARD_PX };
  };
})();
