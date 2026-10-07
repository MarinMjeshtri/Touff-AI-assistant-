/* Touff settings. Python calls the global reload(); everything else talks to window.pywebview.api. */
let S = null; // everything from Python (get_all)
const api = () => window.pywebview.api;
const $ = (id) => document.getElementById(id);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ---------------------------------------------------------------- icons
const ICONS = {
  home: '<path d="M3.5 10.5 12 3.5l8.5 7"/><path d="M5.5 9v10.5a1 1 0 0 0 1 1H10v-5.5h4v5.5h3.5a1 1 0 0 0 1-1V9"/>',
  zap: '<path d="M13 2.5 4.5 13.5H11l-1 8 8.5-11H12z"/>',
  book: '<path d="M4.5 19V5.5a2 2 0 0 1 2-2h13v14h-13a2 2 0 0 0-2 2zm0 0a2 2 0 0 0 2 2h13"/><path d="M12 7.2c-.9-1-2.6-.7-2.6.8 0 1.4 2.6 3 2.6 3s2.6-1.6 2.6-3c0-1.5-1.7-1.8-2.6-.8z"/>',
  grid: '<rect x="3.5" y="3.5" width="7" height="7" rx="2"/><rect x="13.5" y="3.5" width="7" height="7" rx="2"/><rect x="3.5" y="13.5" width="7" height="7" rx="2"/><rect x="13.5" y="13.5" width="7" height="7" rx="3.5"/>',
  history: '<path d="M3.5 12a8.5 8.5 0 1 0 2.6-6.1L3.5 8.5"/><path d="M3.5 3.5v5h5"/><path d="M12 7.5V12l3 2"/>',
  sliders: '<path d="M4 6.5h9M17 6.5h3M4 12h3M11 12h9M4 17.5h11M19 17.5h1"/><circle cx="15" cy="6.5" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="17.5" r="2"/>',
  devil: '<path d="M5.5 3.5c0 2.5 1 4 2.5 4.8M18.5 3.5c0 2.5-1 4-2.5 4.8"/><circle cx="12" cy="13.5" r="7.5"/><path d="M8.8 12.2l2 1M15.2 12.2l-2 1M9.3 16.3c1.6 1.1 3.8 1.1 5.4 0"/>',
  minus: '<path d="M5 12h14"/>',
  x: '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
  mic: '<rect x="9" y="2.5" width="6" height="12" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5v4"/>',
  sparkles: '<path d="M11 3.5l1.7 4.6 4.6 1.7-4.6 1.7L11 16.1l-1.7-4.6-4.6-1.7 4.6-1.7z"/><path d="M18.5 14.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
  arrowUp: '<path d="M12 19V5.5M6 11.5l6-6 6 6"/>',
  arrowRight: '<path d="M5 12h14M13.5 6.5 19 12l-5.5 5.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  tag: '<path d="M3.5 12.3V4.5a1 1 0 0 1 1-1h7.8l8.6 8.6a1.5 1.5 0 0 1 0 2.1l-6.7 6.7a1.5 1.5 0 0 1-2.1 0z"/><circle cx="8" cy="8" r="1.4"/>',
  note: '<path d="M14.5 3.5H6.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-10z"/><path d="M14.5 3.5v5h5M8.5 13h7M8.5 16.5h5"/>',
  refresh: '<path d="M20 11.5A8 8 0 0 0 5.7 7L4 8.7"/><path d="M4 4v4.7h4.7"/><path d="M4 12.5A8 8 0 0 0 18.3 17l1.7-1.7"/><path d="M20 20v-4.7h-4.7"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="m20 20-4.2-4.2"/>',
  wave: '<path d="M3.5 10.5v3M7.25 8v8M11 4.5v15M14.75 8v8M18.5 6.5v11M21 11v2"/>',
  file: '<path d="M14 3.5H6.5a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V9z"/><path d="M14 3.5V9h5.5"/><path d="M9 13v3M12 11.5v6M15 13.5v2"/>',
  feather: '<path d="M20 4c-6 0-11 3.5-12.5 10.5L6 20"/><path d="M8.2 13.8C14 14 18 10 20 4M10.5 10h5"/>',
  gauge: '<path d="M4.3 17.5a8.5 8.5 0 1 1 15.4 0"/><path d="M12 14l4-4.5"/><circle cx="12" cy="14" r="1.3"/>',
  volume: '<path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z"/><path d="M15.5 9.3a3.8 3.8 0 0 1 0 5.4M18.2 6.8a7.5 7.5 0 0 1 0 10.4"/>',
  play: '<path d="M7.5 5.2v13.6a.8.8 0 0 0 1.2.7l10.6-6.8a.8.8 0 0 0 0-1.4L8.7 4.5a.8.8 0 0 0-1.2.7z"/>',
  ear: '<path d="M7 9a5 5 0 0 1 10 0c0 3-2.5 4-2.5 6.5a3 3 0 0 1-5.5 1.7"/><path d="M10 9.5a2 2 0 0 1 4 0c0 1.2-1.3 1.5-1.3 2.7"/>',
  timer: '<circle cx="12" cy="13.5" r="7.5"/><path d="M12 9.5v4l2.5 2M9.5 2.5h5M19 6l1.5-1.5"/>',
  bell: '<path d="M6 9.5a6 6 0 0 1 12 0c0 5.5 2.5 7 2.5 7h-17S6 15 6 9.5z"/><path d="M10 20a2.2 2.2 0 0 0 4 0"/>',
  message: '<path d="M4.5 4.5h15a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1h-8.5l-4.5 4v-4h-2a1 1 0 0 1-1-1v-10a1 1 0 0 1 1-1z"/><path d="M8.5 10.5h.01M12 10.5h.01M15.5 10.5h.01"/>',
  cpu: '<rect x="6" y="6" width="12" height="12" rx="2.5"/><rect x="9.5" y="9.5" width="5" height="5" rx="1"/><path d="M9.5 3v3M14.5 3v3M9.5 18v3M14.5 18v3M3 9.5h3M3 14.5h3M18 9.5h3M18 14.5h3"/>',
  brainy: '<path d="M12 5.5a3 3 0 0 0-5.6-1.2A3 3 0 0 0 4 8.5a3.2 3.2 0 0 0 .4 5.6A3.3 3.3 0 0 0 8 19a3 3 0 0 0 4 .5z"/><path d="M12 5.5a3 3 0 0 1 5.6-1.2A3 3 0 0 1 20 8.5a3.2 3.2 0 0 1-.4 5.6A3.3 3.3 0 0 1 16 19a3 3 0 0 1-4 .5z"/><path d="M12 5.5v14"/>',
  plug: '<path d="M9 3v4.5M15 3v4.5M6.5 7.5h11V11a5.5 5.5 0 0 1-11 0zM12 16.5V21"/>',
  power: '<path d="M12 3v8"/><path d="M6.6 6.6a7.6 7.6 0 1 0 10.8 0"/>',
  flame: '<path d="M12 21a6.8 6.8 0 0 0 6.8-6.8c0-3.9-2.8-5.8-4-9.7-1.9 1.9-2.4 3.9-2.4 5.3-1-.7-1.9-2.2-1.9-3.6-2.9 2.4-5.3 5.3-5.3 8A6.8 6.8 0 0 0 12 21z"/><path d="M12 21a2.8 2.8 0 0 1-2.8-2.8c0-1.6 1.4-2.6 2.8-4.4 1.4 1.8 2.8 2.8 2.8 4.4A2.8 2.8 0 0 1 12 21z"/>',
  skull: '<path d="M12 3a7.5 7.5 0 0 0-4.8 13.3V19a1 1 0 0 0 1 1h7.6a1 1 0 0 0 1-1v-2.7A7.5 7.5 0 0 0 12 3z"/><circle cx="9.2" cy="11.5" r="1.6"/><circle cx="14.8" cy="11.5" r="1.6"/><path d="M10.5 20v-2.5M13.5 20v-2.5"/>',
  bug: '<rect x="7.5" y="7.5" width="9" height="13" rx="4.5"/><path d="M12 11v9.5M7.5 12.5h-4M20.5 12.5h-4M7.5 17H4.5M19.5 17h-3M9 7.8 7 5.5M15 7.8l2-2.3M9.5 7.5a2.5 2.5 0 0 1 5 0"/>',
  folder: '<path d="M3.5 7a2 2 0 0 1 2-2h3.8l2 2.5h7.2a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z"/>',
  pencil: '<path d="M4 20h4L18.8 9.2a2.8 2.8 0 0 0-4-4L4 16z"/><path d="M13.5 6.5l4 4"/>',
  trash: '<path d="M4.5 7h15M10 11v6M14 11v6"/><path d="M6.5 7l.9 12.2a1 1 0 0 0 1 .8h7.2a1 1 0 0 0 1-.8L17.5 7M9.5 7V4.5h5V7"/>',
  chevUp: '<path d="m6.5 14.5 5.5-5.5 5.5 5.5"/>',
  chevDown: '<path d="m6.5 9.5 5.5 5.5 5.5-5.5"/>',
  gamepad: '<path d="M7 8h10a4.5 4.5 0 0 1 4.4 5.4l-.6 3a2.6 2.6 0 0 1-4.5 1.2L14.5 15.5h-5l-1.8 2.1a2.6 2.6 0 0 1-4.5-1.2l-.6-3A4.5 4.5 0 0 1 7 8z"/><path d="M7.5 11v3M6 12.5h3M15.5 11.5h.01M17.5 13.5h.01"/>',
  window: '<rect x="3.5" y="4.5" width="17" height="15" rx="2.5"/><path d="M3.5 9h17M6.8 6.8h.01M9.3 6.8h.01"/>',
  globe: '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5c2.3 2.4 3.4 5.2 3.4 8.5s-1.1 6.1-3.4 8.5c-2.3-2.4-3.4-5.2-3.4-8.5S9.7 5.9 12 3.5z"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5a7.5 7.5 0 0 1 15 0"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5M12 8h.01"/>',
};
const icon = (name, cls = "") => `<svg class="i ${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICONS[name] || ""}</svg>`;
function hydrateIcons(root = document) { $$("i[data-icon]", root).forEach((el) => { el.outerHTML = icon(el.dataset.icon); }); }
hydrateIcons();

