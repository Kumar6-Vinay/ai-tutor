/* API-driven client. All teaching decisions come from the server; this file only renders actions and sends input. */
(function () {
"use strict";
const $ = s => document.querySelector(s);
const stage = $("#stage");
const esc = s => String(s).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const SYM = {"+": "+", "-": "−"};

let child = null, sid = null, action = null, lastFb = null, items = [];
try { child = JSON.parse(localStorage.getItem("tutorChild") || "null"); } catch (e) {}

/* ---------- API ---------- */
async function api(method, path, body) {
  const r = await fetch(path, {method, headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
  if (r.status === 204) return null;
  const data = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map(x => x.msg).join(". ") : (d || "Something went wrong"));
  }
  return data;
}
async function send(input) {
  try {
    const res = await api("POST", `/api/sessions/${sid}/input`, input);
    lastFb = res.feedback;
    action = res.action;
    render();
  } catch (e) { showErr(e.message); }
}
function showErr(m) { const e = $("#err"); if (e) e.textContent = m; }

/* ---------- Tilli, voice, sounds and rewards ---------- */
let voiceOn = true, lastSaid = "", talkTimer = null, hlTimer = null, stars = 0, moodTimer = null, ac = null;
try { voiceOn = localStorage.getItem("tilliVoice") !== "off"; } catch (e) {}
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const tilliSVG = () => `<svg viewBox="0 0 120 160">
  <ellipse cx="60" cy="154" rx="30" ry="5" fill="#000" opacity=".12"/>
  <g class="arm l"><path d="M40 86 Q22 90 16 104" fill="none" stroke="#2b1a0b" stroke-width="7" stroke-linecap="round"/><circle cx="15" cy="106" r="8" fill="#fff" stroke="#2b1a0b" stroke-width="3"/></g>
  <g class="arm r"><path d="M80 86 Q98 90 104 104" fill="none" stroke="#2b1a0b" stroke-width="7" stroke-linecap="round"/><circle cx="105" cy="106" r="8" fill="#fff" stroke="#2b1a0b" stroke-width="3"/></g>
  <rect x="40" y="8" width="40" height="22" rx="10" fill="#ff8fab" stroke="#2b1a0b" stroke-width="3"/>
  <rect x="36" y="28" width="48" height="14" rx="3" fill="#cfd8e3" stroke="#2b1a0b" stroke-width="3"/>
  <path d="M38 42 H82 V118 H38 Z" fill="#ffd23f" stroke="#2b1a0b" stroke-width="3" stroke-linejoin="round"/>
  <rect x="68" y="45" width="11" height="70" fill="#f2b705" opacity=".7"/>
  <path d="M38 118 H82 L60 150 Z" fill="#f3c98b" stroke="#2b1a0b" stroke-width="3" stroke-linejoin="round"/>
  <path d="M53 138 L60 150 L67 138 Z" fill="#2b1a0b"/>
  <circle cx="45" cy="84" r="5.5" fill="#ff7a8a" opacity=".55"/><circle cx="75" cy="84" r="5.5" fill="#ff7a8a" opacity=".55"/>
  <g class="eye"><ellipse cx="51" cy="68" rx="8" ry="9.5" fill="#fff" stroke="#2b1a0b" stroke-width="2.5"/><circle class="pupil" cx="52" cy="69" r="4.4" fill="#2b1a0b"/><circle cx="53.6" cy="67" r="1.5" fill="#fff"/></g>
  <g class="eye"><ellipse cx="69" cy="68" rx="8" ry="9.5" fill="#fff" stroke="#2b1a0b" stroke-width="2.5"/><circle class="pupil" cx="68" cy="69" r="4.4" fill="#2b1a0b"/><circle cx="69.6" cy="67" r="1.5" fill="#fff"/></g>
  <path class="brow l" d="M43 55 Q51 51 58 55" fill="none" stroke="#2b1a0b" stroke-width="3" stroke-linecap="round"/>
  <path class="brow r" d="M62 55 Q69 51 77 55" fill="none" stroke="#2b1a0b" stroke-width="3" stroke-linecap="round"/>
  <path class="smile" d="M51 88 Q60 98 69 88" fill="none" stroke="#2b1a0b" stroke-width="3.5" stroke-linecap="round"/>
  <ellipse class="mouth" cx="60" cy="92" rx="7.5" ry="5.5" fill="#7a1c2a" stroke="#2b1a0b" stroke-width="2.5"/>
  <text class="thinkmark" x="92" y="26" font-family="Baloo 2,sans-serif" font-weight="800" font-size="30" fill="#7b5cff">?</text>
  <g class="spark" fill="#ff9f1c"><path d="M14 30 l3 7 7 3 -7 3 -3 7 -3 -7 -7 -3 7 -3z"/><path d="M104 22 l2.5 6 6 2.5 -6 2.5 -2.5 6 -2.5 -6 -6 -2.5 6 -2.5z"/></g>
</svg>`;
const TILLI = (mood = "") => `<div class="tilli ${mood}" id="tilli" aria-hidden="true">${tilliSVG()}<span class="nm">Tilli</span></div>`;
function talking(on) { const t = $("#tilli"); if (t) t.classList.toggle("talk", on); }
function mood(m, ms = 0) {
  const t = $("#tilli"); if (!t) return;
  t.classList.remove("cheer", "think", "hello"); if (m) t.classList.add(m);
  clearTimeout(moodTimer); if (ms) moodTimer = setTimeout(() => t.classList.remove(m), ms);
}

/* little synth sounds, no audio files needed */
function beep(notes, o = {}) {
  if (!voiceOn) return;
  try {
    ac = ac || new (window.AudioContext || window.webkitAudioContext)();
    notes.forEach((f, i) => {
      const t = ac.currentTime + i * (o.gap || .09), osc = ac.createOscillator(), g = ac.createGain();
      osc.type = o.type || "triangle"; osc.frequency.value = f;
      g.gain.setValueAtTime(.0001, t); g.gain.exponentialRampToValueAtTime(o.vol || .12, t + .02); g.gain.exponentialRampToValueAtTime(.0001, t + (o.len || .22));
      osc.connect(g).connect(ac.destination); osc.start(t); osc.stop(t + (o.len || .22) + .05);
    });
  } catch (e) {}
}
const sfx = {
  tap: () => beep([520], {len: .07, vol: .05, type: "sine"}),
  good: () => beep([523, 659, 784, 1047], {gap: .08}),
  hint: () => beep([392, 330], {gap: .14, type: "sine", vol: .08}),
  win: () => beep([523, 659, 784, 659, 784, 1047, 1319], {gap: .11, len: .3})
};
document.addEventListener("click", e => { if (e.target.closest("button")) sfx.tap(); });

function confetti(n = 46) {
  if (REDUCED) return;
  const fx = $("#fx"), cols = ["#ff5d6c", "#ffd23f", "#18b3a4", "#5b8def", "#7b5cff", "#ff9f1c"];
  for (let i = 0; i < n; i++) {
    const c = document.createElement("i"); c.className = "conf";
    c.style.cssText = `left:${Math.random() * 100}vw;background:${cols[i % cols.length]};animation-duration:${1.4 + Math.random() * 1.4}s;animation-delay:${Math.random() * .4}s`;
    fx.appendChild(c); setTimeout(() => c.remove(), 3500);
  }
}
function addStar() {
  stars++; $("#starN").textContent = stars;
  const s = $("#stars"); s.classList.remove("pop"); void s.offsetWidth; s.classList.add("pop");
}

/* Tilli speaks, and the words in her bubble light up as she reads them */
function words(text) { return text.split(/(\s+)/).filter(t => t && !/^\s+$/.test(t)); }
function spoken(w) { return w.replace(/−/g, "minus").replace(/=/g, "equals").replace(/\+/g, "plus"); }
function lightWord(i) { document.querySelectorAll("#say .w").forEach(e => e.classList.toggle("on", +e.dataset.i === i)); }
function say(text, force) {
  if ((!voiceOn && !force) || !text) return;
  try {
    const ws = words(text), offs = []; let spk = "";
    ws.forEach(w => { offs.push(spk.length); spk += spoken(w) + " "; });
    const bubble = $("#say"), sync = bubble && bubble.textContent.replace(/\s+/g, " ").trim() === ws.join(" ");
    const u = new SpeechSynthesisUtterance(spk);
    u.lang = "en-IN"; u.rate = .88; u.pitch = 1.3;
    const vs = speechSynthesis.getVoices();
    const v = vs.find(v => /en[-_]IN/i.test(v.lang) && /female|veena|heera|lekha/i.test(v.name)) || vs.find(v => /en[-_]IN/i.test(v.lang)) || vs.find(v => /^en/i.test(v.lang));
    if (v) u.voice = v;
    let gotBoundary = false;
    u.onstart = () => {
      talking(true);
      if (!sync) return;
      setTimeout(() => {   // some voices send no word events: step through the words ourselves
        if (gotBoundary) return;
        let i = 0; clearInterval(hlTimer);
        hlTimer = setInterval(() => { lightWord(i++); if (i > ws.length) clearInterval(hlTimer); }, 340 / u.rate);
      }, 500);
    };
    u.onboundary = e => {
      if (!sync || e.name === "sentence") return;
      gotBoundary = true; clearInterval(hlTimer);
      let i = 0; offs.forEach((o, k) => { if (o <= e.charIndex) i = k; }); lightWord(i);
    };
    u.onend = u.onerror = () => { talking(false); clearInterval(hlTimer); lightWord(-1); };
    clearInterval(hlTimer); speechSynthesis.cancel(); speechSynthesis.speak(u);
    clearTimeout(talkTimer); talking(true); talkTimer = setTimeout(() => talking(false), Math.min(12000, 600 + text.length * 80));
  } catch (e) { talking(false); }
}
function guideHTML(text, tone = "neutral", extra = "", m = "") {
  const body = words(text || "").map((w, i) => `<span class="w" data-i="${i}">${esc(w)}</span>`).join(" ");
  return `<div class="guide">${TILLI(m)}<div class="bubble ${esc(tone)}"><p class="say" id="say">${body}</p>${extra}</div></div>`;
}

/* ---------- sticks ---------- */
function sticksHTML(tens, ones, o = {}) {
  let b = "";
  for (let i = 0; i < tens; i++) {
    let s = ""; for (let k = 0; k < 10; k++) s += '<i class="s"></i>';
    const gone = i >= tens - (o.goneT || 0);
    b += `<span class="bundle${gone ? " gone" : ""}">${s}<span class="bandmark"></span></span>`;
  }
  let l = ""; for (let i = 0; i < ones; i++) l += `<i class="s${i >= ones - (o.goneO || 0) ? " gone" : ""}"></i>`;
  return `<div class="sticks"><div class="group">${b}</div><div class="loose">${l}</div></div>`;
}

/* ---------- photo helper ---------- */
function shrink(file, max = 1600) {
  return new Promise((ok, no) => {
    const img = new Image(), url = URL.createObjectURL(file);
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height)), c = document.createElement("canvas");
      c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height); URL.revokeObjectURL(url);
      c.toBlob(b => b ? ok(b) : no(new Error("Could not use that photo")), "image/jpeg", .85);
    };
    img.onerror = () => { URL.revokeObjectURL(url); no(new Error("Could not open that photo")); };
    img.src = url;
  });
}

