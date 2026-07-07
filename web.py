"""Web console: browser chat + live dashboard for the agent.

Runs an aiohttp server inside the same process (and event loop) as the
Telegram bot. Serves a single-page J.A.R.V.I.S.-style console showing the
conversation, the agent's permanent memory, and its scheduled tasks.

Optional auth: set WEB_PASSWORD to require a password (sent as the X-Auth
header by the UI). Without it the console is open to anyone with the URL.
"""

import logging
import os

from aiohttp import web

import brain
import memory

logger = logging.getLogger(__name__)

WEB_USER_ID = "web"  # single-user console; web chat has its own conversation
WEB_PASSWORD = os.getenv("WEB_PASSWORD", "")


@web.middleware
async def auth_middleware(request, handler):
    if WEB_PASSWORD and request.path.startswith("/api/"):
        if request.headers.get("X-Auth", "") != WEB_PASSWORD:
            return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


async def index(request):
    return web.Response(text=PAGE, content_type="text/html")


async def state(request):
    return web.json_response({
        "model": brain.MODEL,
        "auth": bool(WEB_PASSWORD),
        "messages": memory.load_history(WEB_USER_ID, 100),
        "facts": memory.list_facts(WEB_USER_ID),
        "tasks": memory.list_jobs(WEB_USER_ID),
    })


async def chat(request):
    data = await request.json()
    text = (data.get("message") or "").strip()
    if not text:
        return web.json_response({"error": "empty message"}, status=400)
    try:
        reply = await brain.run_agent(WEB_USER_ID, WEB_USER_ID, text)
    except Exception:
        logger.exception("Web chat agent run failed")
        return web.json_response({"error": "agent failed, check server logs"}, status=500)
    return web.json_response({"reply": reply})


async def cancel_task(request):
    data = await request.json()
    ok = memory.cancel_job(WEB_USER_ID, int(data.get("task_id", 0)))
    return web.json_response({"ok": ok})