// ---------------------------------------------------------------- toasts & modal
const TOAST_ICON = { ok: "check", evil: "devil", info: "sparkles", warn: "info" };
function toast(msg, kind) {
  kind = kind || (/saved|done|learned|noted|ran it|deleted/i.test(msg) ? "ok" : "info");
  msg = String(msg).replace(/\s*✓\s*$/, "");
  const box = $("toasts");
  const last = box.lastElementChild;
  if (last && last._msg === msg && !last.classList.contains("out")) { clearTimeout(last._h); last._h = setTimeout(() => dropToast(last), 2400); return; }
  const t = document.createElement("div");
  t.className = "toast " + kind; t._msg = msg;
  t.innerHTML = `<span class="ti">${icon(TOAST_ICON[kind] || "sparkles")}</span><span>${esc(msg)}</span>`;
  box.appendChild(t);
  while (box.children.length > 3) box.firstElementChild.remove();
  t._h = setTimeout(() => dropToast(t), 2400);
}
function dropToast(t) { t.classList.add("out"); setTimeout(() => t.remove(), 300); }

function ask(title, text, placeholder = "") {
  return new Promise((resolve) => {
    const m = $("modal"), inp = $("mInput");
    $("mTitle").textContent = title; $("mText").textContent = text; inp.value = ""; inp.placeholder = placeholder;
    m.classList.add("on"); setTimeout(() => inp.focus(), 50);
    const done = (v) => { m.classList.remove("on"); inp.onkeydown = $("mOk").onclick = $("mCancel").onclick = m.onclick = null; resolve(v); };
    $("mOk").onclick = () => done(inp.value.trim() || null);
    $("mCancel").onclick = () => done(null);
    m.onclick = (e) => { if (e.target === m) done(null); };
    inp.onkeydown = (e) => { if (e.key === "Enter") done(inp.value.trim() || null); if (e.key === "Escape") done(null); };
  });
}