/* ---------- screens: parent setup ---------- */
function setup() {
  $("#controls").hidden = true; $("#stars").hidden = true;
  if (!child) {
    stage.innerHTML = `${guideHTML("Hi! I'm Tilli the pencil. A grown-up needs to set me up first, then we can play with numbers!", "neutral", "", "hello")}
      <span class="grownup">👪 For the grown-up</span><p class="sub"> We store a nickname, class and learning progress only.</p>
      <div class="row">
        <label class="field">Child's nickname<input id="nick" maxlength="16" value="Riya"></label>
        <label class="field">Class<select id="grade"><option>1</option><option selected>2</option><option>3</option></select></label>
        <label class="field">Age<select id="band"><option value="5-7">5 to 7</option><option value="8-10">8 to 10</option></select></label>
      </div>
      <label class="check"><input type="checkbox" id="consent"> I am the parent or guardian and I agree to this app storing my child's nickname and maths progress. I can delete it at any time.</label>
      <div class="err" id="err"></div>
      <button class="primary" id="go">Continue</button>`;
    $("#go").onclick = async () => {
      try {
        child = await api("POST", "/api/children", {nickname: $("#nick").value, grade: +$("#grade").value,
          age_band: $("#band").value, parent_consent: $("#consent").checked});
        try { localStorage.setItem("tutorChild", JSON.stringify(child)); } catch (e) {}
        setup();
      } catch (e) { showErr(e.message); }
    };
    return;
  }
  stage.innerHTML = `${guideHTML("Hi " + child.nickname + "! Ready for some maths fun? Ask a grown-up to show me today's homework.", "neutral", "", "hello")}
    <span class="grownup">👪 For the grown-up</span><h2>Today's homework</h2>
    <div class="row" id="photoRow">
      <label class="primary camera" for="cam">📷 Take a photo of the homework</label>
      <input type="file" id="cam" accept="image/*" capture="environment" hidden>
    </div>
    <p class="sub" id="photoNote">The photo is sent once to Claude, an AI reader, to read the numbers. It is not saved. Please check what it read.</p>
    <p class="sub">Or type the problems from ${esc(child.nickname)}'s sheet, for example: 52 − 27, 63 − 38, 71 − 46</p>
    <textarea id="ws" aria-label="Worksheet problems">52 - 27\n63 - 38\n71 - 46\n84 - 59\n92 - 35</textarea>
    <div class="row" style="margin-top:12px"><button class="soft" id="read">Check problems</button>
      <button class="ghost" id="prog">Progress</button><button class="ghost" id="del">Delete ${esc(child.nickname)}'s data</button></div>
    <div id="confirm"></div><div class="err" id="err"></div>`;
  let unsure = new Set(), notRead = 0;
  const key = i => `${i.a}${i.op}${i.b}`;
  async function check() {
    try {
      const r = await api("POST", "/api/worksheets/parse", {text: $("#ws").value});
      items = r.items.filter(i => i.valid);
      const bad = r.items.filter(i => !i.valid);
      $("#confirm").innerHTML = r.items.length ? `<p class="sub">Is this right? Check each one against the sheet.</p><div class="ws">${r.items.map(i =>
        `<div class="${i.valid ? (unsure.has(key(i)) ? "unsure" : "") : "bad"}">${i.a} ${SYM[i.op]} ${i.b}${i.valid ? (unsure.has(key(i)) ? "<small>Not sure I read this right</small>" : "") : `<small>${esc(i.reason)}</small>`}</div>`).join("")}</div>
        ${bad.length ? `<p class="sub">Crossed-out problems are outside what the tutor teaches yet.</p>` : ""}
        ${notRead ? `<p class="sub">${notRead} other exercise${notRead > 1 ? "s" : ""} on the sheet (not adding or taking away) can't be taught here yet, so those stay for you.</p>` : ""}
        <p class="sub">Tilli will go through every problem with ${esc(child.nickname)}, then check it has really been learned.</p>
        <button class="primary" id="start" ${items.length ? "" : "disabled"}>🚀 Let's go, ${esc(child.nickname)}!</button>`
        : `<p class="err">No problems found. Write them like 52 - 27.</p>`;
      const st = $("#start"); if (st) st.onclick = start;
    } catch (e) { showErr(e.message); }
  }
  $("#read").onclick = () => { unsure = new Set([...unsure].filter(k => $("#ws").value.replace(/[−–]/g, "-").replace(/\s+/g, "").includes(k.replace(/\s+/g, "")))); check(); };

  /* phone camera: shrink the photo in the browser, then send it for reading */
  let photoOn = true;
  api("GET", "/api/health").then(h => { photoOn = !!h.photo; }).catch(() => {});
  $("#cam").onclick = ev => {
    if (photoOn) return;
    ev.preventDefault();
    $("#confirm").innerHTML = `<p class="err">Photo reading is not switched on for this copy of the app yet. Type the problems below instead. (To turn it on, start the server with ANTHROPIC_API_KEY set.)</p>`;
  };
  $("#photoRow label").onclick = ev => { if (!photoOn) { ev.preventDefault(); $("#cam").click(); } };
  $("#cam").onchange = async ev => {
    const f = ev.target.files[0]; if (!f) return;
    showErr(""); $("#confirm").innerHTML = `<p class="sub">📖 Tilli is reading the sheet…</p>`;
    try {
      const blob = await shrink(f);
      const res = await fetch("/api/worksheets/photo", {method: "POST", headers: {"Content-Type": "image/jpeg"}, body: blob});
      const r = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(r.detail || "Could not read the photo");
      notRead = r.not_read || 0;
      unsure = new Set(r.needs_confirmation.map(i => key(r.items[i])));
      $("#ws").value = r.items.map(i => `${i.a} ${i.op} ${i.b}`).join("\n");
      if (!r.items.length) { $("#confirm").innerHTML = `<p class="err">I couldn't find any sums in that photo. Try again closer and in good light, or type them.</p>`; return; }
      check();
    } catch (e) { $("#confirm").innerHTML = ""; showErr(e.message); }
    ev.target.value = "";
  };
  $("#prog").onclick = progress;
  $("#del").onclick = () => {
    $("#confirm").innerHTML = `<p>This deletes ${esc(child.nickname)}'s profile and all progress. It cannot be undone.</p>
      <div class="row"><button class="primary" id="yes">Delete everything</button><button class="soft" id="no">Keep</button></div>`;
    $("#no").onclick = setup;
    $("#yes").onclick = async () => {
      try { await api("DELETE", `/api/children/${child.id}`); } catch (e) {}
      child = null; try { localStorage.removeItem("tutorChild"); } catch (e) {}
      setup();
    };
  };
}

