/* The page as a desktop app. A published copy declares the artifact capability `desktop`; in the app's own window
   (installed from the Claude desktop app) `claude.use("desktop")` gives the window, the application menu and the
   Dock icon, and this file sets them up: a dark window with a hidden-inset title bar whose drag strip the page keeps
   clear, a Dock icon drawn here in the page's own rings and kind colours, and a menu naming the page's own commands
   (the controller's, passed to attach(); nothing here moves the scene itself). Outside the app (a browser, the
   artifact panel) the namespace holds at most `install`, and the About strip's Install app button shows when
   `install.state()` reads "available". From disk or local http there is no `claude` at all and nothing here acts.
   No call here needs a permission, so the manifest tag in index.html lists none. Every desktop call is caught: a
   refusal shows as a short notice and never as the page's fatal screen. */
(function () {
  "use strict";
  const NHI = window.NHI = window.NHI || {};
  const PUBLIC_URL = "https://claude.ai/artifact/UM72XZP7QvQ2N5assaVmgP";   // the published page; a copied link is this plus the hash
  const SOURCE_URL = "https://github.com/John-Therrien-WA/NHI-timeline";
  const DRAG_STRIP = 36;   // px: the title bar's drag strip, which the page keeps clear of controls (CSS --chrome-top)
  const TRIES_KEY = "nhi-window-tries";   // sessionStorage: window option sets that reloaded the page, against a reload loop

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

  // ---------- the window: one constant set of options, applied only when the window does not have them ----------
  function windowOptions() {
    const bg = getComputedStyle(document.documentElement).getPropertyValue("--bg").trim().toLowerCase();
    if (!/^#[0-9a-f]{6}$/.test(bg)) throw new Error("the page's --bg is " + JSON.stringify(bg) + "; the window's background needs #rrggbb");
    return { titleBarStyle: "hiddenInset", dragHeight: DRAG_STRIP, backgroundColor: bg, width: 1440, height: 900, minWidth: 960, minHeight: 640 };
  }
  // width and height are left out of the comparison: the person resizes the window, and setting them again would reload the page
  const HELD = ["titleBarStyle", "dragHeight", "backgroundColor", "minWidth", "minHeight"];
  const has = (applied, want) => HELD.every(k => String((applied || {})[k]).toLowerCase() === String(want[k]).toLowerCase());
  function inset(on) {
    document.body.classList.toggle("app-inset", on);
    document.documentElement.style.setProperty("--chrome-top", on ? DRAG_STRIP + "px" : "0px");
  }
  function tries(n) { try { if (n === undefined) return parseInt(sessionStorage.getItem(TRIES_KEY) || "0", 10); sessionStorage.setItem(TRIES_KEY, String(n)); } catch (e) { return 0; } return n; }
  function setUpWindow(d) {
    const want = windowOptions();
    return d.window.getOptions().then(({ applied }) => {
      if (has(applied, want)) { tries(0); inset(applied.titleBarStyle === "hiddenInset"); return; }
      if (tries() >= 2) throw new Error("the window was given its options twice and still does not report them; it keeps its present look");
      return d.window.setOptions(want).then(r => {
        if (r.reloading) { tries(tries() + 1); return; }   // the window is rebuilt and the page loads again with them
        tries(0);
        if (r.applied === "now") inset(want.titleBarStyle === "hiddenInset");
        else toast("The window takes its new look the next time the app opens.");
      });
    });
  }

  // ---------- the Dock icon: the corridor seen down its axis, the tiers as rings, stories in the kind colours ----------
  function drawIcon() {
    const S = 256, cv = document.createElement("canvas");
    cv.width = cv.height = S;
    const g = cv.getContext("2d"), m = 26, w = S - 2 * m, r = 46, cx = S / 2, cy = S / 2;
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
    return cv.toDataURL("image/png");
  }

  // the window and the icon start while the page loads, before the stories are drawn
  desktopPromise.then(d => {
    if (!inApp(d)) return;
    setUpWindow(d).catch(refused("The window's look could not be set"));
    Promise.resolve().then(() => d.app.dock.setIcon(drawIcon())).catch(refused("The Dock icon could not be set"));
  });

  /* attach(cmd), from the controller once the page is drawn. cmd: { key(code) a page key as if pressed, setMode(name),
     mode() the view's name, step(dir) along the rail, legend(), about(), resetTrust(), back(), forward(), story() the
     open story's id or null }. Returns { refresh() }, which the controller calls when the view changes. */
  function attach(cmd) {
    let api = null;
    const installBtn = document.getElementById("btn-install");
    installBtn.addEventListener("click", () => {
      if (!api) return;
      api.install.request().then(r => {
        if (r === "installed") installBtn.hidden = true;
        else if (r === "failed" || r === "unavailable") toast("The app could not be installed here (" + r + ").");
      }, refused("Install as app"));
    });

    function copyLink() {
      const url = PUBLIC_URL + location.hash, what = cmd.story() ? "this story" : "this view";
      NHI.notes.copy(url).then(ok => ok ? toast("Link to " + what + " copied.") : toast("The clipboard refused; the link to " + what + ": " + url, true));
    }
    const isGlobe = () => cmd.mode() === "globe";
    const item = (label, accelerator, click, extra) => Object.assign({ label, accelerator, click }, extra || {});
    function template(withRoles) {
      const viewTail = withRoles ? [
        { type: "separator" },
        { role: "resetZoom", label: "Actual Size", accelerator: "CmdOrCtrl+0" },
        { role: "zoomIn", label: "Zoom In", accelerator: "CmdOrCtrl+Plus" },
        { role: "zoomOut", label: "Zoom Out", accelerator: "CmdOrCtrl+-" },
        { type: "separator" },
        item("Reload", "CmdOrCtrl+R", () => location.reload()),
        { role: "togglefullscreen", label: "Toggle Full Screen" },
      ] : [{ type: "separator" }, item("Reload", "CmdOrCtrl+R", () => location.reload())];
      return [
        { role: "editMenu" },
        { label: "Story", submenu: [
          item("Back", "CmdOrCtrl+[", () => cmd.back()),
          item("Forward", "CmdOrCtrl+]", () => cmd.forward()),
          { type: "separator" },
          item("Find a Story, Teller or Place", "CmdOrCtrl+F", () => cmd.key("Slash")),
          item("Copy Link to This Story", "CmdOrCtrl+Shift+C", copyLink),
          { type: "separator" },
          item("Snap to the Nearest Story", "CmdOrCtrl+Alt+Enter", () => cmd.key("Tab")),
          item("Ride the Time Rail", "CmdOrCtrl+Alt+1", () => cmd.key("Digit1")),
          item("Ride the Kind Rail", "CmdOrCtrl+Alt+2", () => cmd.key("Digit2")),
          item("Ride the Strength Rail", "CmdOrCtrl+Alt+3", () => cmd.key("Digit3")),
          item("Ride the Links Rail", "CmdOrCtrl+Alt+4", () => cmd.key("Digit4")),
          item("Next on the Rail", "CmdOrCtrl+Alt+Right", () => cmd.step(1)),
          item("Previous on the Rail", "CmdOrCtrl+Alt+Left", () => cmd.step(-1)),
          item("Free Flight, Close", "CmdOrCtrl+Alt+Backspace", () => cmd.key("Escape")),
        ] },
        { label: "View", submenu: [
          item("Corridor", "CmdOrCtrl+1", () => cmd.setMode("corridor"), { type: "radio", checked: !isGlobe() }),
          item("Globe", "CmdOrCtrl+2", () => cmd.setMode("globe"), { type: "radio", checked: isGlobe() }),
          { type: "separator" },
          item(isGlobe() ? "Reset the Globe" : "Back to the Entrance", "CmdOrCtrl+Shift+R", () => cmd.key("KeyR")),
          item("Overview", "CmdOrCtrl+Shift+O", () => cmd.key("KeyO"), { enabled: !isGlobe() }),
          item("Angle by Kind or Region", "CmdOrCtrl+Shift+A", () => cmd.key("KeyC"), { enabled: !isGlobe() }),
          item("Flatten", "CmdOrCtrl+Shift+F", () => cmd.key("KeyF"), { enabled: isGlobe() }),
          item("Previous Era", "CmdOrCtrl+Shift+Left", () => cmd.key(isGlobe() ? "KeyQ" : "PageUp")),
          item("Next Era", "CmdOrCtrl+Shift+Right", () => cmd.key(isGlobe() ? "KeyE" : "PageDown")),
          { type: "separator" },
          item("Legend and Filters", "CmdOrCtrl+L", () => cmd.legend()),
          item("Keys", "CmdOrCtrl+K", () => cmd.key("KeyK")),
          item("Reset Institutional Trust", "CmdOrCtrl+Alt+T", () => cmd.resetTrust()),
          ...viewTail,
        ] },
        { label: "Help", submenu: [
          item("About This Page", "CmdOrCtrl+Shift+/", () => cmd.about()),
          { type: "separator" },
          { label: "Open in the Browser", href: PUBLIC_URL },
          { label: "Source and Data on GitHub", href: SOURCE_URL },
        ] },
      ];
    }
    // the zoom and full-screen roles are Electron's; a desktop app that refuses them gets the menu without them, said once
    let roles = true;
    function setMenu() {
      return api.Menu.setApplicationMenu(template(roles)).catch(e => {
        if (!roles) throw e;
        roles = false;
        return api.Menu.setApplicationMenu(template(false)).then(() => toast("Zoom and full screen are not in this app's menu (" + ((e && e.message) || e) + ")."));
      }).catch(refused("The app's menu could not be set"));
    }

    desktopPromise.then(d => {
      if (!d) return;
      api = d;
      if (d.install) d.install.state().then(s => { installBtn.hidden = s !== "available"; }, refused("Install as app"));
      if (!inApp(d)) return;
      setMenu();
      // the mouse's back and forward buttons do what they do in a browser
      window.addEventListener("mouseup", e => { if (e.button === 3) cmd.back(); else if (e.button === 4) cmd.forward(); });
    });
    return { refresh: () => { if (inApp(api)) setMenu(); } };
  }
  NHI.desktop = { attach };
})();