// ---------------------------------------------------------------- window chrome (frameless)
$("winMin").onclick = () => { try { api().minimize_settings(); } catch (e) {} };
$("winClose").onclick = () => { try { api().hide_settings(); } catch (e) {} };
$$(".rz").forEach((h) => h.addEventListener("pointerdown", (e) => {
  if (!window.pywebview || !api().resize_settings) return;
  e.preventDefault(); h.setPointerCapture(e.pointerId);
  const dir = h.dataset.dir, sx = e.screenX, sy = e.screenY, w0 = window.innerWidth, h0 = window.innerHeight;
  let pending = null, busy = false;
  const pump = async () => {
    if (busy || !pending) return;
    busy = true; const p = pending; pending = null;
    try { await api().resize_settings(p[0], p[1]); } catch (err) {}
    busy = false; pump();
  };
  const move = (ev) => {
    pending = [Math.max(720, Math.round(dir.includes("r") ? w0 + ev.screenX - sx : w0)),
               Math.max(520, Math.round(dir.includes("b") ? h0 + ev.screenY - sy : h0))];
    pump();
  };
  const up = () => { h.removeEventListener("pointermove", move); h.removeEventListener("pointerup", up); };
  h.addEventListener("pointermove", move); h.addEventListener("pointerup", up);
}));

// ---------------------------------------------------------------- tabs
const TITLES = { home: "Home", commands: "Commands", memories: "Memories", apps: "Apps", history: "History", settings: "Settings", developer: "Developer" };
let current = "home";
$$("nav a[data-tab]").forEach((a) => {
  a.onclick = () => showTab(a.dataset.tab);
  a.onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); showTab(a.dataset.tab); } };
});
function showTab(name) {
  const changed = name !== current;
  current = name;
  $$("nav a").forEach((x) => x.classList.toggle("on", x.dataset.tab === name));
  $$("section").forEach((x) => {
    const on = x.id === name;
    x.classList.toggle("on", on);
    if (on && changed) { x.classList.remove("enter"); void x.offsetWidth; x.classList.add("enter"); }
  });
  document.body.classList.toggle("evil", name === "developer");
  $("crumb").innerHTML = `<span class="nm">${esc(S ? S.config.name : "Touff")}</span> &nbsp;/&nbsp; <b>${TITLES[name] || name}</b>`;
  if (changed) $("main").scrollTop = 0;
  moveIndicator();
  requestAnimationFrame(layoutSegs);
}
function moveIndicator() {
  const a = document.querySelector("nav a.on"), ind = $("navInd");
  if (!a || a.offsetParent === null) { ind.style.opacity = 0; return; }
  ind.style.opacity = 1;
  ind.style.height = a.offsetHeight + "px";
  ind.style.transform = `translateY(${a.offsetTop}px)`;
}
window.addEventListener("resize", () => { moveIndicator(); layoutSegs(); });

// keyboard: Ctrl+K / "/" jumps to the type box, Esc closes things
document.addEventListener("keydown", (e) => {
  const typing = /INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName);
  if ((e.ctrlKey && e.key.toLowerCase() === "k") || (e.key === "/" && !typing)) {
    e.preventDefault(); showTab("home"); $("tryText").focus(); $("tryText").select();
  } else if (e.key === "Escape" && !$("modal").classList.contains("on")) {
    if ($("cmdEditor").innerHTML) closeEditor(); else if (typing) document.activeElement.blur();
  }
});

// ---------------------------------------------------------------- the blobs
// secret developer menu: poke the logo blob 5 times
let pokes = 0, pokeTimer;
$("logo").onclick = async () => {
  pokes++; clearTimeout(pokeTimer); pokeTimer = setTimeout(() => pokes = 0, 1500);
  const b = $("logoBlob"); b.classList.remove("poked"); void b.offsetWidth; b.classList.add("poked");
  b.style.rotate = `${(pokes % 2 ? 1 : -1) * pokes * 5}deg`; setTimeout(() => b.style.rotate = "", 180);
  if (!S) return;
  if (pokes === 5 && !S.config.dev_unlocked) {
    S = await api().save_config({ dev_unlocked: true }); render();
    toast("Developer mode unlocked", "evil"); showTab("developer");
  } else if (pokes === 3 && !S.config.dev_unlocked) toast("hey, that tickles", "info");
};