async function start() {
  try {
    const r = await api("POST", "/api/sessions", {child_id: child.id, items: items.map(({a, b, op}) => ({a, b, op}))});
    sid = r.session_id; action = r.action; lastFb = null; lastSaid = ""; stars = 0; $("#starN").textContent = 0; render();
  } catch (e) {
    if (/not found/i.test(e.message)) { child = null; try { localStorage.removeItem("tutorChild"); } catch (x) {} setup(); }
    else showErr(e.message);
  }
}

async function progress() {
  try {
    const p = await api("GET", `/api/children/${child.id}/progress`);
    stage.innerHTML = `<div class="report"><h2>${esc(p.nickname)}'s progress</h2>
      <h3>Skills</h3>${p.skills.length ? `<dl class="kv">${p.skills.map(s => `<dt>${esc(s.name)}</dt><dd>${esc(s.plain)}${s.next_review ? ` · review ${esc(s.next_review)}` : ""}</dd>`).join("")}</dl>` : "<p>Nothing yet.</p>"}
      <h3>Things we noticed</h3>${p.noticed.length ? `<ul>${p.noticed.map(n => `<li>${esc(n.text)} (${n.confirmed ? "seen on 2+ problems" : "seen once"})
        <button class="ghost" data-s="${esc(n.skill)}" data-b="${esc(n.bug)}">This is wrong, remove it</button></li>`).join("")}</ul>` : "<p>Nothing to flag.</p>"}
      <p class="note">Observations expire after 30 days unless seen again.</p>
      <button class="soft" id="back">Back</button></div>`;
    stage.querySelectorAll("[data-s]").forEach(b => b.onclick = async () => {
      await api("DELETE", `/api/children/${child.id}/observations/${b.dataset.s}/${b.dataset.b}`); progress();
    });
    $("#back").onclick = setup;
  } catch (e) { showErr(e.message); }
}

