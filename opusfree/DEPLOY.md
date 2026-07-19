# Hosting opusfree on the web (so it's always at a URL)

Your tool does heavy video processing (AI transcription + ffmpeg), so
"free + always-on + on the web" always has *some* catch. This guide covers the
best realistic options, easiest first.

---

## ⭐ Option 1 — Hugging Face Spaces (recommended: free + permanent URL)

You get a permanent URL like `https://YOURNAME-opusfree.hf.space`. The Space
sleeps when idle and **wakes automatically** when someone opens it. Free CPU is
slow-ish, but it works and it's genuinely free forever.

**Steps (no command line needed):**

1. Make a free account at <https://huggingface.co/join>.
2. Go to <https://huggingface.co/new-space>.
   - **Space name:** `opusfree`
   - **License:** any (e.g. MIT)
   - **SDK:** choose **Docker** → **Blank**
   - **Visibility:** **Private** (recommended — only you can use it, so nobody
     burns your free compute). You can make it Public later.
   - Click **Create Space**.
3. Upload the tool's files into the Space (drag-and-drop in the Space's **Files**
   tab, or `git push` — HF shows you the exact git commands). Upload **everything
   in this `opusfree/` folder**: `Dockerfile`, `requirements.txt`, `webrun.py`,
   `run.py`, and the `opusfree/` package directory.
4. **Important:** the Space's own `README.md` must have Docker settings at the
   top. Copy the file `deploy/huggingface-README.md` from this repo and upload it
   as the Space's `README.md` (replacing the auto-created one).
5. That's it. HF builds the Docker image automatically (a few minutes the first
   time) and your app goes live at the Space URL. Open it and generate clips.

**Notes**
- First job downloads the Whisper model once (cached in the container).
- Free CPU: use the `tiny` or `base` model and short videos for reasonable speed.
- Uploads are held in memory during a job, so keep source files modest (say
  < a few hundred MB) on the free tier.

---

## Option 2 — Render.com (free web service, also permanent URL)

1. Push this `opusfree/` folder to a GitHub repo.
2. At <https://render.com> → **New → Web Service** → connect that repo.
3. Render auto-detects the `Dockerfile`. Set **Instance Type: Free**.
4. Deploy. You get `https://opusfree.onrender.com` (or similar).

Catch: the free service **spins down after ~15 min idle** and cold-starts on the
next visit (a slow first load), with a 750 hours/month cap.

---

## Option 3 — Fly.io (free allowance, always-on small VM)

With the Docker image this is:
```bash
# one-time
curl -L https://fly.io/install.sh | sh
fly auth signup
# from inside the opusfree/ folder
fly launch --dockerfile Dockerfile   # accept defaults, pick the free-ish size
fly deploy
```
Gives you `https://opusfree.fly.dev`. More technical, but closest to a real
always-on server for free.

---

## Option 4 — Your own computer, shared to the web (Cloudflare Tunnel)

Truly free and private, but only online while your computer is on.
```bash
# terminal 1: run the app locally
python webrun.py
# terminal 2: expose it (install cloudflared first)
cloudflared tunnel --url http://localhost:8500
```
Cloudflare prints a public `https://…trycloudflare.com` URL that forwards to your
machine. Close your laptop and it goes offline — so it's "on the web" only while
running.

---

## Which should you pick?

- **Want it always at a URL, free, minimal fuss →** Hugging Face Spaces (Option 1).
- **Comfortable with GitHub →** Render (Option 2).
- **Want a real always-on server, don't mind CLI →** Fly.io (Option 3).
- **Just want to share it occasionally from your own PC →** Cloudflare Tunnel (Option 4).

## Security reminder

A public instance lets **anyone with the link** run video jobs on your hosting.
Keep the Space/service **private**, or only share the URL with people you trust.