// the hero blob looks at your cursor and loves boops
const BOOPS = ["boop!", "hehe, again!", "that's my nose!", "rude. (do it again)", "*happy wobble*"];
let boopN = 0;
$("heroBlob").onclick = () => {
  const b = $("heroBlob"); b.classList.add("happy"); clearTimeout(b._h); b._h = setTimeout(() => b.classList.remove("happy"), 1100);
  toast(BOOPS[boopN++ % BOOPS.length], "info");
};
document.addEventListener("mousemove", (e) => {
  if (current !== "home") return;
  const b = $("heroBlob").getBoundingClientRect();
  if (!b.width) return;
  const dx = e.clientX - (b.left + b.width / 2), dy = e.clientY - (b.top + b.height / 2);
  const d = Math.hypot(dx, dy) || 1, k = Math.min(1, d / 260);
  $("heroFace").style.transform = `translate(${(dx / d) * 6 * k}px, ${(dy / d) * 5 * k}px)`;
});
function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Up late, huh?" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

// ---------------------------------------------------------------- loading
async function reload() { S = await api().get_all(); render(); }
window.addEventListener("pywebviewready", reload);
setInterval(() => { if (S && !S.ready) reload(); }, 3000);

function render() {
  const c = S.config;
  $$(".nm").forEach((e) => e.textContent = c.name);
  $("brand").textContent = c.name;
  $("devtab").style.display = c.dev_unlocked ? "" : "none";
  if (current === "developer" && !c.dev_unlocked) showTab("home");
  renderStatus(); renderConfig(); renderCommands(); renderMemories(); renderApps(); renderHistory();
  moveIndicator();
}