/* ---------- screens: child session ---------- */
function fbHTML() {
  if (!lastFb || !lastFb.text) return `<div class="fb" id="fb"></div>`;
  let extra = "";
  if (lastFb.offer_break) extra = `<div class="choice"><button class="soft" id="chHelp">One step with me</button><button class="soft" id="chBreak">Take a break</button></div>`;
  return `<div class="fb ${esc(lastFb.tone || "neutral")}" id="fb">${esc(lastFb.text)}${extra}</div>`;
}

function columnHTML(p) {
  const d = p.digits, sub = p.op === "-";
  const topT = sub && p.regrouped ? `<span class="struck">${d.at}</span><span class="over">${d.at - 1}</span>` : d.at;
  const topO = sub && p.regrouped ? `<span class="pre">1</span>${d.ao}` : d.ao;
  const carry = !sub && p.regrouped ? `<span class="over">1</span>` : "";
  const box = (val, active) => `<div class="c box${active ? " active" : ""}${val !== null ? " filled" : ""}">${val !== null ? val : ""}</div>`;
  return `<div class="col" role="img" aria-label="${p.a} ${sub ? "minus" : "plus"} ${p.b}">
    <div></div><div class="hd">tens</div><div class="hd">ones</div>
    <div></div><div class="c">${topT}${carry}</div><div class="c">${topO}</div>
    <div class="c">${SYM[p.op]}</div><div class="c">${d.bt}</div><div class="c">${d.bo}</div>
    <div class="rule"></div>
    <div></div>${box(p.tens, p.step === "tens")}${box(p.ones, p.step === "ones")}</div>`;
}
function padHTML(label, showRegroup) {
  let b = ""; for (let n = 0; n <= 9; n++) b += `<button data-n="${n}">${n}</button>`;
  return `<div class="pad">${b}${showRegroup ? `<button class="act" id="regroup">${esc(label)}</button>` : ""}</div>`;
}
function aidHTML(p) {
  if (!lastFb || lastFb.aid !== "sticks") return "";
  const d = p.digits;
  return `<p class="sub">Top number: ${p.a}</p>` + sticksHTML(d.at, d.ao);
}

