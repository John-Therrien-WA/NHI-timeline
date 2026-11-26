/* The installed app's menu, built by the desktop-app kit from the page's own commands (site/js/desktop.js), against
   the kit's stand-in desktop: the menus come in the set's order (File, Edit, View, Story, Window, Help), View > Reload
   is on Shift-Cmd-R and reloads the page, and every command of the page reaches the menu.

     node tests/desktop_menu.cjs <kit folder>      (or the kit folder in $FLUXTECH_KIT)

   The kit folder is the one holding app.js and fake-desktop.js. Prints one PASS line, or FAIL with what differs and
   exits 1. */
"use strict";
const path = require("path");
const fs = require("fs");

const kit = process.argv[2] || process.env.FLUXTECH_KIT;
if (!kit) { console.error("FAIL: name the desktop-app kit folder (the one holding app.js and fake-desktop.js) as the argument or in $FLUXTECH_KIT"); process.exit(2); }
for (const f of ["app.js", "fake-desktop.js"]) {
  if (!fs.existsSync(path.join(kit, f))) { console.error("FAIL: " + path.join(kit, f) + " does not exist; is " + kit + " the kit folder?"); process.exit(2); }
}

let reloads = 0;
globalThis.window = globalThis;
globalThis.location = { reload: () => { reloads++; }, hash: "" };
const KitApp = require(path.resolve(kit, "app.js"));
const KitFakeDesktop = require(path.resolve(kit, "fake-desktop.js"));
require(path.join(__dirname, "..", "site", "js", "desktop.js"));   // no claude here: it defines NHI.desktop and acts on nothing

async function main() {
  const fake = KitFakeDesktop.make({});
  const ran = [];
  const cmd = new Proxy({ mode: () => "corridor", story: () => null }, {
    get: (t, k) => t[k] || ((...a) => { ran.push(k + (a.length ? " " + a.join(",") : "")); }),
  });
  const app = await KitApp.boot(Object.assign(window.NHI.desktop.bootOptions("#05070d"), { desktop: fake.desktop, doc: null }));
  const commands = window.NHI.desktop.commands(cmd);
  app.register({ commands });
  await app.refreshMenu();

  const problems = [];
  const menu = fake.record.menu || [];
  const top = menu.map(m => m.label || m.role);
  const want = ["File", "editMenu", "View", "Story", "windowMenu", "Help"];
  if (JSON.stringify(top) !== JSON.stringify(want)) problems.push("the menus are " + JSON.stringify(top) + ", not " + JSON.stringify(want));
  const view = (menu.find(m => m.label === "View") || {}).submenu || [];
  const reload = view.find(i => i.label === "Reload");
  if (!reload) problems.push("View has no Reload");
  else {
    if (reload.accelerator !== "CmdOrCtrl+Shift+R") problems.push("View > Reload is on " + JSON.stringify(reload.accelerator) + ", not Shift-Cmd-R");
    reload.click({});
    if (reloads !== 1) problems.push("View > Reload reloaded the page " + reloads + " times, not once");
  }
  const items = [];
  const walk = list => list.forEach(i => { if (i.submenu) walk(i.submenu); else if (i.label) items.push(i.label); });
  walk(menu);
  const missing = commands.filter(c => !items.includes(c.title)).map(c => c.title);
  if (missing.length) problems.push("the menu leaves out " + missing.join(", "));

  if (problems.length) { console.log("FAIL: " + problems.join("; ")); process.exit(1); }
  console.log("PASS: menus " + top.join(", ") + "; Reload on Shift-Cmd-R reloads; " + commands.length + " page commands in the menu");
}
main().catch(e => { console.log("FAIL: " + (e && e.stack || e)); process.exit(1); });
