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
from .multipart import parse_multi
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
            zooms=opts.get("zooms", True), sfx=False,
            split_screen=opts.get("split", True),
            tighten=opts.get("tighten", True), enhance_audio=opts.get("enhance", True),
            clean_audio=opts.get("clean_audio", False),
            translate=opts.get("translate", False),
            cta=opts.get("cta") or None,
            music_path=opts.get("music_path"),
            hook_titles=opts.get("hook_titles", True),
            progress_bar=opts.get("progress_bar", True),
            broll=opts.get("broll", True),
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
        fields, files = parse_multi(body, self.headers.get("Content-Type", ""))
        upload = files.get("video")
        url = fields.get("url", "").strip()
        if (not upload or not upload[1]) and not url:
            self._send(400, b'{"error":"no video or link provided"}',
                       "application/json")
            return

        job_id = uuid.uuid4().hex[:12]
        out_dir = os.path.join(WORK_ROOT, job_id)
        os.makedirs(out_dir, exist_ok=True)
        if upload and upload[1]:
            src_name = os.path.basename(upload[0])
            video_path = os.path.join(out_dir, "_source_" + src_name)
            with open(video_path, "wb") as fh:
                fh.write(upload[1])
        else:
            video_path = url  # a link; pipeline downloads via yt-dlp

        music_path = None
        music = files.get("music")
        if music and music[1]:
            music_path = os.path.join(out_dir, "_music_" + os.path.basename(music[0]))
            with open(music_path, "wb") as fh:
                fh.write(music[1])

        def g(name, default):
            return fields.get(name, default)

        opts = {
            "count": int(g("count", "10")),
            "min_dur": float(g("min_dur", "15")),
            "max_dur": float(g("max_dur", "60")),
            "model": g("model", "base"),
            "style": g("style", "retention"),
            "llm": None,
            "meta": g("meta", "on") == "on",
            "zooms": g("zooms", "on") == "on",
            "split": g("split", "on") == "on",
            "tighten": g("tighten", "on") == "on",
            "enhance": g("enhance", "on") == "on",
            "hook_titles": g("hook", "on") == "on",
            "progress_bar": g("bar", "on") == "on",
            "broll": g("broll", "on") == "on",
            "translate": g("translate", "") == "on",
            "clean_audio": g("clean", "") == "on",
            "cta": g("cta", "Follow for more").strip(),
            "music_path": music_path,
            "prompt": g("prompt", "").strip(),
            "ratios": [r for r in g("ratios", "9:16").split(",") if r],
        }
        JOBS[job_id] = {"status": "running", "pct": 0, "message": "queued",
                        "stage": "queued", "out_dir": out_dir, "clips": []}
        threading.Thread(target=_run_job, args=(job_id, video_path, opts),
                         daemon=True).start()
        self._send(200, json.dumps({"job": job_id}).encode(), "application/json")


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>opusfree - turn long videos into viral shorts</title>
<style>
:root{
  --bg:#0a0b10; --panel:#13151d; --panel2:#181b25; --line:#242838;
  --txt:#eef0f6; --muted:#8b93a7; --dim:#6b7387;
  --accent:#6d5efc; --good:#3ddc84; --warn:#ffce6b;
  --grad:linear-gradient(120deg,#6d5efc,#a855f7);
  color-scheme:dark;
}
*{box-sizing:border-box}
body{margin:0;font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,system-ui,sans-serif;
  background:var(--bg);color:var(--txt);-webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(60vw 40vh at 80% -5%,rgba(109,94,252,.16),transparent 60%),
             radial-gradient(50vw 40vh at 5% 0%,rgba(168,85,247,.10),transparent 55%)}
main{max-width:940px;margin:0 auto;padding:0 20px 80px;position:relative;z-index:1}
.top{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:22px 4px 26px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px}
.logo{width:40px;height:40px;border-radius:11px;background:var(--grad);display:grid;place-items:center;
  box-shadow:0 6px 20px rgba(109,94,252,.4);flex:0 0 auto}
.brand h1{margin:0;font-size:20px;font-weight:700;letter-spacing:-.02em}
.brand p{margin:1px 0 0;color:var(--muted);font-size:12.5px}
.pill{font-size:12px;font-weight:600;padding:7px 13px;border-radius:99px;display:inline-flex;align-items:center;gap:7px;border:1px solid transparent;max-width:100%}
.pill.on{background:rgba(61,220,132,.12);color:var(--good);border-color:rgba(61,220,132,.25)}
.pill.off{background:rgba(255,206,107,.10);color:var(--warn);border-color:rgba(255,206,107,.22)}
.dot{width:7px;height:7px;border-radius:50%;background:currentColor;flex:0 0 auto;box-shadow:0 0 8px currentColor}
.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:22px;margin-bottom:16px;
  box-shadow:0 12px 40px -20px rgba(0,0,0,.7)}