function numberHTML() {
  return `<div class="row"><div class="numin" id="num" aria-live="polite"></div></div>
    <div class="pad" style="margin-top:10px">${[1,2,3,4,5,6,7,8,9,0].map(n => `<button data-k="${n}">${n}</button>`).join("")}
    <button class="act" data-k="del">⌫ Delete</button><button class="wide primary" id="ok">Check ✔</button></div>`;
}
function wireNumber(onOk) {
  let v = "";
  const show = () => { $("#num").textContent = v; };
  stage.querySelectorAll("[data-k]").forEach(b => b.onclick = () => {
    if (b.dataset.k === "del") v = v.slice(0, -1); else if (v.length < 2) v += b.dataset.k;
    show();
  });
  $("#ok").onclick = () => { if (v !== "") onOk(+v); };
}

function modelScreen(a) {
  let i = 0;
  const sub = a.op === "-";
  const at = Math.floor(a.a / 10), ao = a.a % 10, bt = Math.floor(a.b / 10), bo = a.b % 10;
  function sticksFor(step) {
    const done = a.steps.slice(0, step + 1).map(s => s.do);
    if (sub) {
      const opened = done.includes("open");
      const t = opened ? at - 1 : at, o = opened ? ao + 10 : ao;
      return sticksHTML(t, o, {goneO: done.includes("remove_ones") ? bo : 0, goneT: done.includes("remove_tens") ? bt : 0});
    }
    const joined = done.includes("join_ones"), bundled = done.includes("bundle");
    if (!joined) return sticksHTML(at, ao) + sticksHTML(bt, bo);
    const o = ao + bo;
    return bundled ? sticksHTML(at + bt + 1, o - 10) : sticksHTML(at + bt, o);
  }
  function draw() {
    const s = a.steps[i], last = i === a.steps.length - 1;
    stage.innerHTML = `<h2>${esc(a.title)}</h2>${guideHTML(s.say)}${sticksFor(i)}
      <div class="row">${i > 0 ? `<button class="soft" id="prev">⬅ Back</button>` : ""}
      <button class="primary" id="nx">${last ? "I'm ready to try! 🚀" : "Next ➜"}</button></div>`;
    say(s.say);
    if ($("#prev")) $("#prev").onclick = () => { i--; draw(); };
    $("#nx").onclick = () => { if (last) send({kind: "continue"}); else { i++; draw(); } };
  }
  draw();
}

