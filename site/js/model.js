/* The data model shared by both views: validation (fail loud), the score recomputed at the
   reader's institutional trust, the tiers, the filters, and the lookups the panel and the rails use.
   A classic script, so the page also opens from disk; it defines window.NHI.model. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};

  const KINDS = ["sighting", "encounter", "crash-retrieval", "reverse-engineering", "program", "document", "testimony", "theory", "cosmology", "place-lore"];
  const KIND_NAMES = { "sighting": "Sighting", "encounter": "Encounter", "crash-retrieval": "Crash retrieval", "reverse-engineering": "Reverse engineering",
    "program": "Program", "document": "Document", "testimony": "Testimony", "theory": "Theory", "cosmology": "Cosmology", "place-lore": "Place lore" };
  const KIND_COLORS = { "sighting": "#5fb8ff", "encounter": "#a98bff", "crash-retrieval": "#ff9e5e", "reverse-engineering": "#ffd05c", "program": "#e3ee6a",
    "document": "#8fdc7a", "testimony": "#46d6c0", "theory": "#f08fd8", "cosmology": "#c9c9de", "place-lore": "#d9a37a" };
  const TELLING_KINDS = { firsthand: "first-hand", official: "official", journalist: "journalist", secondhand: "second-hand", researcher: "researcher", host: "host framing" };
  const REGION_ORDER = ["North America", "South America", "Atlantic", "Europe", "Africa", "Middle East", "Asia", "Pacific", "Antarctica", "Off Earth"];
  const UNPLACED = "Unplaced";
  // Tiers, foreground first. The look is what the views draw: size and brightness multipliers, and how far
  // away (in world units) a story's label still shows. A told-once story is labelled only near or selected.
  const TIERS = [
    { id: "well-attested", name: "well attested", rule: "two or more independent tellers, with a document, a witness or a record", size: 1.3, bright: 1.0, labelAt: 140 },
    { id: "told-by-several", name: "told by several", rule: "two or more independent tellers, none a witness or a record, no document", size: 1.0, bright: 0.78, labelAt: 34 },
    { id: "told-once", name: "told once", rule: "one independent teller, however often repeated", size: 0.68, bright: 0.48, labelAt: 9 },
  ];
  const TIER_INDEX = { "well-attested": 0, "told-by-several": 1, "told-once": 2 };
  const PROFILE_NUM = ["independent_tellers", "firsthand", "official_records", "official_conclusions", "journalist", "secondhand", "researcher", "host", "documents", "credited_documents", "repetitions"];
  const WEIGHT_KEYS = ["firsthand", "official", "journalist", "secondhand", "researcher", "host", "document_telling", "document_credited"];
  const DISCUSSION_KINDS = ["debunk", "rebunk", "note", "source"];
  const STORY_IMAGE_KINDS = ["object", "place-then", "place-now", "person"];
  const LICENCE_KINDS = ["free", "fair-use"];
  const S_MIN = 0.2, S_MAX = 10;   // the log scale the views and the score bar use; 1.0 is the corpus median

  function fail(msg) { throw new Error("NHI data: " + msg); }
  function need(c, msg) { if (!c) fail(msg); }
  const isNum = x => typeof x === "number" && isFinite(x);
  const isStr = x => typeof x === "string" && x.length > 0;

  function hash(str) { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 100000) / 100000; }
  function yearsText(y) { if (!y) return "undated"; return y.from === y.to ? String(y.from) : y.from + " to " + y.to; }
  function hms(sec) { sec = Math.floor(sec); const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0"); }
  function hmsToSeconds(t) {
    const parts = String(t).split(":").map(Number);
    if (!parts.length || parts.some(n => !Number.isFinite(n))) return null;
    return parts.reduce((a, n) => a * 60 + n, 0);
  }
  function youtube(id, seconds) { return "https://www.youtube.com/watch?v=" + encodeURIComponent(id) + (Number.isFinite(seconds) ? "&t=" + Math.floor(seconds) + "s" : ""); }
  function strengthOf(score) { // 0 weakest, 1 strongest, log scale from S_MIN to S_MAX
    const t = (Math.log(Math.max(S_MIN, Math.min(S_MAX, score))) - Math.log(S_MIN)) / (Math.log(S_MAX) - Math.log(S_MIN));
    return Math.min(1, Math.max(0, t));
  }

  // an image block from pipeline.build: a path relative to the page, a kind from the list, a caption, a credit and a licence
  function checkImage(x, at, kinds) {
    need(x && typeof x === "object", at + " is not an object.");
    need(isStr(x.file) && !/^([a-z]+:|\/)/i.test(x.file), at + " needs a file path relative to the page.");
    need(kinds.includes(x.kind), at + " has kind " + JSON.stringify(x.kind) + "; expected one of " + kinds.join(", ") + ".");
    need(LICENCE_KINDS.includes(x.licence_kind), at + " has licence_kind " + JSON.stringify(x.licence_kind) + "; expected free or fair-use.");
    need(isStr(x.caption) && isStr(x.credit) && isStr(x.licence), at + " needs a caption, a credit and a licence.");
    need(isStr(x.source) && /^https?:\/\//.test(x.source), at + " needs a source URL.");
  }

  // ---------- validation ----------
  function validate(D) {
    need(D && typeof D === "object", "the data is not an object.");
    need(Array.isArray(D.stories) && D.stories.length > 0, "stories must be a non-empty list.");
    need(Array.isArray(D.eras) && D.eras.length > 0, "eras must be a non-empty list.");
    need(Array.isArray(D.places), "places must be a list.");
    need(Array.isArray(D.links), "links must be a list.");
    need(D.people && typeof D.people === "object", "people must be an object keyed by id.");
    need(D.episodes && typeof D.episodes === "object", "episodes must be an object keyed by video id.");
    const sc = D.scoring;
    need(sc && typeof sc === "object", "scoring is missing; run pipeline.build after pipeline.score.");
    need(sc.weights && WEIGHT_KEYS.every(k => isNum(sc.weights[k])), "scoring.weights must give " + WEIGHT_KEYS.join(", ") + ".");
    const tr = sc.institutional_trust;
    need(tr && isNum(tr.min) && isNum(tr.max) && isNum(tr.default) && tr.min <= tr.default && tr.default <= tr.max, "scoring.institutional_trust needs min <= default <= max.");
    need(isNum(sc.median_floor) && sc.median_floor > 0, "scoring.median_floor must be a positive number.");
    D.eras.forEach((e, i) => {
      need(isStr(e.id) && isStr(e.name), "era " + i + " needs an id and a name.");
      need(Number.isInteger(e.from) && Number.isInteger(e.to) && e.to >= e.from, "era " + e.id + " needs integer years from <= to.");
      if (i > 0) need(e.from > D.eras[i - 1].to, "eras must be in time order and must not overlap (" + e.id + ").");
    });
    D.places.forEach((p, i) => {
      need(isStr(p.id) && isStr(p.name), "place " + i + " needs an id and a name.");
      need(isStr(p.region), "place " + p.id + " has no region.");
      need(p.region !== UNPLACED, "place " + p.id + " uses the reserved region name Unplaced.");
      const ll = isNum(p.lat) && isNum(p.lon);
      if (!ll) {
        need(p.lat == null && p.lon == null, "place " + p.id + " has a partial or non-numeric lat and lon.");
        need(p.region === "Off Earth", "place " + p.id + " has no lat and lon; only Off Earth places may lack them.");
      }
    });
    const eraIds = new Set(D.eras.map(e => e.id)), placeIds = new Set(D.places.map(p => p.id)), ids = new Set();
    D.stories.forEach((s, i) => {
      const at = "story " + (s && s.id ? s.id : "#" + i);
      need(isStr(s.id), at + " has no id.");
      need(!ids.has(s.id), at + " appears twice.");
      ids.add(s.id);
      need(isStr(s.title), at + " has no title.");
      need(KINDS.includes(s.kind), at + " has unknown kind " + JSON.stringify(s.kind) + "; expected one of " + KINDS.join(", ") + ".");
      need(isNum(s.score) && s.score >= 0, at + " has no numeric score.");
      need(isNum(s.attestation) && s.attestation >= 0, at + " has no numeric attestation.");
      need(TIER_INDEX[s.tier] != null, at + " has unknown tier " + JSON.stringify(s.tier) + ".");
      need(s.profile && typeof s.profile === "object" && !Array.isArray(s.profile), at + " has no profile; the page recomputes the score from it. Run pipeline.score and pipeline.build.");
      PROFILE_NUM.forEach(k => need(isNum(s.profile[k]) && s.profile[k] >= 0, at + " profile." + k + " must be a non-negative number."));
      need(typeof s.profile.contradicted === "boolean", at + " profile.contradicted must be true or false.");
      need(Array.isArray(s.tellings) && s.tellings.length > 0, at + " has no tellings; a story without a telling is a note.");
      s.tellings.forEach((t, j) => {
        need(isStr(t.teller), at + " telling " + j + " has no teller.");
        need(typeof t.quote === "string", at + " telling " + j + " has no quote.");
        need(t.episode || t.document, at + " telling " + j + " names neither an episode nor a document.");
        if (t.episode) need(isNum(t.from_s), at + " telling " + j + " has an episode but no from_s time code.");
        need(Array.isArray(t.cites), at + " telling " + j + " has no cites list.");
        need(Array.isArray(t.repeats) && t.repeats.every(c => t.cites.includes(c)), at + " telling " + j + " has no repeats list, or one naming a person it does not cite: run pipeline.build.");
        need(Array.isArray(t.documents || []), at + " telling " + j + " has a malformed documents list.");
      });
      if (s.years != null) need(isNum(s.years.from) && isNum(s.years.to) && s.years.to >= s.years.from, at + " has malformed years.");
      if (s.era != null) need(eraIds.has(s.era), at + " names unknown era " + JSON.stringify(s.era) + ".");
      if (s.place != null) need(placeIds.has(s.place), at + " names unknown place " + JSON.stringify(s.place) + ".");
      need(Array.isArray(s.documents || []), at + " has a malformed documents list.");
      need(Array.isArray(s.related || []), at + " has a malformed related list.");
      if (s.discussion != null) {
        need(Array.isArray(s.discussion), at + " discussion must be a list.");
        s.discussion.forEach((x, j) => {
          need(x && DISCUSSION_KINDS.includes(x.kind), at + " discussion " + j + " has kind " + JSON.stringify(x && x.kind) + "; expected one of " + DISCUSSION_KINDS.join(", ") + ".");
          need(isStr(x.by) && isStr(x.text), at + " discussion " + j + " needs by and text.");
          if (x.time != null) need(hmsToSeconds(x.time) != null, at + " discussion " + j + " has a time that is not h:mm:ss.");
        });
      }
      if (s.notes_open != null) need(Number.isInteger(s.notes_open) && s.notes_open >= 0, at + " notes_open must be a count.");
      if (s.images != null) {
        need(Array.isArray(s.images), at + " images must be a list.");
        s.images.forEach((x, j) => {
          checkImage(x, at + " image " + j, STORY_IMAGE_KINDS);
          if (x.kind === "person") need(isStr(x.person) && x.licence_kind === "free", at + " image " + j + " is a person picture; it names the person and is free-licensed only.");
        });
      }
    });
    Object.keys(D.people).forEach(id => {
      const im = D.people[id] && D.people[id].image;
      if (im == null) return;
      checkImage(im, "person " + id + " image", ["headshot"]);
      need(im.licence_kind === "free", "person " + id + " has a fair-use headshot; a headshot is free-licensed only.");
    });
    D.links.forEach((l, i) => {
      need(ids.has(l.a) && ids.has(l.b), "link " + i + " (" + l.a + " to " + l.b + ") names a story that does not exist.");
      need(isStr(l.relation), "link " + i + " has no relation.");
    });
    D.stories.forEach(s => (s.related || []).forEach(r => need(ids.has(r.story) && isStr(r.relation), "story " + s.id + " has a related entry to unknown story " + r.story + ".")));
  }

  // ---------- the score at any knob (scoring.md, the same arithmetic as pipeline/score.py) ----------
  function attestationOf(p, W, trust) {
    const a = W.firsthand * p.firsthand + W.official * trust * (p.official_records + p.official_conclusions)
      + W.journalist * p.journalist + W.secondhand * p.secondhand + W.researcher * p.researcher + W.host * p.host
      + W.document_telling * p.documents + W.document_credited * p.credited_documents;
    return Math.round(a * 1e4) / 1e4;
  }
  function tierOf(p) {
    if (p.independent_tellers >= 2) return (p.documents + p.credited_documents || p.firsthand || p.official_records) ? "well-attested" : "told-by-several";
    return "told-once";
  }
  function median(xs) {
    const v = xs.slice().sort((a, b) => a - b), n = v.length, m = n >> 1;
    return n % 2 ? v[m] : (v[m - 1] + v[m]) / 2;
  }

  function build(D) {
    validate(D);
    const M = { D, KINDS, KIND_NAMES, KIND_COLORS, TELLING_KINDS, TIERS, TIER_INDEX, UNPLACED, S_MIN, S_MAX, hash, yearsText, hms, hmsToSeconds, youtube, strengthOf };
    const W = D.scoring.weights, TR = D.scoring.institutional_trust;
    M.trust = { min: TR.min, max: TR.max, def: TR.default, value: TR.default };
    M.eraById = {}; D.eras.forEach((e, i) => { M.eraById[e.id] = { era: e, index: i }; });
    M.placeById = {}; D.places.forEach(p => { M.placeById[p.id] = p; });
    M.storyById = {}; D.stories.forEach(s => { M.storyById[s.id] = s; });
    // an id that a fold retired opens the story that absorbed it
    M.aliasOf = Object.assign({}, D.aliases || {});
    D.stories.forEach(s => (s.aliases || []).forEach(a => { M.aliasOf[a] = s.id; }));
    M.resolve = id => M.storyById[id] ? id : (M.aliasOf[id] && M.storyById[M.aliasOf[id]] ? M.aliasOf[id] : null);
    M.personName = id => (D.people[id] && D.people[id].name) || id;
    M.regionOf = s => s.place ? M.placeById[s.place].region : UNPLACED;
    // the free text of an unresolved place, or "no place given" when the extractor gave none worth showing
    M.unplacedKey = s => { const t = (s.place_text || "").trim(); return (!t || /^(unspecified|unknown|none|n\/a)$/i.test(t)) ? "no place given" : t; };
    M.placeText = s => {
      if (s.place) return M.placeById[s.place].name;
      const k = M.unplacedKey(s);
      return k === "no place given" ? k : k + " (not placed)";
    };
    M.docTitle = new Map();
    D.stories.forEach(s => (s.documents || []).forEach(x => { if (x && x.id) M.docTitle.set(x.id, x.title || x.id); }));

    // links: the build's list and every story's related entries, one per pair and relation
    const key = (a, b, r) => (a < b ? a + "|" + b : b + "|" + a) + "|" + r;
    const lm = new Map();
    D.links.forEach(l => lm.set(key(l.a, l.b, l.relation), { a: l.a, b: l.b, relation: l.relation, note: l.note || "" }));
    D.stories.forEach(s => (s.related || []).forEach(r => { const k = key(s.id, r.story, r.relation); if (!lm.has(k) && r.story !== s.id) lm.set(k, { a: s.id, b: r.story, relation: r.relation, note: r.note || "" }); }));
    M.links = [...lm.values()];
    const byId = new Map();
    M.links.forEach(l => [[l.a, l.b], [l.b, l.a]].forEach(([x, y]) => { if (!byId.has(x)) byId.set(x, []); byId.get(x).push({ other: y, relation: l.relation, note: l.note }); }));
    M.linksOf = id => byId.get(id) || [];

    // voices and sources shared between stories: highlight on hover only, never a line
    const tokStories = new Map(), storyToks = new Map();
    const addTok = (sid, t) => { if (!tokStories.has(t)) tokStories.set(t, new Set()); tokStories.get(t).add(sid); storyToks.get(sid).add(t); };
    D.stories.forEach(s => {
      storyToks.set(s.id, new Set());
      s.tellings.forEach(t => { addTok(s.id, "p:" + t.teller); t.cites.forEach(c => addTok(s.id, "p:" + c)); if (t.document) addTok(s.id, "d:" + t.document); (t.documents || []).forEach(x => addTok(s.id, "d:" + x)); });
      (s.documents || []).forEach(x => addTok(s.id, "d:" + x.id));
    });
    M.sharing = sid => { const out = new Set(); storyToks.get(sid).forEach(t => tokStories.get(t).forEach(o => { if (o !== sid) out.add(o); })); return out; };

    // the chronological order every view and the Time rail share: dated by years, then undated by title
    M.chrono = (a, b) => ((a.years ? 0 : 1) - (b.years ? 0 : 1)) ||
      (a.years && b.years ? (a.years.from - b.years.from) || (a.years.to - b.years.to) : 0) ||
      (a.title < b.title ? -1 : a.title > b.title ? 1 : 0) || (a.id < b.id ? -1 : 1);
    M.byTime = D.stories.slice().sort(M.chrono);
    M.byTime.forEach((s, i) => { s._order = i; });

    M.kindCounts = {}; D.stories.forEach(s => { M.kindCounts[s.kind] = (M.kindCounts[s.kind] || 0) + 1; });
    M.regionCounts = new Map(); D.stories.forEach(s => { const r = M.regionOf(s); M.regionCounts.set(r, (M.regionCounts.get(r) || 0) + 1); });
    M.regionKeys = REGION_ORDER.filter(r => M.regionCounts.has(r))
      .concat([...M.regionCounts.keys()].filter(r => !REGION_ORDER.includes(r) && r !== UNPLACED).sort())
      .concat(M.regionCounts.has(UNPLACED) ? [UNPLACED] : []);

    // tiers come from the profile and never move with the knob
    D.stories.forEach(s => { s._tierId = tierOf(s.profile); s._tier = TIER_INDEX[s._tierId]; });
    M.tierCounts = [0, 0, 0]; D.stories.forEach(s => M.tierCounts[s._tier]++);

    // recompute every story at a knob value: s._att, s._score, s._str, and M.median
    M.rescore = function (trust) {
      M.trust.value = trust;
      const att = D.stories.map(s => (s._att = attestationOf(s.profile, W, trust)));
      M.median = Math.max(D.scoring.median_floor, median(att));
      D.stories.forEach(s => { s._score = s._att / M.median; s._str = strengthOf(s._score); });
      M.byStrength = D.stories.slice().sort((a, b) => b._score - a._score || a._order - b._order);
    };
    // the stored values were written at the default knob: the recompute must reproduce them to three decimals
    M.checkStored = function () {
      const bad = [];
      M.rescore(M.trust.def);
      D.stories.forEach(s => {
        if (Math.abs(s._att - s.attestation) > 0.0005 + 1e-9) bad.push(s.id + ": attestation " + s._att.toFixed(4) + " recomputed, " + s.attestation + " stored");
        else if (Math.abs(s._score - s.score) > 0.0005 + 1e-9) bad.push(s.id + ": score " + s._score.toFixed(4) + " recomputed, " + s.score + " stored");
        if (s._tierId !== s.tier) bad.push(s.id + ": tier " + s._tierId + " from the profile, " + s.tier + " stored");
      });
      if (isNum(D.scoring.median_attestation) && Math.abs(M.median - D.scoring.median_attestation) > 0.0005) bad.push("median attestation " + M.median.toFixed(4) + " recomputed, " + D.scoring.median_attestation + " stored");
      return bad;
    };

    // filters: hidden kinds, regions and tiers
    M.hidden = { kind: new Set(), region: new Set(), tier: new Set() };
    M.isVisible = s => !M.hidden.kind.has(s.kind) && !M.hidden.region.has(M.regionOf(s)) && !M.hidden.tier.has(s._tierId);

    // a mismatch means the build or the recompute is wrong: the page refuses to draw
    const bad = M.checkStored();
    if (bad.length) fail("recompute differs from the stored values for " + bad.length + (bad.length === 1 ? " item" : " items") + ":\n" +
      bad.slice(0, 12).join("\n") + (bad.length > 12 ? "\n..." : ""));
    return M;
  }

  NHI.model = { build, KINDS, KIND_COLORS, TIERS };
})();
