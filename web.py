"""Web console: browser chat + live dashboard for the agent.

Runs an aiohttp server inside the same process (and event loop) as the
Telegram bot. Serves a single-page UI showing the conversation, the agent's
permanent memory, and its scheduled tasks.

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
<title>Agent Console</title>
<style>
  :root {
    --bg: #0e1116; --panel: #161b23; --panel2: #1c232e; --border: #2a3340;
    --text: #e6edf3; --dim: #8b98a8; --accent: #d97a4a; --accent2: #e8b04b;
    --user: #24435e; --agent: #1f2a38;
  }
  * { box-sizing: border-box; margin: 0; }
  body {
    background: var(--bg); color: var(--text); height: 100vh; display: flex;
    flex-direction: column; font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  }
  header {
    display: flex; align-items: center; gap: 10px; padding: 12px 18px;
    background: var(--panel); border-bottom: 1px solid var(--border);
  }
  header .dot { width: 9px; height: 9px; border-radius: 50%; background: #4cbf6c; }
  header h1 { font-size: 15px; font-weight: 600; letter-spacing: .3px; }
  header .model { color: var(--dim); font-size: 12px; margin-left: auto; }
  main { flex: 1; display: flex; min-height: 0; }
  #chatcol { flex: 1; display: flex; flex-direction: column; min-width: 0; }
  #log { flex: 1; overflow-y: auto; padding: 18px; display: flex; flex-direction: column; gap: 10px; }
  .msg { max-width: 78%; padding: 10px 14px; border-radius: 12px; white-space: pre-wrap; word-wrap: break-word; }
  .msg.user { background: var(--user); align-self: flex-end; border-bottom-right-radius: 4px; }
  .msg.assistant { background: var(--agent); align-self: flex-start; border-bottom-left-radius: 4px; }
  .msg .badge {
    display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: .5px;
    color: var(--accent2); margin-bottom: 4px;
  }
  .msg time { display: block; font-size: 10px; color: var(--dim); margin-top: 5px; }
  #typing { color: var(--dim); font-size: 13px; padding: 0 20px 8px; display: none; }
  form {
    display: flex; gap: 10px; padding: 12px 18px; background: var(--panel);
    border-top: 1px solid var(--border);
  }
  input[type=text] {
    flex: 1; background: var(--panel2); border: 1px solid var(--border); color: var(--text);
    border-radius: 10px; padding: 11px 14px; font-size: 15px; outline: none;
  }
  input[type=text]:focus { border-color: var(--accent); }
  button {
    background: var(--accent); border: 0; color: #fff; font-weight: 600; padding: 0 20px;
    border-radius: 10px; cursor: pointer; font-size: 15px;
  }
  button:disabled { opacity: .5; cursor: default; }
  aside {
    width: 300px; background: var(--panel); border-left: 1px solid var(--border);
    overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 20px;
  }
  aside h2 {
    font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: var(--dim);
    margin-bottom: 8px;
  }
  .card { background: var(--panel2); border: 1px solid var(--border); border-radius: 10px; padding: 9px 12px; margin-bottom: 7px; font-size: 13px; }
  .card .meta { color: var(--dim); font-size: 11px; margin-top: 3px; }
  .card .cancel { float: right; background: none; border: 0; color: var(--dim); cursor: pointer; font-size: 13px; padding: 0 0 0 8px; }
  .card .cancel:hover { color: #e05d5d; }
  .empty { color: var(--dim); font-size: 13px; }
  @media (max-width: 760px) { aside { display: none; } }
</style>
</head>
<body>
<header>
  <div class="dot"></div>
  <h1>Agent Console</h1>
  <span class="model" id="model"></span>
</header>
<main>
  <div id="chatcol">
    <div id="log"></div>
    <div id="typing">Agent is working…</div>
    <form id="form">
      <input id="input" type="text" placeholder="Message your agent… (try: remember that…, search for…, every morning at 8am…)" autocomplete="off">
      <button id="send" type="submit">Send</button>
    </form>
  </div>
  <aside>
    <section>
      <h2>Memory</h2>
      <div id="facts"><div class="empty">Nothing stored yet.</div></div>
    </section>
    <section>
      <h2>Scheduled tasks</h2>
      <div id="tasks"><div class="empty">No active tasks.</div></div>
    </section>
  </aside>
</main>
<script>
const $ = id => document.getElementById(id);
let auth = localStorage.getItem("agent_auth") || "";
let lastCount = -1;

function headers(json) {
  const h = json ? {"Content-Type": "application/json"} : {};
  if (auth) h["X-Auth"] = auth;
  return h;
}

async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (res.status === 401) {
    auth = prompt("Console password:") || "";
    localStorage.setItem("agent_auth", auth);
    if (auth) return api(path, {...opts, headers: {...(opts.headers||{}), "X-Auth": auth}});
    throw new Error("unauthorized");
  }
  return res;
}

function renderMessages(msgs) {
  if (msgs.length === lastCount) return;
  lastCount = msgs.length;
  const log = $("log");
  log.innerHTML = "";
  for (const m of msgs) {
    const div = document.createElement("div");
    div.className = "msg " + (m.role === "user" ? "user" : "assistant");
    let text = m.content;
    if (text.startsWith("[SCHEDULED TASK]")) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = "SCHEDULED RUN";
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
  el.innerHTML = "";
  if (!facts.length) { el.innerHTML = '<div class="empty">Nothing stored yet.</div>'; return; }
  for (const f of facts) {
    const d = document.createElement("div");
    d.className = "card";
    d.textContent = f.fact;
    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = "#" + f.id;
    d.appendChild(meta);
    el.appendChild(d);
  }
}

function renderTasks(tasks) {
  const el = $("tasks");
  el.innerHTML = "";
  if (!tasks.length) { el.innerHTML = '<div class="empty">No active tasks.</div>'; return; }
  for (const t of tasks) {
    const d = document.createElement("div");
    d.className = "card";
    const x = document.createElement("button");
    x.className = "cancel"; x.textContent = "✕"; x.title = "Cancel task";
    x.onclick = async () => {
      await api("/api/cancel_task", {method: "POST", headers: headers(true), body: JSON.stringify({task_id: t.id})});
      refresh();
    };
    d.appendChild(x);
    d.appendChild(document.createTextNode(t.prompt));
    const meta = document.createElement("div");
    meta.className = "meta";
    const sched = t.schedule_type === "daily" ? `daily at ${t.daily_time} UTC`
      : t.schedule_type === "every" ? `every ${t.interval_minutes} min` : "once";
    meta.textContent = `#${t.id} · ${sched} · next: ${new Date(t.next_run).toLocaleString()}`;
    d.appendChild(meta);
    el.appendChild(d);
  }
}

async function refresh() {
  try {
    const res = await api("/api/state", {headers: headers(false)});
    const s = await res.json();
    $("model").textContent = s.model;
    renderMessages(s.messages);
    renderFacts(s.facts);
    renderTasks(s.tasks);
  } catch (e) { /* transient; retry on next poll */ }
}

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("input").value.trim();
  if (!text) return;
  $("input").value = "";
  $("send").disabled = true;
  $("typing").style.display = "block";
  lastCount = -1;  // force re-render
  const log = $("log");
  const div = document.createElement("div");
  div.className = "msg user";
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  try {
    await api("/api/chat", {method: "POST", headers: headers(true), body: JSON.stringify({message: text})});
  } catch (e) { /* handled by refresh */ }
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