function renderStatus() {
  const w = S.wake, c = S.config;
  $("greet").textContent = greeting();
  // sidebar pill
  $("miniStatus").innerHTML = S.ready
    ? `<span class="dot ok"></span><div><b>Listening</b><span>say "${esc(c.name)}"</span></div>`
    : `<span class="dot warn"></span><div><b>Starting up</b><span>loading her brain...</span></div>`;
  // hero chips: quick jumps
  const n = (x, one, many) => `${x} ${x === 1 ? one : many}`;
  $("heroChips").innerHTML =
    `<button class="chip" onclick="showTab('commands')">${icon("zap")}${n(S.commands.length, "command", "commands")}</button>` +
    `<button class="chip" onclick="showTab('memories')">${icon("book")}${n(S.memories.glossary.length + S.memories.notes.length, "memory", "memories")}</button>` +
    `<button class="chip" onclick="showTab('apps')">${icon("grid")}${n(S.apps.length, "app", "apps")}</button>`;
  // tiles
  const tiles = [];
  const words = w ? w.listening_for.map((x) => `"${esc(x)}"`).join(", ") : "";
  tiles.push(`<div class="tile"><div class="ico-tile">${icon("ear")}</div><div class="grow"><div class="k">Ears</div>
    <div class="v">${S.ready ? `<span class="dot ok"></span>Listening` : `<span class="dot warn"></span>Starting up...`}</div>
    <div class="d">${w ? `for ${words}` : "loading the wake word..."}</div>
    ${w && w.unknown.length ? `<div class="d warn" title="Not in her vocabulary, so it's ignored">"${w.unknown.map(esc).join('", "')}" isn't a word she knows</div>` : ""}</div></div>`);
  if (S.brain_installed) {
    const on = c.brain === "claude";
    tiles.push(`<div class="tile"><div class="ico-tile">${icon("brainy")}</div><div class="grow"><div class="k">Big brain</div>
      <div class="v">${on ? `Claude ${esc(c.claude_model)}` : "Off"}</div><div class="d">${on ? "Fuzzy stuff goes to Claude." : "Offline only: instant, simple."}</div></div></div>`);
  } else {
    tiles.push(`<div class="tile warn-t"><div class="ico-tile">${icon("info")}</div><div class="grow"><div class="k">Big brain</div>
      <div class="v warn">Not found</div><div class="d">Claude Code not found: running on the small brain only.</div></div></div>`);
  }
  const expr = S.voice_engine_active === "expressive";
  tiles.push(`<div class="tile"><div class="ico-tile">${icon("volume")}</div><div class="grow"><div class="k">Voice</div>
    <div class="v">${S.ready ? (expr ? "Expressive" : "Lightweight") : "Warming up"}</div>
    <div class="d">${S.ready ? (expr ? "GPU voice with feelings." : "Calm CPU voice.") : "clearing her throat..."}${!S.expressive_installed ? " Expressive voice not installed." : ""}</div></div></div>`);
  if (c.feisty_mode) {
    tiles.push(`<div class="tile evil"><div class="ico-tile">${icon("devil")}</div><div class="grow"><div class="k">Feisty mode</div>
      <div class="v" style="color:#ff5c7a">ON · ${c.feisty_level}%</div><div class="d">She might say no.${c.feisty_swearing ? " Swearing allowed." : ""}</div></div></div>`);
  }
  $("statusCard").innerHTML = tiles.join("");
}

// ---------------------------------------------------------------- home: type to Touff
const TRY = ["open binding of isaac", "play lose yourself on spotify", "next song", "set a timer for 5 minutes",
  "when I say boot up the sack, open binding of isaac", "what time is it", "tell me a joke"];
$("sugg").insertAdjacentHTML("beforeend", TRY.map((t) => `<button class="chip" data-try="${esc(t)}">${esc(t)}</button>`).join(""));
$("sugg").onclick = (e) => { const b = e.target.closest("[data-try]"); if (!b) return; $("tryText").value = b.dataset.try; $("tryText").focus(); };
$("trySend").onclick = tryIt;
$("tryText").onkeydown = (e) => { if (e.key === "Enter") tryIt(); };
$("talkNow").onclick = () => {
  const b = $("talkNow"); b.classList.remove("go"); void b.offsetWidth; b.classList.add("go");
  api().talk_now(); toast("She's listening, go!", "info");
};
const AVATAR = `<div class="av"><div class="blob"><div class="face"><div class="eye l"></div><div class="eye r"></div></div></div></div>`;
async function tryIt() {
  const text = $("tryText").value.trim(); if (!text) return;
  const r = $("tryReply"); r.classList.remove("on"); void r.offsetWidth; r.classList.add("on");
  r.innerHTML = `${AVATAR}<div class="msg"><div class="muted" style="margin-bottom:6px">You: "${esc(text)}"</div>
    <div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div></div>`;
  $("tryText").value = "";
  let out;
  try { out = await api().try_text(text); } catch (err) { r.querySelector(".bubble").innerHTML = `<span class="bad">Oops: ${esc(err.message || err)}</span>`; return; }
  const bubble = r.querySelector(".bubble");
  if (out.say) typewrite(bubble, out.say); else bubble.innerHTML = `<i class="muted">(no words, just did it)</i>`;
  r.querySelector(".msg").insertAdjacentHTML("beforeend", `<div class="meta">${out.actions.map((a) => `<span class="chip">${icon("zap")}${esc(actionLabel(a))}</span>`).join("")}
    <span class="badge ${esc(out.source)}">${esc(out.source)}</span></div>`);
  reload();
}
function typewrite(el, text) {
  clearInterval(el._tw); el.textContent = "";
  let i = 0; const step = Math.max(1, Math.ceil(text.length / 60));
  el._tw = setInterval(() => { i += step; el.textContent = text.slice(0, i); if (i >= text.length) clearInterval(el._tw); }, 18);
}

// ---------------------------------------------------------------- settings
const FMT = {
  speech_speed: (v) => (+v).toFixed(2).replace(/0$/, "").replace(/\.0$/, "") + "×",
  volume: (v) => Math.round(v * 100) + "%",
  silence_ms: (v) => (v / 1000).toFixed(1) + " s",
  feisty_level: (v) => v + "%",
};
function paintSlider(el) {
  const wrap = el.closest(".slider"); if (!wrap) return;
  const p = (el.value - el.min) / (el.max - el.min);
  wrap.style.setProperty("--p", p * 100 + "%"); wrap.style.setProperty("--pn", p);
  const txt = (FMT[el.dataset.cfg] || String)(Number(el.value));
  wrap.querySelector("output").textContent = txt;
  if (el.dataset.out) $(el.dataset.out).textContent = txt;
}
function layoutSegs() {
  $$(".seg").forEach((seg) => {
    const on = seg.querySelector("button.on"), ind = seg.querySelector(".seg-ind");
    if (!on || !seg.offsetParent) return;
    ind.style.width = on.offsetWidth + "px";
    ind.style.transform = `translateX(${on.offsetLeft}px)`;
  });
}
function setSeg(seg, value) {
  $$("button", seg).forEach((b) => b.classList.toggle("on", b.dataset.v === String(value ?? "")));
  const key = seg.dataset.seg;
  if (key) { const on = seg.querySelector("button.on"), d = document.querySelector(`[data-seg-desc="${key}"]`); if (d) d.textContent = on?.dataset.d || ""; }
}
function renderConfig() {
  const c = S.config;
  $("voiceSel").innerHTML = S.voices.map((v) => `<option value="${esc(v.id)}">${esc(v.label)}</option>`).join("");
  $("micSel").innerHTML = `<option value="">System default</option>` + S.mics.map((m) => `<option value="${m.id}">${esc(m.name)}</option>`).join("");
  $$("[data-cfg]").forEach((el) => {
    const v = c[el.dataset.cfg];
    if (el.type === "checkbox") el.checked = !!v;
    else if (document.activeElement !== el || el.type === "range") el.value = v ?? "";
    if (el.type === "range") paintSlider(el);
  });
  $$(".seg[data-seg]").forEach((seg) => setSeg(seg, c[seg.dataset.seg]));
  layoutSegs();
  if (document.activeElement !== $("wakeWords")) $("wakeWords").value = (c.wake_words || []).join(", ");
  $("engineNow").textContent = S.ready ? `· speaking with the ${S.voice_engine_active === "expressive" ? "expressive GPU" : "lightweight"} voice` +
    (!S.expressive_installed ? " (expressive voice not installed)" : "") : "";
  const w = S.wake;
  $("wakeInfo").innerHTML = w ? `Currently listening for: ${w.listening_for.map((x) => `<span class="chip acc">${esc(x)}</span>`).join("")}` +
    (w.unknown.length ? `<div class="warn" style="margin-top:4px">"${w.unknown.map(esc).join('", "')}" isn't a word my ears know, so sound-alikes do the work.</div>` : "") : "";
}
$$("[data-cfg]").forEach((el) => {
  el.addEventListener(el.type === "range" ? "input" : "change", async () => {
    let v = el.type === "checkbox" ? el.checked : el.value;
    if ("num" in el.dataset) v = Number(v);
    if (el.dataset.cfg === "mic_device") v = v === "" ? null : Number(v);
    if (el.type === "range") { // live labels; save when the slider settles
      paintSlider(el);
      clearTimeout(el._h); el._h = setTimeout(() => save(el.dataset.cfg, v), 350); return;
    }
    save(el.dataset.cfg, v);
  });
  if (el.type === "range") {
    const wrap = el.closest(".slider");
    el.addEventListener("pointerdown", () => wrap.classList.add("drag"));
    el.addEventListener("pointerup", () => wrap.classList.remove("drag"));
    el.addEventListener("blur", () => wrap.classList.remove("drag"));
  }
});
$$(".seg[data-seg]").forEach((seg) => seg.addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b || b.classList.contains("on")) return;
  setSeg(seg, b.dataset.v); layoutSegs(); save(seg.dataset.seg, b.dataset.v);
}));
async function save(key, value) {
  S = await api().save_config({ [key]: value }); render();
  if (["voice", "voice_engine", "voice_clip", "stt_engine"].includes(key)) toast("Switching voice... she'll say something when ready", "info");
  else if (key === "mic_device") toast("Mic change applies after restarting Touff", "info");
  else if (key === "feisty_mode") toast(value ? "Uh oh. She has opinions now." : "Back to sweet mode", value ? "evil" : "ok");
  else toast("Saved", "ok");
}
$("wakeWords").onchange = () => save("wake_words", $("wakeWords").value.split(",").map((x) => x.trim().toLowerCase()).filter(Boolean));
$("suggestWake").onclick = async () => {
  const b = $("suggestWake"); b.classList.add("busy");
  const s = await api().suggest_wake(S.config.name).finally(() => b.classList.remove("busy"));
  if (!s.length) return toast("Couldn't find sound-alikes. Try spelling it like it sounds!", "warn");
  $("wakeWords").value = s.join(", "); $("wakeWords").onchange(); toast("Found: " + s.join(", "), "ok");
};
const PREVIEWS = ["[happy] Hi, I'm {n}! How do I sound?", "[angry] I am NOT playing Candy Shop!", "[crying] You're closing me already? [sniff]",
  "[whispering] Psst. I can whisper too.", "[sarcastic] Oh wow, another Google search. [sigh] Thrilling.", "[dramatic] Booting up... the sack! [laugh]"];
