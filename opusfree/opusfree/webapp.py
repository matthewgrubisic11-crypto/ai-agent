"""Local web UI for opusfree — a browser front-end over the pipeline.

Run:  python -m opusfree.webapp   (then open http://localhost:8500)

Pure Python standard library, no web framework needed. Upload a video, pick
options, watch progress, preview and download clips + their social copy.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .captions import STYLES
from .envfile import load_env
from .multipart import parse as parse_multipart
from .pipeline import process

load_env()

JOBS: dict[str, dict] = {}
WORK_ROOT = os.path.join(tempfile.gettempdir(), "opusfree_jobs")
os.makedirs(WORK_ROOT, exist_ok=True)


def _run_job(job_id: str, video_path: str, opts: dict) -> None:
    job = JOBS[job_id]

    def progress(stage: str, pct: float, msg: str) -> None:
        job["pct"] = round(pct)
        job["message"] = msg
        job["stage"] = stage

    try:
        manifest = process(
            video_path, job["out_dir"],
            count=opts["count"], min_dur=opts["min_dur"], max_dur=opts["max_dur"],
            model_size=opts["model"], caption_style=opts["style"],
            use_llm=opts["llm"], prompt=opts["prompt"] or None,
            ratios=opts["ratios"], gen_meta=opts["meta"],
            zooms=opts.get("zooms", True), sfx=opts.get("sfx", True),
            split_screen=opts.get("split", True),
            tighten=opts.get("tighten", True), enhance_audio=opts.get("enhance", True),
            on_progress=progress,
        )
        job["clips"] = manifest
        job["status"] = "done"
    except Exception as exc:  # pragma: no cover - surfaced to the UI
        job["status"] = "error"
        job["message"] = str(exc)
    finally:
        try:
            os.remove(video_path)
        except OSError:
            pass


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # quieter console
        pass

    def _send(self, code: int, body: bytes, ctype: str = "text/html") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self._send(200, PAGE.encode("utf-8"))
        elif self.path.startswith("/status/"):
            job_id = self.path.split("/status/", 1)[1]
            job = JOBS.get(job_id)
            if not job:
                self._send(404, b'{"error":"no such job"}', "application/json")
                return
            payload = {k: job[k] for k in ("status", "pct", "message", "stage")}
            payload["clips"] = job.get("clips", [])
            payload["job"] = job_id
            self._send(200, json.dumps(payload).encode(), "application/json")
        elif self.path.startswith("/file/"):
            self._serve_file()
        else:
            self._send(404, b"not found")

    def _serve_file(self):
        # /file/<job_id>/<name>
        try:
            _, _, job_id, name = self.path.split("/", 3)
        except ValueError:
            self._send(400, b"bad path")
            return
        job = JOBS.get(job_id)
        name = os.path.basename(name)  # prevent traversal
        if not job:
            self._send(404, b"no job")
            return
        path = os.path.join(job["out_dir"], name)
        if not os.path.isfile(path):
            self._send(404, b"no file")
            return
        ctype = "video/mp4" if name.endswith(".mp4") else "text/plain"
        with open(path, "rb") as fh:
            data = fh.read()
        self._send(200, data, ctype)

    def do_POST(self):
        if self.path != "/process":
            self._send(404, b"not found")
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        fields, upload = parse_multipart(body, self.headers.get("Content-Type", ""))
        if not upload or not upload[1]:
            self._send(400, b'{"error":"no video uploaded"}', "application/json")
            return

        job_id = uuid.uuid4().hex[:12]
        out_dir = os.path.join(WORK_ROOT, job_id)
        os.makedirs(out_dir, exist_ok=True)
        src_name = os.path.basename(upload[0])
        video_path = os.path.join(out_dir, "_source_" + src_name)
        with open(video_path, "wb") as fh:
            fh.write(upload[1])

        def g(name, default):
            return fields.get(name, default)

        opts = {
            "count": int(g("count", "10")),
            "min_dur": float(g("min_dur", "15")),
            "max_dur": float(g("max_dur", "60")),
            "model": g("model", "base"),
            "style": g("style", "retention"),
            "llm": "ollama" if g("llm", "") == "on" else None,
            "meta": g("meta", "on") == "on",
            "zooms": g("zooms", "on") == "on",
            "sfx": g("sfx", "on") == "on",
            "split": g("split", "on") == "on",
            "tighten": g("tighten", "on") == "on",
            "enhance": g("enhance", "on") == "on",
            "prompt": g("prompt", "").strip(),
            "ratios": [r for r in g("ratios", "9:16").split(",") if r],
        }
        JOBS[job_id] = {"status": "running", "pct": 0, "message": "queued",
                        "stage": "queued", "out_dir": out_dir, "clips": []}
        threading.Thread(target=_run_job, args=(job_id, video_path, opts),
                         daemon=True).start()
        self._send(200, json.dumps({"job": job_id}).encode(), "application/json")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>opusfree — free local Opus Clip</title>
<style>
:root{color-scheme:dark}
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 system-ui,sans-serif;background:#0b0d12;color:#e6e8ee}
header{padding:22px 28px;border-bottom:1px solid #1c2130}
header h1{margin:0;font-size:20px}
header p{margin:4px 0 0;color:#8b93a7;font-size:13px}
main{max-width:1000px;margin:0 auto;padding:24px}
.card{background:#12151d;border:1px solid #1c2130;border-radius:14px;padding:20px;margin-bottom:18px}
label{display:block;font-size:12px;color:#9aa3b8;margin:12px 0 5px;text-transform:uppercase;letter-spacing:.04em}
input,select{width:100%;padding:9px 11px;background:#0b0d12;border:1px solid #262c3d;border-radius:8px;color:#e6e8ee;font-size:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.drop{border:2px dashed #2b3345;border-radius:12px;padding:30px;text-align:center;color:#8b93a7;cursor:pointer;transition:.15s}
.drop.hover{border-color:#5b7cfa;color:#c8d2f0;background:#141a2b}
button{margin-top:18px;width:100%;padding:12px;background:#5b7cfa;border:0;border-radius:9px;color:#fff;font-size:15px;font-weight:600;cursor:pointer}
button:disabled{opacity:.5;cursor:not-allowed}
.bar{height:8px;background:#1c2130;border-radius:99px;overflow:hidden;margin-top:8px}
.bar>i{display:block;height:100%;width:0;background:linear-gradient(90deg,#5b7cfa,#9a6bff);transition:width .3s}
.row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.chip{font-size:11px;padding:3px 8px;border-radius:99px;background:#1c2130;color:#9aa3b8}
.clip{display:flex;gap:16px;padding:14px 0;border-top:1px solid #1c2130}
.clip video{width:150px;border-radius:10px;background:#000}
.score{font-size:26px;font-weight:800;color:#8affc1}
.muted{color:#8b93a7;font-size:13px}
.tags{color:#7fa0ff;font-size:13px}
a.dl{color:#9a6bff;font-size:12px;text-decoration:none;margin-right:10px}
.hidden{display:none}
small.note{color:#6b7488}
</style></head><body>
<header><h1>opusfree</h1><p>A free Opus Clip alternative — runs on your machine.</p>
<div id="aistat" style="margin-top:8px;font-size:12px">__AISTATUS__</div></header>
<main>
 <div class="card" id="setup">
  <div class="drop" id="drop">Drop a video here, or click to choose a file
    <div id="fname" class="muted" style="margin-top:8px"></div></div>
  <input type="file" id="file" accept="video/*,audio/*" class="hidden">
  <label>ClipAnything — describe what to clip (optional)</label>
  <input id="prompt" placeholder="e.g. every moment about pricing / funny reactions / advice for founders">
  <div class="grid">
   <div><label>Clips</label><input id="count" type="number" value="10" min="1" max="30"></div>
   <div><label>Min sec</label><input id="min_dur" type="number" value="15"></div>
   <div><label>Max sec</label><input id="max_dur" type="number" value="60"></div>
   <div><label>Whisper model</label><select id="model">
     <option>tiny</option><option selected>base</option><option>small</option>
     <option>medium</option><option>large-v3</option></select></div>
   <div><label>Caption style</label><select id="style">__STYLES__</select></div>
   <div><label>Aspect ratios</label><select id="ratios">
     <option value="9:16">9:16 (TikTok/Shorts)</option>
     <option value="1:1">1:1 (Instagram)</option>
     <option value="16:9">16:9 (YouTube)</option>
     <option value="9:16,1:1,16:9">All three</option></select></div>
  </div>
  <div class="row" style="margin-top:14px">
   <label style="margin:0"><input type="checkbox" id="meta" checked style="width:auto"> AI titles + hashtags</label>
   <label style="margin:0"><input type="checkbox" id="tighten" checked style="width:auto"> Surgical cut (remove filler + dead air)</label>
   <label style="margin:0"><input type="checkbox" id="zooms" checked style="width:auto"> Multicam punch zooms</label>
   <label style="margin:0"><input type="checkbox" id="sfx" checked style="width:auto"> Anticipation sound</label>
   <label style="margin:0"><input type="checkbox" id="split" checked style="width:auto"> Auto split-screen</label>
   <label style="margin:0"><input type="checkbox" id="enhance" checked style="width:auto"> Enhance dialogue audio</label>
   <label style="margin:0"><input type="checkbox" id="llm" style="width:auto"> Use local LLM (Ollama)</label>
  </div>
  <button id="go" disabled>Generate clips</button>
  <small class="note">First run downloads the Whisper model once. Big videos take a few minutes on CPU.</small>
 </div>

 <div class="card hidden" id="progress">
  <div class="row"><b id="pmsg">Working…</b><span class="chip" id="pstage"></span></div>
  <div class="bar"><i id="pbar"></i></div>
 </div>

 <div class="card hidden" id="results"><h3 style="margin-top:0">Clips</h3><div id="clips"></div></div>
</main>
<script>
const $=s=>document.querySelector(s);
let file=null, job=null;
const drop=$('#drop'), fi=$('#file');
drop.onclick=()=>fi.click();
['dragover','dragenter'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('hover')}));
['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('hover')}));
drop.addEventListener('drop',ev=>{file=ev.dataTransfer.files[0];shown()});
fi.onchange=()=>{file=fi.files[0];shown()};
function shown(){if(file){$('#fname').textContent=file.name;$('#go').disabled=false}}
$('#go').onclick=async()=>{
  if(!file)return;
  const fd=new FormData();
  fd.append('video',file);
  ['count','min_dur','max_dur','model','style','prompt'].forEach(k=>fd.append(k,$('#'+k).value));
  fd.append('ratios',$('#ratios').value);
  fd.append('meta',$('#meta').checked?'on':'off');
  fd.append('zooms',$('#zooms').checked?'on':'off');
  fd.append('sfx',$('#sfx').checked?'on':'off');
  fd.append('split',$('#split').checked?'on':'off');
  fd.append('tighten',$('#tighten').checked?'on':'off');
  fd.append('enhance',$('#enhance').checked?'on':'off');
  fd.append('llm',$('#llm').checked?'on':'off');
  $('#go').disabled=true;$('#progress').classList.remove('hidden');
  const r=await fetch('/process',{method:'POST',body:fd});
  const j=await r.json(); job=j.job; poll();
};
async function poll(){
  const r=await fetch('/status/'+job); const s=await r.json();
  $('#pbar').style.width=s.pct+'%'; $('#pmsg').textContent=s.message; $('#pstage').textContent=s.stage;
  if(s.status==='running'){setTimeout(poll,1200);return}
  if(s.status==='error'){$('#pmsg').textContent='Error: '+s.message;return}
  render(s.clips);
}
function render(clips){
  $('#results').classList.remove('hidden');
  const box=$('#clips'); box.innerHTML='';
  if(!clips.length){box.innerHTML='<p class="muted">No clips matched. Try a broader prompt or wider min/max.</p>';return}
  clips.forEach((c,idx)=>{
    const ratios=Object.entries(c.files||{});
    const first=ratios.length?ratios[0][1]:null;
    const dls=ratios.map(([r,n])=>`<a class="dl" href="/file/${job}/${n}" download>⬇ ${r}</a>`).join('');
    const dls_extra=c.thumbnail?`<a class="dl" href="/file/${job}/${c.thumbnail}" download>⬇ thumbnail</a>`:'';
    const tags=(c.hashtags||[]).join(' ');
    const why=(c.score_breakdown||[]).map(b=>`<span class="chip">${escapeHtml(b)}</span>`).join(' ');
    const framing=Object.values(c.framing||{}).includes('split')?'<span class="chip" style="color:#8affc1">split-screen</span>':'';
    const zooms=(c.zoom_moments&&c.zoom_moments.length)?`<span class="chip">${c.zoom_moments.length} punch zoom${c.zoom_moments.length>1?'s':''}</span>`:'';
    const trimmed=c.trimmed_seconds?`<span class="chip">−${c.trimmed_seconds}s dead air</span>`:'';
    const kit=c.growth_kit||{};
    const titles=(kit.on_screen_titles||[]).map(t=>`<div class="muted">• ${escapeHtml(t)}</div>`).join('');
    box.insertAdjacentHTML('beforeend',`<div class="clip">
      ${first?`<video src="/file/${job}/${first}" controls preload="metadata"></video>`:''}
      <div style="flex:1">
        <div class="row"><span class="score">${c.viral_score}<span style="font-size:14px;color:#8b93a7">/10</span></span><span class="muted">${c.output_duration||''}s${c.trimmed_seconds?' (cut)':''}</span>${framing}${zooms}${trimmed}</div>
        <b>${escapeHtml(c.title||('Clip '+(idx+1)))}</b>
        <div class="muted">${escapeHtml(c.score_justification||'')}</div>
        ${titles?`<details style="margin-top:6px"><summary class="muted" style="cursor:pointer;font-size:12px">Growth kit — titles, caption & hashtags</summary>
          <div style="margin-top:6px">${titles}<pre style="white-space:pre-wrap;color:#c8d2f0;font-size:12px;margin:8px 0">${escapeHtml(kit.post_caption||'')}</pre></div></details>`:''}
        <details style="margin-top:6px"><summary class="muted" style="cursor:pointer;font-size:12px">Why this score?</summary>
          <div class="row" style="margin-top:6px">${why||'<span class="muted">no breakdown</span>'}</div></details>
        <div style="margin-top:6px">${dls} ${dls_extra}</div>
      </div></div>`);
  });
}
function escapeHtml(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
</script></body></html>"""


def run(host: str = "127.0.0.1", port: int = 8500) -> None:
    options = "".join(
        f'<option value="{s}"{" selected" if s=="retention" else ""}>{s}</option>'
        for s in STYLES
    )
    from . import llm_select
    prov = llm_select.available()
    if prov:
        ai = (f'<span class="chip" style="background:#0f3d24;color:#8affc1">'
              f'✓ AI brain ON ({prov}) — Opus-style clip selection</span>')
    else:
        ai = ('<span class="chip" style="background:#3d2a0f;color:#ffcf8a">'
              '● AI brain OFF — using built-in scorer. Paste a free Gemini key '
              'in opusfree/.env for far better picks (see .env.example)</span>')
    global PAGE
    PAGE = PAGE.replace("__STYLES__", options).replace("__AISTATUS__", ai)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"opusfree web UI running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    run()