async def start_server(port: int) -> None:
    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get("/", index)
    app.router.add_get("/api/state", state)
    app.router.add_post("/api/chat", chat)
    app.router.add_post("/api/cancel_task", cancel_task)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info("Web console listening on port %s%s", port,
                " (password protected)" if WEB_PASSWORD else " (no password set!)")


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>J.A.R.V.I.S.</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
<style>
  :root {
    --bg0: #030710; --bg1: #071021; --bg2: #0b1830;
    --gold: #ffb54d; --gold-hi: #ffd98c; --gold-dim: #b07830;
    --steel: #6fa3d8; --steel-dim: #3a5a80;
    --text: #e8dcc0; --dim: #8a91a0; --danger: #ff5d5d;
    --line: rgba(255, 181, 77, .22);
    --line-steel: rgba(111, 163, 216, .25);
  }
  * { box-sizing: border-box; margin: 0; }
  body {
    background:
      radial-gradient(ellipse 70% 55% at 50% 38%, rgba(255,150,40,.07), transparent 60%),
      radial-gradient(ellipse 90% 70% at 50% 110%, rgba(40,80,160,.15), transparent 65%),
      var(--bg0);
    color: var(--text); height: 100vh; display: flex; flex-direction: column;
    font: 14px/1.55 "Share Tech Mono", ui-monospace, Menlo, monospace;
    overflow: hidden;
  }
  /* faint HUD grid + scanlines over everything */
  body::before {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 0;
    background:
      repeating-linear-gradient(0deg, transparent 0 39px, rgba(120,160,220,.05) 39px 40px),
      repeating-linear-gradient(90deg, transparent 0 39px, rgba(120,160,220,.05) 39px 40px);
  }
  body::after {
    content: ""; position: fixed; inset: 0; pointer-events: none; z-index: 60;
    background: repeating-linear-gradient(0deg, rgba(0,0,0,.16) 0 1px, transparent 1px 3px);
    mix-blend-mode: multiply;
  }

  /* ---------- boot overlay ---------- */
  #boot {
    position: fixed; inset: 0; z-index: 100; background: var(--bg0);
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 18px; transition: opacity .6s; font-family: Orbitron, monospace;
  }
  #boot .t { color: var(--gold); letter-spacing: 8px; font-size: 22px; font-weight: 700;
    text-shadow: 0 0 24px rgba(255,181,77,.8); }
  #boot .s { color: var(--dim); letter-spacing: 3px; font-size: 10px; }
  #boot .bar { width: 260px; height: 2px; background: rgba(255,181,77,.15); overflow: hidden; }
  #boot .bar i { display: block; height: 100%; width: 0; background: var(--gold);
    box-shadow: 0 0 12px var(--gold); animation: load 1.1s ease-out forwards; }
  @keyframes load { to { width: 100%; } }
  #boot.done { opacity: 0; pointer-events: none; }

  /* ---------- header ---------- */
  header {
    position: relative; z-index: 10; display: flex; align-items: center; gap: 14px;
    padding: 10px 20px; background: linear-gradient(180deg, rgba(10,20,40,.9), rgba(7,14,28,.75));
    border-bottom: 1px solid var(--line);
    box-shadow: 0 1px 0 rgba(255,181,77,.08), 0 6px 24px rgba(0,0,0,.5);
  }
  #emblem { width: 52px; height: 52px; filter: drop-shadow(0 0 8px rgba(255,170,60,.7)); }
  .idblock h1 {
    font: 900 19px Orbitron, monospace; letter-spacing: 7px; color: var(--gold-hi);
    text-shadow: 0 0 18px rgba(255,181,77,.75);
  }
  .idblock .sub { font-size: 9px; letter-spacing: 3.5px; color: var(--dim); margin-top: 2px; }
  .readouts { margin-left: auto; display: flex; gap: 26px; text-align: right; }
  .readouts .r { display: flex; flex-direction: column; gap: 1px; }
  .readouts .k { font-size: 8px; letter-spacing: 2.5px; color: var(--dim); }
  .readouts .v { font-size: 12px; letter-spacing: 1px; color: var(--gold); text-shadow: 0 0 10px rgba(255,181,77,.5); }
  .readouts .v.ok::before { content: "● "; color: #59d98c; text-shadow: 0 0 8px #59d98c; }

  main { position: relative; z-index: 5; flex: 1; display: flex; min-height: 0; }

  /* ---------- chat column ---------- */
  #chatcol { flex: 1; display: flex; flex-direction: column; min-width: 0; position: relative; }
  #holo { position: absolute; left: 50%; top: 46%; transform: translate(-50%,-50%);
    pointer-events: none; opacity: .55; z-index: 0; }
  #log { flex: 1; overflow-y: auto; padding: 22px 26px; display: flex; flex-direction: column;
    gap: 14px; position: relative; z-index: 1; scrollbar-width: thin; scrollbar-color: var(--gold-dim) transparent; }

  .msg { max-width: 72%; padding: 10px 14px 8px; position: relative;
    background: linear-gradient(160deg, rgba(255,166,60,.10), rgba(255,166,60,.03));
    border: 1px solid var(--line);
    clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 14px, 100% 100%, 14px 100%, 0 calc(100% - 14px));
    white-space: pre-wrap; word-wrap: break-word;
    box-shadow: inset 0 0 24px rgba(255,166,60,.05), 0 0 18px rgba(255,166,60,.06);
    align-self: flex-start;
  }
  .msg.user {
    align-self: flex-end;
    background: linear-gradient(160deg, rgba(90,140,210,.13), rgba(90,140,210,.04));
    border-color: var(--line-steel);
    box-shadow: inset 0 0 24px rgba(90,140,210,.06), 0 0 18px rgba(90,140,210,.07);
    color: #d7e4f5;
  }
  .msg .who { font: 700 9px Orbitron, monospace; letter-spacing: 3px; margin-bottom: 5px;
    color: var(--gold); text-shadow: 0 0 10px rgba(255,181,77,.6); }
  .msg.user .who { color: var(--steel); text-shadow: 0 0 10px rgba(111,163,216,.6); }
  .msg .badge { display: inline-block; font-size: 9px; letter-spacing: 2px; color: var(--gold-hi);
    border: 1px solid var(--line); padding: 1px 7px; margin-bottom: 6px;
    background: rgba(255,181,77,.08); }
  .msg time { display: block; font-size: 9px; color: var(--dim); margin-top: 6px; letter-spacing: 1px; }

  #typing { display: none; padding: 0 26px 10px; color: var(--gold); font-size: 11px;
    letter-spacing: 3px; z-index: 1; text-shadow: 0 0 10px rgba(255,181,77,.6); }
  #typing i { animation: blink 1s steps(2) infinite; font-style: normal; }
  @keyframes blink { 50% { opacity: 0; } }

  form { display: flex; gap: 12px; padding: 14px 22px 16px; position: relative; z-index: 1;
    background: linear-gradient(0deg, rgba(10,18,36,.92), rgba(10,18,36,.6));
    border-top: 1px solid var(--line); }
  .inputwrap { flex: 1; display: flex; align-items: center; gap: 10px;
    background: rgba(6,12,24,.85); border: 1px solid var(--line);
    clip-path: polygon(0 0, calc(100% - 12px) 0, 100% 12px, 100% 100%, 12px 100%, 0 calc(100% - 12px));
    padding: 0 14px; transition: box-shadow .2s; }
  .inputwrap:focus-within { box-shadow: 0 0 22px rgba(255,181,77,.25), inset 0 0 18px rgba(255,181,77,.06); }
  .inputwrap .prompt { color: var(--gold); text-shadow: 0 0 8px rgba(255,181,77,.7); }
  input[type=text] { flex: 1; background: none; border: 0; outline: 0; color: var(--text);
    font: 14px "Share Tech Mono", monospace; padding: 12px 0; letter-spacing: .5px; }
  input[type=text]::placeholder { color: #5a6272; }
  button.send {
    background: linear-gradient(160deg, rgba(255,166,60,.25), rgba(255,166,60,.1));
    border: 1px solid var(--gold-dim); color: var(--gold-hi); cursor: pointer;
    font: 700 11px Orbitron, monospace; letter-spacing: 3px; padding: 0 22px;
    clip-path: polygon(0 0, calc(100% - 10px) 0, 100% 10px, 100% 100%, 10px 100%, 0 calc(100% - 10px));
    text-shadow: 0 0 10px rgba(255,181,77,.7); transition: all .15s;
  }
  button.send:hover { box-shadow: 0 0 20px rgba(255,181,77,.35); }
  button.send:disabled { opacity: .4; cursor: default; box-shadow: none; }

  /* ---------- sidebar ---------- */
  aside { width: 320px; border-left: 1px solid var(--line);
    background: linear-gradient(200deg, rgba(10,20,40,.75), rgba(6,12,26,.9));
    overflow-y: auto; padding: 18px 16px; display: flex; flex-direction: column; gap: 22px;
    scrollbar-width: thin; scrollbar-color: var(--gold-dim) transparent; }
  aside h2 { font: 700 10px Orbitron, monospace; letter-spacing: 3px; color: var(--gold);
    text-shadow: 0 0 12px rgba(255,181,77,.5); display: flex; align-items: center; gap: 8px; }
  aside h2::after { content: ""; flex: 1; height: 1px;
    background: linear-gradient(90deg, var(--line), transparent); }
  aside h2 .count { color: var(--dim); font-family: "Share Tech Mono", monospace; font-size: 10px; }
  .card { position: relative; background: rgba(255,166,60,.05); border: 1px solid rgba(255,181,77,.16);
    border-left: 2px solid var(--gold-dim); padding: 9px 12px; margin-top: 8px; font-size: 12.5px;
    box-shadow: inset 0 0 16px rgba(255,166,60,.03); }
  .card .meta { color: var(--dim); font-size: 10px; margin-top: 4px; letter-spacing: 1px; }
  .card .cancel { float: right; background: none; border: 0; color: var(--dim); cursor: pointer;
    font-size: 13px; padding: 0 0 0 8px; }
  .card .cancel:hover { color: var(--danger); text-shadow: 0 0 8px var(--danger); }
  .empty { color: #566072; font-size: 11.5px; letter-spacing: 1px; margin-top: 8px; }

  @media (max-width: 780px) { aside { display: none; } #holo { opacity: .25; } }
</style>
</head>
<body>

<div id="boot">
  <div class="t">J.A.R.V.I.S.</div>
  <div class="bar"><i></i></div>
  <div class="s">INITIALIZING PERSONAL AGENT INTERFACE</div>
</div>

<header>
  <canvas id="emblem" width="104" height="104"></canvas>
  <div class="idblock">
    <h1>J.A.R.V.I.S.</h1>
    <div class="sub">JUST A RATHER VERY INTELLIGENT SYSTEM</div>
  </div>
  <div class="readouts">
    <div class="r"><span class="k">CORE MODEL</span><span class="v" id="model">—</span></div>
    <div class="r"><span class="k">UTC</span><span class="v" id="clock">—</span></div>
    <div class="r"><span class="k">LINK</span><span class="v ok" id="link">ONLINE</span></div>
  </div>
</header>

<main>
  <div id="chatcol">
    <canvas id="holo" width="760" height="760" style="width:380px;height:380px"></canvas>
    <div id="log"></div>
    <div id="typing">PROCESSING REQUEST<i>▌</i></div>
    <form id="form">
      <div class="inputwrap">
        <span class="prompt">&gt;</span>
        <input id="input" type="text" placeholder="At your service, sir. State your request…" autocomplete="off">
      </div>
      <button id="send" class="send" type="submit">TRANSMIT</button>
    </form>
  </div>
  <aside>
    <section>
      <h2>MEMORY BANK <span class="count" id="factcount"></span></h2>
      <div id="facts"><div class="empty">— NO RECORDS —</div></div>
    </section>
    <section>
      <h2>DIRECTIVES <span class="count" id="taskcount"></span></h2>
      <div id="tasks"><div class="empty">— NO ACTIVE DIRECTIVES —</div></div>
    </section>
  </aside>
</main>

<script>
const $ = id => document.getElementById(id);
let auth = localStorage.getItem("agent_auth") || "";
let lastCount = -1;

/* ---------- holographic particle spheres ---------- */
function hologram(canvas, opts) {
  const ctx = canvas.getContext("2d");
  const N = opts.n, R = opts.r, cx = canvas.width / 2, cy = canvas.height / 2;
  const pts = [];
  for (let i = 0; i < N; i++) {
    const y = 1 - (i / (N - 1)) * 2;
    const rad = Math.sqrt(1 - y * y);
    const th = 2.399963 * i;
    pts.push([Math.cos(th) * rad, y, Math.sin(th) * rad, Math.random()]);
  }
  let a = 0;
  (function frame() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    a += opts.speed;
    // orbital rings
    ctx.strokeStyle = "rgba(255,170,70," + opts.ring + ")";
    ctx.lineWidth = 1;
    for (let k = 0; k < 3; k++) {
      ctx.beginPath();
      ctx.ellipse(cx, cy, R * 1.12, R * (0.30 + 0.16 * k), a * (k % 2 ? 1 : -1) + k * 1.1, 0, 6.283);
      ctx.stroke();
    }
    for (const p of pts) {
      const x = p[0] * Math.cos(a) + p[2] * Math.sin(a);
      const z = -p[0] * Math.sin(a) + p[2] * Math.cos(a);
      const depth = (z + 1.6) / 2.6;
      const flick = 0.75 + 0.25 * Math.sin(a * 37 + p[3] * 40);
      ctx.beginPath();
      ctx.arc(cx + x * R, cy + p[1] * R * 0.94, Math.max(.4, depth * opts.dot * flick), 0, 6.283);
      ctx.fillStyle = "rgba(255," + Math.floor(160 + 70 * depth) + ",70," + (opts.alpha * depth * flick) + ")";
      ctx.fill();
    }
    requestAnimationFrame(frame);
  })();
}
hologram($("emblem"), {n: 220, r: 40, dot: 1.5, alpha: .95, ring: .35, speed: .012});
hologram($("holo"),   {n: 1400, r: 300, dot: 2.6, alpha: .75, ring: .22, speed: .004});

/* ---------- boot ---------- */
setTimeout(() => $("boot").classList.add("done"), sessionStorage.getItem("booted") ? 150 : 1300);
sessionStorage.setItem("booted", "1");

/* ---------- clock ---------- */
setInterval(() => {
  $("clock").textContent = new Date().toISOString().slice(11, 19);
}, 1000);

/* ---------- api ---------- */
function headers(json) {
  const h = json ? {"Content-Type": "application/json"} : {};
  if (auth) h["X-Auth"] = auth;
  return h;
}
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (res.status === 401) {
    auth = prompt("Authorization code:") || "";
    localStorage.setItem("agent_auth", auth);
    if (auth) return api(path, {...opts, headers: {...(opts.headers || {}), "X-Auth": auth}});
    throw new Error("unauthorized");
  }
  return res;
}

/* ---------- renderers ---------- */
function renderMessages(msgs) {
  if (msgs.length === lastCount) return;
  lastCount = msgs.length;
  const log = $("log");
  log.innerHTML = "";
  for (const m of msgs) {
    const div = document.createElement("div");
    div.className = "msg " + (m.role === "user" ? "user" : "assistant");
    const who = document.createElement("div");
    who.className = "who";
    who.textContent = m.role === "user" ? "YOU" : "J.A.R.V.I.S.";
    div.appendChild(who);
    let text = m.content;
    if (text.startsWith("[SCHEDULED TASK]")) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "⟳ SCHEDULED DIRECTIVE";
      div.appendChild(badge);
      div.appendChild(document.createElement("br"));
      text = text.replace("[SCHEDULED TASK]", "").trim();
    }
    div.appendChild(document.createTextNode(text));
    if (m.created_at) {
      const t = document.createElement("time");
      t.textContent = new Date(m.created_at).toLocaleString();
      div.appendChild(t);
    }
    log.appendChild(div);
  }
  log.scrollTop = log.scrollHeight;
}