let prevIdx = 0;
$("preview").onclick = () => { api().preview_voice(PREVIEWS[prevIdx++ % PREVIEWS.length].replace("{n}", S.config.name)); toast("Playing a preview", "info"); };
$("checkBrain").onclick = async () => {
  const b = $("checkBrain"), m = $("brainMsg"); b.classList.add("busy"); m.className = ""; m.textContent = "asking Claude...";
  try { const r = await api().check_brain(); m.textContent = r; m.className = r.startsWith("Connected") ? "ok" : "warn"; }
  finally { b.classList.remove("busy"); }
};

// ---------------------------------------------------------------- commands
let editing = null;
$("newCmd").onclick = () => editCommand({ id: "", name: "", phrases: [], actions: [{ type: "open_app", arg: "" }], reply: "" });
function actionLabel(a) { return `${a.type.replace(/_/g, " ")}${a.arg ? ": " + a.arg : ""}`; }
function renderCommands() {
  const list = $("cmdList");
  if (!S.commands.length) {
    list.innerHTML = `<div class="card"><div class="empty"><div class="sleepy"><i>z</i></div><b>No commands yet</b>
      <span>Make one here, or just say "when I say X, do Y".</span>
      <button class="btn p" onclick="$('newCmd').click()">${icon("plus")}New command</button></div></div>`;
    return;
  }
  const arrow = `<span class="arrow">${icon("arrowRight")}</span>`;
  list.innerHTML = S.commands.map((c, i) => `
    <div class="cmd">
      <div class="ico-tile">${icon("zap")}</div>
      <div class="grow">
        <div class="name">${esc(c.name || c.phrases[0] || "Untitled")}</div>
        <div class="phr">${c.phrases.map((p) => `<span class="chip acc">"${esc(p)}"</span>`).join("")}</div>
        <div class="flow">${c.actions.map((a) => `<span class="chip">${esc(actionLabel(a))}</span>`).join(arrow) || `<span class="faint">does nothing yet</span>`}</div>
        ${c.reply ? `<div class="says">says "${esc(c.reply)}"</div>` : ""}
      </div>
      <button class="btn s" onclick="runCmd(${i}, this)" title="Run it now">${icon("play")}Run</button>
      <button class="btn s icon" onclick="editCommand(S.commands[${i}])" title="Edit">${icon("pencil")}</button>
    </div>`).join("");
}
async function runCmd(i, btn) {
  btn?.classList.add("busy");
  try { const p = await api().run_actions(S.commands[i].actions); toast(p.length ? p[0] : "Done", p.length ? "warn" : "ok"); }
  finally { btn?.classList.remove("busy"); }
}
function editCommand(cmd) {
  editing = JSON.parse(JSON.stringify(cmd));
  if (!editing.actions.length) editing.actions.push({ type: "open_app", arg: "" });
  $("cmdEditor").innerHTML = "";
  drawEditor(); showTab("commands");
  setTimeout(() => { if (!editing) return; $("cmdEditor").scrollIntoView({ behavior: "smooth", block: "start" }); if (!editing.name) $("eName")?.focus(); }, 60);
}
function drawEditor() {
  const types = Object.keys(S.actions);
  const appNames = S.apps.map((a) => `<option value="${esc(a.name)}">`).join("");
  const n = editing.actions.length;
  const rows = editing.actions.map((a, i) => {
    const spec = S.actions[a.type] || {};
    return `<div class="step">
      <div class="num"><span>${i + 1}</span></div>
      <select onchange="setStepType(${i}, this.value)">${types.map((t) => `<option value="${t}" ${t === a.type ? "selected" : ""}>${t.replace(/_/g, " ")}</option>`).join("")}</select>
      <input type="text" list="appNames" value="${esc(a.arg)}" placeholder="${esc(spec.arg || "")}" oninput="editing.actions[${i}].arg=this.value" spellcheck="false">
      <div class="tools">
        <button class="btn ghost s icon" title="Move up" ${i === 0 ? "disabled style='opacity:.3'" : ""} onclick="moveStep(${i}, -1)">${icon("chevUp")}</button>
        <button class="btn ghost s icon" title="Move down" ${i === n - 1 ? "disabled style='opacity:.3'" : ""} onclick="moveStep(${i}, 1)">${icon("chevDown")}</button>
        <button class="btn ghost s icon d" title="Remove step" onclick="removeStep(${i})">${icon("x")}</button>
      </div>
      <div class="desc">${esc(spec.description || "")}${spec.risky ? ` <span class="badge risky">risky</span>` : ""}</div>
    </div>`;
  }).join("");
  $("cmdEditor").innerHTML = `<div class="card editor">
    <div class="card-head" style="margin-bottom:2px">
      <div class="ico-tile">${icon(editing.id ? "pencil" : "sparkles")}</div>
      <div class="grow"><h3>${editing.id ? "Edit command" : "New command"}</h3><p class="muted">Say any of the phrases and she runs the steps in order.</p></div>
      <button class="btn ghost icon" title="Close (Esc)" onclick="closeEditor()">${icon("x")}</button>
    </div>
    <div class="grid2">
      <div><label class="f">Name</label><input type="text" id="eName" value="${esc(editing.name)}" placeholder="Isaac time"></div>
      <div><label class="f">She says (optional)</label><input type="text" id="eReply" value="${esc(editing.reply)}" placeholder="Booting up the sack!"></div>
    </div>
    <label class="f">Phrases that trigger it (one per line)</label>
    <textarea id="ePhrases" placeholder="boot up the sack" spellcheck="false">${esc(editing.phrases.join("\n"))}</textarea>
    <label class="f">What to do, in order</label>
    <div class="steps">${rows}</div>
    <datalist id="appNames">${appNames}</datalist>
    <button class="btn s" style="margin-top:10px" onclick="addStep()">${icon("plus")}Add step</button>
    <div class="editor-foot">
      ${editing.id ? `<button class="btn d" onclick="deleteCmd()">${icon("trash")}Delete</button>` : ""}
      <div class="grow"></div>
      <button class="btn" onclick="closeEditor()">Cancel</button>
      <button class="btn" onclick="testCmd(this)">${icon("play")}Test</button>
      <button class="btn p" onclick="saveCmd()">${icon("check")}Save</button>
    </div></div>`;
}
function keepFields() {
  if (!$("eName")) return;
  editing.name = $("eName").value; editing.reply = $("eReply").value;
  editing.phrases = $("ePhrases").value.split("\n").map((x) => x.trim()).filter(Boolean);
}
function redraw() { keepFields(); drawEditor(); }
function setStepType(i, t) { editing.actions[i].type = t; redraw(); }
function addStep() { editing.actions.push({ type: "open_app", arg: "" }); redraw(); const s = $$(".steps .step input"); s[s.length - 1]?.focus(); }
function removeStep(i) { editing.actions.splice(i, 1); redraw(); }
function moveStep(i, d) { const a = editing.actions, j = i + d; if (j < 0 || j >= a.length) return; [a[i], a[j]] = [a[j], a[i]]; redraw(); }
function closeEditor() { $("cmdEditor").innerHTML = ""; editing = null; }
async function testCmd(btn) {
  keepFields(); btn.classList.add("busy");
  try { const p = await api().run_actions(editing.actions); toast(p.length ? p[0] : "Ran it", p.length ? "warn" : "ok"); }
  finally { btn.classList.remove("busy"); }
}
async function saveCmd() {
  keepFields();
  if (!editing.phrases.length) { toast("Give it at least one phrase", "warn"); $("ePhrases").focus(); return; }
  const cmds = S.commands.filter((c) => c.id !== editing.id);
  const idx = S.commands.findIndex((c) => c.id === editing.id);
  cmds.splice(idx < 0 ? cmds.length : idx, 0, editing);
  S.commands = await api().save_commands(cmds);
  const first = editing.phrases[0];
  closeEditor(); renderCommands(); renderStatus(); toast(`Saved! Try saying "${first}"`, "ok");
}
async function deleteCmd() {
  S.commands = await api().save_commands(S.commands.filter((c) => c.id !== editing.id));
  closeEditor(); renderCommands(); renderStatus(); toast("Deleted", "ok");
}