function render() {
  if (!sid || !action) { setup(); return; }
  const a = action;
  const tutoring = ["column", "word_problem", "diagnostic_build", "diagnostic_fact"].includes(a.type);
  $("#controls").hidden = !tutoring && a.type !== "model";
  $("#stars").hidden = false;
  $("#btnHelp").hidden = a.type !== "column";
  if (a.type === "model") { modelScreen(a); return; }

  const fb = lastFb && lastFb.text ? lastFb : null;
  const line = fb ? fb.text : (a.say || "");
  const tone = fb ? (fb.tone || "neutral") : "neutral";
  const m = a.type === "summary" ? "cheer" : tone === "good" ? "cheer" : tone === "hint" ? "think" : "";
  const choices = fb && fb.offer_break ? `<div class="choice"><button class="soft b-help" id="chHelp">💡 One step with me</button><button class="soft b-break" id="chBreak">😴 Take a break</button></div>` : "";
  let html = `<h2>${esc(a.title || "")}</h2>${guideHTML(line, tone, choices, m)}`;
  if (fb && a.say && a.say !== fb.text) html += `<p class="task">${esc(a.say)}</p>`;
  if (a.type === "column") {
    html += `<div class="colwrap">${columnHTML(a.problem)}${padHTML(a.regroup_label, a.problem.step === "ones" && !a.problem.regrouped)}</div>${aidHTML(a.problem)}`;
  } else if (a.type === "diagnostic_build") {
    html += `<div id="build"></div>`;
  } else if (a.type === "teach_place_value") {
    html += sticksHTML(Math.floor(a.number / 10), a.number % 10) + `<button class="primary" id="cont">Next</button>`;
  } else if (a.type === "diagnostic_fact" || a.type === "word_problem") {
    html += numberHTML();
  } else if (a.type === "handback") {
    html += `<div class="items">${a.items.map(esc).join("")}</div><button class="primary" id="cont">✅ Done</button>`;
  } else if (a.type === "pause") {
    html += `<button class="primary" id="cont">I'm ready</button>`;
  } else if (a.type === "summary") {
    const n = Math.max(1, Math.min(stars, 10));
    html += `<div class="trophy">🏆</div><div class="bigstars">${"⭐".repeat(n)}</div>
      <div class="chips">${a.chips.map(c => `<span>${esc(c)}</span>`).join("")}</div>
      <p>You solved ${a.solved} problems. ${a.alone} on your own.</p><button class="primary" id="rep">👪 Grown-up report</button>`;
  }
  stage.innerHTML = html;

  // Tilli says the newest line: feedback if present, otherwise the instruction
  const key = a.no + "|" + line;
  if (key !== lastSaid) {
    lastSaid = key;
    if (a.type === "summary") { sfx.win(); confetti(90); }
    else if (tone === "good") { sfx.good(); confetti(); addStar(); mood("cheer", 2600); }
    else if (tone === "hint") { sfx.hint(); mood("think", 3500); }
    say(line);
  }

  if (a.type === "column") {
    stage.querySelectorAll("[data-n]").forEach(b => b.onclick = () => send({kind: "digit", value: +b.dataset.n}));
    if ($("#regroup")) $("#regroup").onclick = () => send({kind: "regroup"});
  }
  if (a.type === "diagnostic_build") builder(a.target);
  if (a.type === "diagnostic_fact" || a.type === "word_problem") wireNumber(v => send({kind: "number", value: v}));
  if ($("#cont")) $("#cont").onclick = () => send({kind: "continue"});
  if ($("#rep")) $("#rep").onclick = report;
  if ($("#chBreak")) $("#chBreak").onclick = () => send({kind: "break"});
  if ($("#chHelp")) $("#chHelp").onclick = () => send({kind: "help"});
}

