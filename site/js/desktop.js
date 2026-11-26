/* The page as a desktop app. A published copy declares the artifact capability `desktop`; in the app's own window
   (installed from the Claude desktop app) `claude.use("desktop")` gives the window, the application menu and the
   Dock icon. The desktop-app kit's `KitApp` (kit/app.js, put beside the page by the app build) sets them up the way
   every app of the set has them: the menus in the set's order (File, Edit, View, Story, Window, Help, after Claude's
   own app menu), View > Reload on Shift-Cmd-R, zoom and full screen, each menu item's key, and the fallback when the
   app refuses part of the menu, and feedback mode on `f`. This file gives the kit what is the page's own: a dark window
   with a hidden-inset title bar whose drag strip the page keeps clear (and the kit's footer below), a Dock icon drawn in
   the page's rings and kind colours, and the commands (the controller's, passed to attach(); nothing here moves the
   scene itself). The app's name and published URL are the build's record's (kit/build.js, from app.json).
   Outside the app (a browser, the artifact panel) the namespace holds at most `install`, and the Install as app button
   above the Keys shows when `install.state()` reads "available"; the kit is not booted there, so the browser keeps its
   own shortcuts. From disk or local http there is no `claude` at all and nothing here acts. No call here needs a
   permission, so app.json lists none. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};
  const SOURCE_URL = "https://github.com/John-Therrien-WA/NHI-timeline";
  const DRAG_STRIP = 36;   // px: the title bar's drag strip, which the page keeps clear of controls (CSS --chrome-top)

  // ---------- a short notice at the foot of the page ----------
  let toastTimer = null;
  function toast(msg, keep) {
    const t = document.getElementById("toast");
    t.textContent = msg; t.hidden = false;
    clearTimeout(toastTimer);
    if (!keep) toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
  }
  function refused(what) {
    return e => { console.error(what, e); toast(what + ": " + ((e && (e.message || e.code)) || String(e)) + ".", true); };
  }

  // ---------- the namespace: null without a claude object, without the capability, or when use() fails ----------
  const desktopPromise = (function () {
    const c = window.claude;
    if (!c || typeof c.use !== "function") return Promise.resolve(null);
    try { return Promise.resolve(c.use("desktop")).catch(e => { console.error("desktop capability", e); return null; }); }
    catch (e) { console.error("desktop capability", e); return Promise.resolve(null); }
  })();
  const inApp = d => !!(d && d.window && d.Menu && d.app);

  // ---------- the Dock icon: the corridor seen down its axis, the tiers as rings, stories in the kind colours ----------
  function drawIcon(g, size) {
    const S = 256;   // drawn in a 256 px box, scaled to the kit's canvas
    g.save(); g.scale(size / S, size / S);
    const m = 26, w = S - 2 * m, r = 46, cx = S / 2, cy = S / 2;
    g.beginPath(); g.roundRect(m, m, w, w, r);
    const bg = g.createRadialGradient(cx, cy, 8, cx, cy, w * 0.72);
    bg.addColorStop(0, "#16203d"); bg.addColorStop(1, "#05070d");
    g.fillStyle = bg; g.fill();
    g.save(); g.clip();
    const rings = [[34, 0.95, 2.4], [62, 0.6, 2], [90, 0.32, 1.6]];   // radius, opacity, width: well attested to told once
    rings.forEach(([rad, op, lw]) => { g.beginPath(); g.arc(cx, cy, rad, 0, Math.PI * 2); g.strokeStyle = "rgba(159,184,255," + op + ")"; g.lineWidth = lw; g.stroke(); });
    const colors = NHI.model.KINDS.map(k => NHI.model.KIND_COLORS[k]);
    colors.forEach((c, i) => {
      const a = -Math.PI / 2 + i * (Math.PI * 2 / colors.length), ring = rings[i % 3], dot = [7, 5.5, 4][i % 3];
      g.beginPath(); g.arc(cx + Math.cos(a) * ring[0], cy + Math.sin(a) * ring[0], dot, 0, Math.PI * 2); g.fillStyle = c; g.fill();
    });
    const glow = g.createRadialGradient(cx, cy, 0, cx, cy, 20);
    glow.addColorStop(0, "rgba(255,255,255,1)"); glow.addColorStop(0.35, "rgba(223,231,255,0.85)"); glow.addColorStop(1, "rgba(159,184,255,0)");
    g.fillStyle = glow; g.beginPath(); g.arc(cx, cy, 20, 0, Math.PI * 2); g.fill();
    g.restore();
    g.beginPath(); g.roundRect(m + 0.5, m + 0.5, w - 1, w - 1, r); g.strokeStyle = "rgba(150,170,220,0.35)"; g.lineWidth = 1; g.stroke();
    g.restore();
  }

  /* The build's record (kit/build.js, which the app build writes from app.json): the app's name and its published URL
     have their one home there. */
  function build() {
    const b = window.KIT_BUILD;
    if (!b || !b.name || !b.artifact) throw new Error("kit/build.js is not loaded or names no app and artifact: the app runs the page the app build makes (site/dist/)");
    return b;
  }

  /* What KitApp.boot takes from the page, for a window background `bg` (#rrggbb, the page's --bg). Feedback mode (`f`,
     or Help > Feedback Mode) keeps its tickets on the page; copy prompt is their way out, as for every app without an
     engine. */
  function bootOptions(bg) {
    const b = build();
    return {
      title: b.name,
      window: { titleBarStyle: "hiddenInset", dragHeight: DRAG_STRIP, backgroundColor: bg, width: 1440, height: 900, minWidth: 960, minHeight: 640 },
      drawIcon,
      help: [{ label: "Open in the Browser", href: b.artifact }, { label: "Source and Data on GitHub", href: SOURCE_URL }],
      feedback: { app: "nhi-timeline", tab: "page", dataAttrs: ["data-mode", "data-m", "data-key", "data-r"] },
    };
  }

  /* The page's commands for the kit's menu and keys. cmd: { key(code) a page key as if pressed, setMode(name), mode()
     the view's name, step(dir) along the rail, legend(), about(), resetTrust(), back(), forward(), story() the open
     story's id or null, copyLink() }. Every key holds Command or Control: the page's plain keys stay the page's own
     (js/app.js), and the set's keys (Shift-Cmd-R reload, Cmd-1 and Cmd-2 for the views) mean here what they mean in
     every app. */
  function commands(cmd) {
    const globe = () => cmd.mode() === "globe";
    const press = code => () => cmd.key(code);
    return [
      { id: "view.corridor", title: "Corridor", key: "CmdOrCtrl+1", menu: "View", run: () => cmd.setMode("corridor"), radio: { group: "view", on: () => !globe() } },
      { id: "view.globe", title: "Globe", key: "CmdOrCtrl+2", menu: "View", run: () => cmd.setMode("globe"), radio: { group: "view", on: globe } },
      { id: "view.reset", title: () => globe() ? "Reset the Globe" : "Back to the Entrance", key: "CmdOrCtrl+Alt+R", menu: "View", run: press("KeyR") },
      { id: "view.overview", title: "Overview", key: "CmdOrCtrl+Shift+O", menu: "View", run: press("KeyO"), enabled: () => !globe() },
      { id: "view.angle", title: "Angle by Kind or Region", key: "CmdOrCtrl+Shift+A", menu: "View", run: press("KeyC"), enabled: () => !globe() },
      { id: "view.flatten", title: "Flatten", key: "CmdOrCtrl+Shift+F", menu: "View", run: press("KeyG"), enabled: globe },
      { id: "era.previous", title: "Previous Era", key: "CmdOrCtrl+Shift+Left", menu: "View", run: () => cmd.key(globe() ? "KeyQ" : "PageUp") },
      { id: "era.next", title: "Next Era", key: "CmdOrCtrl+Shift+Right", menu: "View", run: () => cmd.key(globe() ? "KeyE" : "PageDown") },
      { id: "legend.toggle", title: "Legend and Filters", key: "CmdOrCtrl+L", menu: "View", run: () => cmd.legend(), separatorBefore: true },
      { id: "keys.toggle", title: "Keys", key: "CmdOrCtrl+K", menu: "View", run: press("KeyK") },
      { id: "trust.reset", title: "Reset Institutional Trust", key: "CmdOrCtrl+Alt+T", menu: "View", run: () => cmd.resetTrust() },
      { id: "story.back", title: "Back", key: "CmdOrCtrl+[", menu: "Story", run: () => cmd.back() },
      { id: "story.forward", title: "Forward", key: "CmdOrCtrl+]", menu: "Story", run: () => cmd.forward() },
      { id: "story.find", title: "Find a Story, Teller or Place", key: "CmdOrCtrl+F", menu: "Story", run: press("Slash"), separatorBefore: true },
      { id: "story.copy_link", title: "Copy Link to This Story", key: "CmdOrCtrl+Shift+C", menu: "Story", run: () => cmd.copyLink() },
      { id: "rail.snap", title: "Snap to the Nearest Story", key: "CmdOrCtrl+Alt+Return", menu: "Story", run: press("Tab"), separatorBefore: true },
      { id: "rail.time", title: "Ride the Time Rail", key: "CmdOrCtrl+Alt+1", menu: "Story", run: press("Digit1") },
      { id: "rail.kind", title: "Ride the Kind Rail", key: "CmdOrCtrl+Alt+2", menu: "Story", run: press("Digit2") },
      { id: "rail.strength", title: "Ride the Strength Rail", key: "CmdOrCtrl+Alt+3", menu: "Story", run: press("Digit3") },
      { id: "rail.links", title: "Ride the Links Rail", key: "CmdOrCtrl+Alt+4", menu: "Story", run: press("Digit4") },
      { id: "rail.next", title: "Next on the Rail", key: "CmdOrCtrl+Alt+Right", menu: "Story", run: () => cmd.step(1) },
      { id: "rail.previous", title: "Previous on the Rail", key: "CmdOrCtrl+Alt+Left", menu: "Story", run: () => cmd.step(-1) },
      { id: "rail.leave", title: "Free Flight, Close", key: "CmdOrCtrl+Alt+Backspace", menu: "Story", run: press("Escape") },
      { id: "help.about", title: "About This Page", key: "CmdOrCtrl+Shift+/", menu: "Help", run: () => cmd.about() },
    ];
  }

  // ---------- in the app: the kit, booted while the page loads, before the stories are drawn ----------
  function inset(on) {
    document.body.classList.toggle("app-inset", on);
    document.documentElement.style.setProperty("--chrome-top", on ? DRAG_STRIP + "px" : "0px");
  }
  const appPromise = desktopPromise.then(d => {
    if (!inApp(d)) return null;
    if (!window.KitApp || !window.FeedbackMode) throw new Error("kit/app.js or kit/feedback/ is not loaded: the app runs the page the app build makes (site/dist/), which carries the kit beside it");
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim().toLowerCase();
    if (!/^#[0-9a-f]{6}$/.test(bg)) throw new Error("the page's --bg is " + JSON.stringify(bg) + "; the window's background needs #rrggbb");
    return window.KitApp.boot(Object.assign(bootOptions(bg), { desktop: d })).then(app => {
      // the strip the window has now: the page clears it when the title bar is inset (read here, since boot resolves
      // before the kit's own read of the window's options, app.windowOptions, is sure to have settled)
      d.window.getOptions().then(r => inset(((r && r.applied) || {}).titleBarStyle === "hiddenInset"), refused("The window's options could not be read"));
      // the kit's footer (its status and version line) sits at the foot of the window: the page's bottom parts clear it
      const foot = document.getElementById("kit-chrome");
      if (!foot) throw new Error("the kit drew no #kit-chrome footer");
      const clear = () => document.documentElement.style.setProperty("--chrome-bottom", (foot.hidden ? 0 : foot.offsetHeight) + "px");
      new ResizeObserver(clear).observe(foot);
      clear();
      return app;
    });
  });
  appPromise.catch(refused("The desktop app could not be set up"));

  /* attach(cmd), from the controller once the page is drawn; cmd as for commands() without copyLink. Returns
     { refresh() }, which the controller calls when the view changes (the menu's checks and enabled items follow). */
  function attach(cmd) {
    let api = null, app = null;
    const installBtn = document.getElementById("btn-install");
    installBtn.addEventListener("click", () => {
      if (!api) return;
      api.install.request().then(r => {
        if (r === "installed") installBtn.hidden = true;
        else if (r === "failed" || r === "unavailable") toast("The app could not be installed here (" + r + ").");
      }, refused("Install as app"));
    });
    function copyLink() {
      const url = build().artifact + location.hash, what = cmd.story() ? "this story" : "this view";
      return NHI.notes.copy(url).then(ok => ok ? toast("Link to " + what + " copied.") : toast("The clipboard refused; the link to " + what + ": " + url, true));
    }

    desktopPromise.then(d => {
      if (!d) return;
      api = d;
      // a browser viewer who cannot install is told nothing: the console keeps why
      if (d.install && !inApp(d)) Promise.resolve().then(() => d.install.state()).then(s => { installBtn.hidden = s !== "available"; }, e => console.error("Install as app", e));
    });
    appPromise.then(a => {
      if (!a) return;
      app = a;
      app.register({ commands: commands(Object.assign({}, cmd, { copyLink })) });
      // the mouse's back and forward buttons do what they do in a browser
      window.addEventListener("mouseup", e => { if (e.button === 3) cmd.back(); else if (e.button === 4) cmd.forward(); });
    }, () => {})   // a failed boot is said once, where appPromise is made
      .catch(refused("The app's menu could not be set"));
    return { refresh: () => { if (app) app.refreshMenu(); } };
  }
  NHI.desktop = { attach };
})();