// ---------------------------------------------------------------- memories
function renderMemories() {
  const m = S.memories;
  $("glossList").innerHTML = m.glossary.length ? m.glossary.map((g, i) =>
    `<div class="item"><div class="grow"><span class="gloss-term">${esc(g.term)}</span> <span class="arrow">${icon("arrowRight")}</span> ${esc(g.meaning)}</div>
     <button class="btn ghost s icon d reveal" title="Forget" onclick="delGloss(${i})">${icon("trash")}</button></div>`).join("")
    : `<div class="empty" style="padding:18px"><span>No words yet. Teach her your slang!</span></div>`;
  $("noteList").innerHTML = m.notes.length ? m.notes.map((n, i) =>
    `<div class="item"><span class="note-dot"></span><div class="grow">${esc(n)}</div>
     <button class="btn ghost s icon d reveal" title="Forget" onclick="delNote(${i})">${icon("trash")}</button></div>`).join("")
    : `<div class="empty" style="padding:18px"><span>Nothing yet. What should she know about you?</span></div>`;
}
async function saveMem() { S.memories = await api().save_memories(S.memories); renderMemories(); renderStatus(); }
function delGloss(i) { S.memories.glossary.splice(i, 1); saveMem(); toast("Forgotten", "ok"); }
function delNote(i) { S.memories.notes.splice(i, 1); saveMem(); toast("Forgotten", "ok"); }
$("gAdd").onclick = () => {
  const term = $("gTerm").value.trim(), meaning = $("gMeaning").value.trim();
  if (!term || !meaning) { (term ? $("gMeaning") : $("gTerm")).focus(); return; }
  S.memories.glossary.push({ term, meaning }); $("gTerm").value = $("gMeaning").value = ""; saveMem(); toast("Learned", "ok"); $("gTerm").focus();
};
$("gTerm").onkeydown = (e) => { if (e.key === "Enter") $("gMeaning").focus(); };
$("gMeaning").onkeydown = (e) => { if (e.key === "Enter") $("gAdd").click(); };
$("nAdd").onclick = () => { const t = $("nText").value.trim(); if (!t) return; S.memories.notes.push(t); $("nText").value = ""; saveMem(); toast("Noted", "ok"); };
$("nText").onkeydown = (e) => { if (e.key === "Enter") $("nAdd").click(); };