function builder(target) {
  let t = 0, o = 0;
  const el = $("#build");
  function draw() {
    el.innerHTML = sticksHTML(t, o) + `<div class="counter">
      <div class="count"><button data-d="t-" aria-label="fewer tens">−</button><span>${t} tens</span><button data-d="t+" aria-label="more tens">+</button></div>
      <div class="count"><button data-d="o-" aria-label="fewer ones">−</button><span>${o} ones</span><button data-d="o+" aria-label="more ones">+</button></div></div>
      <button class="primary" id="done">✅ Done</button>`;
    el.querySelectorAll("[data-d]").forEach(b => b.onclick = () => {
      const d = b.dataset.d;
      if (d === "t+" && t < 9) t++; if (d === "t-" && t > 0) t--;
      if (d === "o+" && o < 19) o++; if (d === "o-" && o > 0) o--;
      draw();
    });
    $("#done").onclick = () => send({kind: "build", tens: t, ones: o});
  }
  draw();
}

function hwHTML(r) {
  const h = r.homework, L = a => a.map(esc).join(", ");
  const rows = [
    [`Solved on their own`, h.alone.length ? L(h.alone) : "none yet"],
    [`Done with Tilli after her demo`, h.guided.length ? `${L(h.guided)}. Did it themselves once Tilli showed how.` : null],
    [`Solved with help`, h.with_help.length ? `${L(h.with_help)}. Worth another go on paper.` : null],
    [`Watched, then checked`, h.watched.length ? `${L(h.watched)} (Tilli showed it first)` : null],
    [`Saved for next time`, h.saved_for_next_time.length ? `${L(h.saved_for_next_time)}. Time was up, so ask Tilli again.` : null]
  ].filter(x => x[1]);
  const checks = r.checks.map(c => `<li>${esc(c.skill)}: ${c.passed ? "did a brand-new problem alone ✔" : "needs another practice day"}</li>`).join("");
  return `<dl class="kv">${rows.map(x => `<dt>${x[0]}</dt><dd>${x[1]}</dd>`).join("")}</dl>${checks ? `<p class="sub" style="margin-top:8px">Did they really learn it? A brand-new problem for each skill:</p><ul>${checks}</ul>` : ""}`;
}