function renderFacts(facts) {
  const el = $("facts");
  $("factcount").textContent = "[" + facts.length + "]";
  el.innerHTML = "";
  if (!facts.length) { el.innerHTML = '<div class="empty">— NO RECORDS —</div>'; return; }
  for (const f of facts) {
    const d = document.createElement("div");
    d.className = "card";
    d.textContent = f.fact;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = "REC #" + f.id;
    d.appendChild(meta);
    el.appendChild(d);
  }
}

function renderTasks(tasks) {
  const el = $("tasks");
  $("taskcount").textContent = "[" + tasks.length + "]";
  el.innerHTML = "";
  if (!tasks.length) { el.innerHTML = '<div class="empty">— NO ACTIVE DIRECTIVES —</div>'; return; }
  for (const t of tasks) {
    const d = document.createElement("div");
    d.className = "card";
    const x = document.createElement("button");
    x.className = "cancel"; x.textContent = "✕"; x.title = "Abort directive";
    x.onclick = async () => {
      await api("/api/cancel_task", {method: "POST", headers: headers(true), body: JSON.stringify({task_id: t.id})});
      refresh();
    };
    d.appendChild(x);
    d.appendChild(document.createTextNode(t.prompt));
    const meta = document.createElement("div");
    meta.className = "meta";
    const sched = t.schedule_type === "daily" ? "DAILY " + t.daily_time + " UTC"
      : t.schedule_type === "every" ? "EVERY " + t.interval_minutes + " MIN" : "ONCE";
    meta.textContent = "DIR #" + t.id + " · " + sched + " · NEXT: " + new Date(t.next_run).toLocaleString();
    d.appendChild(meta);
    el.appendChild(d);
  }
}

async function refresh() {
  try {
    const res = await api("/api/state", {headers: headers(false)});
    const s = await res.json();
    $("model").textContent = s.model;
    $("link").textContent = s.auth ? "SECURE" : "OPEN";
    renderMessages(s.messages);
    renderFacts(s.facts);
    renderTasks(s.tasks);
  } catch (e) { /* transient; retry on next poll */ }
}

/* ---------- chat ---------- */
$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("input").value.trim();
  if (!text) return;
  $("input").value = "";
  $("send").disabled = true;
  $("typing").style.display = "block";
  lastCount = -1;  // force re-render on next refresh
  const log = $("log");
  const div = document.createElement("div");
  div.className = "msg user";
  const who = document.createElement("div");
  who.className = "who"; who.textContent = "YOU";
  div.appendChild(who);
  div.appendChild(document.createTextNode(text));
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  try {
    await api("/api/chat", {method: "POST", headers: headers(true), body: JSON.stringify({message: text})});
  } catch (e) { /* surfaced via refresh */ }
  $("send").disabled = false;
  $("typing").style.display = "none";
  refresh();
  $("input").focus();
});

refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""