// ---------------------------------------------------------------- apps
const KIND = { steam: ["Steam", "gamepad"], start: ["App", "window"], url: ["Website", "globe"], folder: ["Folder", "folder"] };
let appKind = "";
setSeg($("kindSeg"), "");
$("kindSeg").addEventListener("click", (e) => {
  const b = e.target.closest("button"); if (!b) return;
  appKind = b.dataset.v; setSeg($("kindSeg"), appKind); layoutSegs(); renderApps();
});
function renderApps() {
  const f = $("appFilter").value.toLowerCase();
  const all = S.apps.filter((a) => (!f || a.name.toLowerCase().includes(f)) && (!appKind || a.kind === appKind));
  const apps = all.slice(0, 300);
  $("appCount").textContent = all.length > apps.length ? `Showing ${apps.length} of ${all.length}` : `${all.length} ${all.length === 1 ? "thing" : "things"}`;
  $("appList").innerHTML = apps.map((a) => {
    const [label, ic] = KIND[a.kind] || [a.kind, "window"];
    return `<div class="item"><div class="app-ico k-${esc(a.kind)}">${icon(ic)}</div><div class="grow">${esc(a.name)}</div>
      <span class="app-kind">${esc(label)}</span>
      <button class="btn s reveal" data-nick="${esc(a.name)}">${icon("tag")}Nickname</button></div>`;
  }).join("") || `<div class="empty"><b>No matches</b><span>Nothing called "${esc(f)}". Try Rescan?</span></div>`;
}
$("appList").onclick = (e) => { const b = e.target.closest("[data-nick]"); if (b) nickname(b.dataset.nick); };
$("appFilter").oninput = renderApps;
$("rescan").onclick = async () => {
  const b = $("rescan"); b.classList.add("busy"); toast("Scanning...", "info");
  try { const n = await api().rescan_apps(); await reload(); toast(`Found ${n} things`, "ok"); } finally { b.classList.remove("busy"); }
};
async function nickname(name) {
  const nick = await ask("Give it a nickname", `What do you call "${name}"?`, "e.g. the sack");
  if (!nick) return;
  S.memories.glossary.push({ term: nick, meaning: name }); saveMem(); toast(`"${nick}" → ${name}`, "ok");
}

// ---------------------------------------------------------------- history
function dayLabel(d) {
  const iso = (x) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  const now = new Date(), y = new Date(now - 864e5);
  if (d === iso(now)) return "Today";
  if (d === iso(y)) return "Yesterday";
  const dt = new Date(d + "T12:00:00");
  return isNaN(dt) ? d : dt.toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" });
}
function renderHistory() {
  const h = S.history;
  if (!h.length) {
    $("histTable").innerHTML = `<div class="empty"><div class="sleepy"><i>z</i></div><b>Nothing yet</b><span>Go talk to her!</span></div>`;
    return;
  }
  let lastDay = null, html = "";
  h.forEach((x, i) => {
    const day = String(x.time).slice(0, 10);
    if (day !== lastDay) { html += `<div class="day">${esc(dayLabel(day))}</div>`; lastDay = day; }
    html += `<div class="hrow">
      <div class="t">${esc(String(x.time).slice(11, 16))}</div>
      <div style="min-width:0">
        <div class="you selectable">${esc(x.heard)}</div>
        ${x.said ? `<div class="her selectable">${esc(x.said)}</div>` : ""}
        ${x.actions.length ? `<div class="acts">${x.actions.map((a) => `<span class="chip">${icon("zap")}${esc(actionLabel(a))}</span>`).join("")}</div>` : ""}
      </div>
      <div class="right"><span class="badge ${esc(x.source)}">${esc(x.source)}</span>
        <button class="btn s" onclick="fromHistory(${i})" title="Make this a command">${icon("plus")}Cmd</button></div>
    </div>`;
  });
  $("histTable").innerHTML = html;
}
function fromHistory(i) {
  const x = S.history[i];
  editCommand({ id: "", name: x.heard, phrases: [x.heard], actions: x.actions.length ? x.actions : [{ type: "open_app", arg: "" }], reply: "" });
}

// first paint before Python answers
showTab("home");
$("greet").textContent = greeting();