async function report() {
  try {
    const r = await api("GET", `/api/sessions/${sid}/report`);
    $("#controls").hidden = true;
    stage.innerHTML = `<div class="report"><h2>${esc(r.name)}'s session</h2><p class="sub">${esc(r.date)} · ${r.minutes} min · ${esc(r.skill)}</p>
      <dl class="kv"><dt>Where they are</dt><dd>${esc(r.where)}</dd><dt>Solved</dt><dd>${r.solved}, ${r.alone} with no help</dd>
      <dt>Most help used</dt><dd>level ${r.max_help} of 6</dd><dt>Word problem</dt><dd>${esc(r.word_problem || "not reached")}</dd>
      <dt>Next review</dt><dd>${esc(r.next_review)}</dd></dl>
      <h3>The homework, problem by problem</h3>${hwHTML(r)}
      <h3>Things we noticed</h3>${r.noticed.length ? `<ul>${r.noticed.map(n => `<li>${esc(n.text)} (${esc(n.status)})</li>`).join("")}</ul>` : "<p>Nothing to flag today.</p>"}
      <h3>Try at home</h3><p>${esc(r.try_at_home)}</p>
      <p class="note">${esc(r.stored)}</p>
      <div class="row"><button class="primary" id="again">New homework</button><button class="soft" id="prog">Progress</button></div></div>`;
    $("#again").onclick = () => { sid = null; action = null; setup(); };
    $("#prog").onclick = () => { sid = null; action = null; progress(); };
  } catch (e) { showErr(e.message); }
}

/* ---------- global controls ---------- */
$("#btnHelp").onclick = () => send({kind: "help"});
$("#btnStuck").onclick = () => send({kind: "stuck"});
$("#btnBreak").onclick = () => send({kind: "break"});
$("#btnRead").onclick = () => {
  const t = [...stage.querySelectorAll(".say,.task")].map(e => e.textContent).filter(Boolean).join(". ");
  say(t, true);
};
const tv = $("#tgVoice");
const tvLabel = () => { tv.setAttribute("aria-pressed", voiceOn); tv.textContent = voiceOn ? "🔊 Tilli talks" : "🔇 Tilli is quiet"; };
tvLabel();
tv.onclick = () => {
  voiceOn = !voiceOn; tvLabel();
  try { localStorage.setItem("tilliVoice", voiceOn ? "on" : "off"); } catch (e) {}
  if (!voiceOn) { try { speechSynthesis.cancel(); } catch (e) {} talking(false); }
};
$("#tgRestart").onclick = () => { sid = null; action = null; lastFb = null; try { speechSynthesis.cancel(); } catch (e) {} setup(); };

render();
})();