.drop{border:1.5px dashed #333a52;border-radius:14px;padding:34px 20px;text-align:center;cursor:pointer;
  transition:.18s;background:linear-gradient(180deg,rgba(255,255,255,.015),transparent)}
.drop:hover,.drop.hover{border-color:var(--accent);background:rgba(109,94,252,.07)}
.drop .ico{width:44px;height:44px;margin:0 auto 10px;border-radius:12px;background:var(--panel2);display:grid;place-items:center;color:var(--accent)}
.drop b{font-size:15px}
.drop .sub{color:var(--muted);font-size:13px;margin-top:4px}
.drop .fname{color:var(--good);font-size:13px;margin-top:10px;font-weight:600;word-break:break-all}
.or{display:flex;align-items:center;gap:12px;color:var(--dim);font-size:12px;margin:16px 0;text-transform:uppercase;letter-spacing:.08em}
.or::before,.or::after{content:"";height:1px;background:var(--line);flex:1}
label.fld{display:block;font-size:12px;color:var(--muted);margin:0 0 6px;font-weight:600}
input[type=text],input[type=number],input:not([type]),select{width:100%;padding:11px 13px;background:var(--bg);
  border:1px solid #2a2f42;border-radius:10px;color:var(--txt);font-size:14px;transition:.15s;font-family:inherit}
input:focus,select:focus{outline:none;border-color:var(--accent);box-shadow:0 0 0 3px rgba(109,94,252,.18)}
input[type=file]{padding:9px;font-size:13px;color:var(--muted)}
input[type=file]::file-selector-button{background:var(--panel2);color:var(--txt);border:1px solid var(--line);
  border-radius:8px;padding:6px 12px;margin-right:10px;cursor:pointer;font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:14px}
.toggles{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:2px}
.switch{display:flex;align-items:center;gap:11px;font-size:13.5px;color:#cdd3e0;cursor:pointer;padding:9px 10px;border-radius:11px;transition:.14s;user-select:none}
.switch:hover{background:rgba(255,255,255,.035)}
.switch input{position:absolute;opacity:0;pointer-events:none}
.track{width:38px;height:22px;border-radius:99px;background:#2c3143;position:relative;transition:.2s;flex:0 0 auto}
.track::after{content:"";position:absolute;top:2px;left:2px;width:18px;height:18px;border-radius:50%;background:#9aa3b8;transition:.2s}
.switch input:checked+.track{background:var(--grad)}
.switch input:checked+.track::after{transform:translateX(16px);background:#fff}
details.adv{margin-top:8px;border-top:1px solid var(--line);padding-top:6px}
details.adv>summary{list-style:none;cursor:pointer;color:var(--muted);font-size:13px;font-weight:600;padding:10px 0;display:flex;align-items:center;gap:8px}
details.adv>summary::-webkit-details-marker{display:none}
details.adv>summary .caret{transition:.2s;display:inline-block}
details.adv[open]>summary .caret{transform:rotate(90deg)}
.go{margin-top:20px;width:100%;padding:15px;background:var(--grad);border:0;border-radius:13px;color:#fff;
  font-size:16px;font-weight:700;cursor:pointer;transition:.15s;box-shadow:0 10px 30px -8px rgba(109,94,252,.6)}
.go:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 14px 36px -8px rgba(109,94,252,.75)}
.go:disabled{opacity:.45;cursor:not-allowed;box-shadow:none}
.note{color:var(--dim);font-size:12px;text-align:center;margin-top:12px}
.bar{height:10px;background:#1b1f2c;border-radius:99px;overflow:hidden;margin-top:12px}
.bar>i{display:block;height:100%;width:0;background:var(--grad);transition:.4s;border-radius:99px;box-shadow:0 0 14px rgba(109,94,252,.6)}
.prow{display:flex;align-items:center;justify-content:space-between;gap:10px}
.spin{width:16px;height:16px;border:2.5px solid rgba(255,255,255,.15);border-top-color:var(--accent);border-radius:50%;animation:sp .7s linear infinite;flex:0 0 auto}
@keyframes sp{to{transform:rotate(360deg)}}
.rhead{display:flex;align-items:baseline;gap:10px;margin:0 0 12px}
.rhead h2{margin:0;font-size:18px}
.rhead span{color:var(--muted);font-size:13px}
.clip{display:flex;gap:16px;padding:16px;border:1px solid var(--line);border-radius:14px;background:var(--panel2);margin-bottom:12px}
.clip video{width:132px;aspect-ratio:9/16;object-fit:cover;border-radius:10px;background:#000;flex:0 0 auto}
.cbody{flex:1;min-width:0}
.scorebadge{display:inline-flex;align-items:baseline;gap:1px;font-weight:800;font-size:26px;
  background:var(--grad);-webkit-background-clip:text;background-clip:text;color:transparent;line-height:1}
.scorebadge small{font-size:13px;color:var(--dim);font-weight:600;-webkit-text-fill-color:var(--dim)}
.ctitle{font-weight:700;font-size:15px;margin:6px 0 2px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin-top:2px}
.chip{font-size:11px;padding:3px 9px;border-radius:99px;background:#20263a;color:#9aa3b8;white-space:nowrap}
.chip.g{background:rgba(61,220,132,.14);color:var(--good)}
.muted{color:var(--muted);font-size:13px}
details.more{margin-top:8px}
details.more>summary{cursor:pointer;color:var(--accent);font-size:12.5px;font-weight:600;list-style:none}
details.more>summary::-webkit-details-marker{display:none}
details.more pre{white-space:pre-wrap;color:#c8d2f0;font-size:12.5px;margin:8px 0;background:var(--bg);padding:10px;border-radius:8px;border:1px solid var(--line)}
.dls{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}
a.dl{color:var(--txt);font-size:12px;font-weight:600;text-decoration:none;background:var(--panel);border:1px solid var(--line);padding:6px 11px;border-radius:8px;transition:.14s}
a.dl:hover{border-color:var(--accent);color:#fff}
.hidden{display:none}
@media(max-width:560px){.clip{flex-direction:column}.clip video{width:100%;max-width:200px}}
</style></head><body>
<main>
 <div class="top">
  <div class="brand">
   <div class="logo"><svg width="22" height="22" viewBox="0 0 24 24" fill="none"><path d="M8 5v14l11-7L8 5z" fill="#fff"/></svg></div>
   <div><h1>opusfree</h1><p>Long videos into viral shorts, on your machine - free</p></div>
  </div>
  <div id="aistat">__AISTATUS__</div>
 </div>

 <div class="card" id="setup">
  <div class="drop" id="drop">
   <div class="ico"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V3m0 0L8 7m4-4 4 4"/><path d="M3 15v4a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-4"/></svg></div>
   <b>Drop a video here</b><div class="sub">or click to choose a file</div>
   <div id="fname" class="fname"></div>
  </div>
  <input type="file" id="file" accept="video/*,audio/*" class="hidden">
  <div class="or">or paste a link</div>
  <input id="url" placeholder="https://www.youtube.com/watch?v=...  (YouTube, Vimeo, etc.)">

  <label class="fld" style="margin-top:16px">What to clip <span class="muted" style="font-weight:400">- leave blank for best moments</span></label>
  <input id="prompt" placeholder="e.g. the best reactions | advice about pricing | funny bits">

  <div class="grid" style="margin-top:16px">
   <div><label class="fld">Clips</label><input id="count" type="number" value="10" min="1" max="30"></div>
   <div><label class="fld">Min sec</label><input id="min_dur" type="number" value="15"></div>
   <div><label class="fld">Max sec</label><input id="max_dur" type="number" value="60"></div>
   <div><label class="fld">Caption style</label><select id="style">__STYLES__</select></div>
   <div><label class="fld">Aspect ratio</label><select id="ratios">
     <option value="9:16">9:16 - TikTok / Shorts</option>
     <option value="1:1">1:1 - Instagram</option>
     <option value="16:9">16:9 - YouTube</option>
     <option value="9:16,1:1,16:9">All three</option></select></div>
   <div><label class="fld">Accuracy</label><select id="model">
     <option value="tiny">Fastest</option><option value="base" selected>Balanced</option>
     <option value="small">Accurate</option><option value="medium">More accurate</option>
     <option value="large-v3">Best (slow)</option></select></div>
  </div>

  <details class="adv" open>
   <summary><span class="caret">&#9656;</span> Enhancements</summary>
   <div class="toggles" style="margin-top:8px">__TOGGLES__</div>
   <div class="grid" style="margin-top:14px">
    <div><label class="fld">End call-to-action</label><input id="cta" value="Follow for more"></div>
    <div><label class="fld">Background music (optional)</label><input type="file" id="music" accept="audio/*"></div>
   </div>
  </details>

  <button class="go" id="go" disabled>Generate clips</button>
  <div class="note">First run downloads the speech model once. Long videos take a few minutes on CPU.</div>
 </div>

 <div class="card hidden" id="progress">
  <div class="prow"><div style="display:flex;align-items:center;gap:11px"><div class="spin"></div><b id="pmsg">Working...</b></div>
   <span class="chip" id="pstage"></span></div>
  <div class="bar"><i id="pbar"></i></div>
 </div>

 <div class="hidden" id="results">
  <div class="rhead"><h2>Your clips</h2><span id="rcount"></span></div>
  <div id="clips"></div>
 </div>
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
$('#url').oninput=shown;
function shown(){if(file){$('#fname').textContent='✓ '+file.name}$('#go').disabled=!(file||$('#url').value.trim())}
const CHECKS=['meta','tighten','zooms','split','enhance','clean','translate','hook','bar','broll'];
$('#go').onclick=async()=>{
  const url=$('#url').value.trim();
  if(!file&&!url)return;
  const fd=new FormData();
  if(file) fd.append('video',file);
  if(url) fd.append('url',url);
  ['count','min_dur','max_dur','model','style','prompt','ratios','cta'].forEach(k=>fd.append(k,$('#'+k).value));
  CHECKS.forEach(k=>fd.append(k,$('#'+k).checked?'on':'off'));
  if($('#music').files[0]) fd.append('music',$('#music').files[0]);
  $('#go').disabled=true;$('#go').textContent='Working...';
  $('#progress').classList.remove('hidden');$('#progress').scrollIntoView({block:'nearest'});
  const r=await fetch('/process',{method:'POST',body:fd});
  const j=await r.json(); job=j.job; poll();
};
async function poll(){
  const r=await fetch('/status/'+job); const s=await r.json();
  $('#pbar').style.width=s.pct+'%'; $('#pmsg').textContent=s.message; $('#pstage').textContent=s.stage||'';
  if(s.status==='running'){setTimeout(poll,1200);return}
  $('#go').disabled=false;$('#go').textContent='Generate clips';
  if(s.status==='error'){$('#pmsg').textContent='Error: '+s.message;const sp=$('.spin');if(sp)sp.style.display='none';return}
  $('#progress').classList.add('hidden');
  render(s.clips);
}
function render(clips){
  $('#results').classList.remove('hidden');
  $('#rcount').textContent=clips.length?clips.length+' clips, best first':'';
  const box=$('#clips'); box.innerHTML='';
  if(!clips.length){box.innerHTML='<div class="card"><p class="muted" style="margin:0">No clips matched. Try a broader prompt or a wider min/max length.</p></div>';return}
  clips.forEach((c,idx)=>{
    const ratios=Object.entries(c.files||{});
    const first=ratios.length?ratios[0][1]:null;
    const dls=ratios.map(([r,n])=>`<a class="dl" href="/file/${job}/${n}" download>&darr; ${r}</a>`).join('');
    const dlt=c.thumbnail?`<a class="dl" href="/file/${job}/${c.thumbnail}" download>&darr; thumbnail</a>`:'';
    const chips=[];
    if(c.output_duration) chips.push(`<span class="chip">${Math.round(c.output_duration)}s</span>`);
    if(c.trimmed_seconds) chips.push(`<span class="chip">-${c.trimmed_seconds}s dead air</span>`);
    if(Object.values(c.framing||{}).includes('split')) chips.push('<span class="chip g">split-screen</span>');
    if(c.motion&&c.motion!=='none') chips.push(`<span class="chip">${escapeHtml(c.motion)}</span>`);
    const why=(c.score_breakdown||[]).map(b=>`<span class="chip">${escapeHtml(b)}</span>`).join(' ');
    const kit=c.growth_kit||{};
    const titles=(kit.on_screen_titles||[]).map(t=>`<div class="muted">- ${escapeHtml(t)}</div>`).join('');
    box.insertAdjacentHTML('beforeend',`<div class="clip">
      ${first?`<video src="/file/${job}/${first}" controls preload="metadata"></video>`:''}
      <div class="cbody">
        <div style="display:flex;align-items:center;gap:10px">
          <span class="scorebadge">${c.viral_score??''}<small>/10</small></span>
          <div class="chips">${chips.join('')}</div>
        </div>
        <div class="ctitle">${escapeHtml(c.title||('Clip '+(idx+1)))}</div>
        <div class="muted">${escapeHtml(c.score_justification||c.text||'')}</div>
        ${titles?`<details class="more"><summary>Growth kit - titles &amp; caption</summary>
          <div style="margin-top:6px">${titles}<pre>${escapeHtml(kit.post_caption||'')}</pre></div></details>`:''}
        <details class="more"><summary>Why this score?</summary>
          <div class="chips" style="margin-top:8px">${why||'<span class="muted">no breakdown</span>'}</div></details>
        <div class="dls">${dls} ${dlt}</div>
      </div></div>`);
  });
}
function escapeHtml(s){return (s||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]))}
</script></body></html>"""


_TOGGLE_DEFS = [
    ("meta", "AI titles &amp; hashtags", True),
    ("tighten", "Surgical cut (filler + dead air)", True),
    ("zooms", "Subtle motion (slow push)", True),
    ("split", "Auto split-screen", True),
    ("enhance", "Enhance dialogue audio", True),
    ("hook", "Hook title card", True),
    ("bar", "Progress bar", True),
    ("broll", "B-roll (needs Pexels key)", True),
    ("clean", "Clean audio (denoise)", False),
    ("translate", "Translate to English", False),
]


def run(host: str = "127.0.0.1", port: int = 8500) -> None:
    options = "".join(
        f'<option value="{s}"{" selected" if s == "retention" else ""}>{s}</option>'
        for s in STYLES
    )
    toggles = "".join(
        f'<label class="switch"><input type="checkbox" id="{tid}"'
        f'{" checked" if on else ""}><span class="track"></span> {label}</label>'
        for tid, label, on in _TOGGLE_DEFS
    )
    from . import llm_select
    prov = llm_select.available()
    if prov:
        ai = (f'<span class="pill on"><span class="dot"></span>'
              f'AI brain ON &middot; {prov}</span>')
    else:
        ai = ('<span class="pill off"><span class="dot"></span>'
              'AI brain OFF &middot; add a key in .env for smarter picks</span>')
    global PAGE
    PAGE = (PAGE.replace("__STYLES__", options)
                .replace("__TOGGLES__", toggles)
                .replace("__AISTATUS__", ai))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"opusfree web UI running at http://{host}:{port}  (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    run()
