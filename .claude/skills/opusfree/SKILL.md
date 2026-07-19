---
name: opusfree
description: >
  Launch the local opusfree video-clipping app (a free Opus Clip alternative)
  and open it in the browser. Use whenever the user says "start opusfree",
  "run opusfree", "open the clipper", "make clips", "open opusfree", or invokes
  /opusfree. Installs anything missing on first run, then serves the web UI at
  http://localhost:8500.
---

# opusfree launcher

Your job: get the opusfree web app running on THIS computer and open it in the
user's browser, then leave it running.

## Steps

1. Find the opusfree folder. It lives in the user's clone of the
   `matthewgrubisic11-crypto/ai-agent` repo, in the `opusfree/` subdirectory.
   - If you can't find it locally, clone it first:
     `git clone -b claude/question-eqvx2c https://github.com/matthewgrubisic11-crypto/ai-agent.git`
     then `cd ai-agent/opusfree`.

2. Launch it using the script for the user's OS, from inside `opusfree/`:
   - macOS / Linux:  `bash setup_and_run.sh`
   - Windows:        `setup_and_run.bat`
   These check for Python + ffmpeg (installing ffmpeg via brew/apt/winget if
   missing), install Python deps, then start the server.
   - Fallback if a script fails: `pip install -r requirements.txt` then
     `python webrun.py`.

3. The app serves http://localhost:8500. Open that URL in the default browser.

4. Keep the process running (don't kill it). Tell the user it's live at
   http://localhost:8500 and how to use it: drop in a video, optionally type a
   ClipAnything prompt, pick clip count + aspect ratios, click Generate, then
   preview and download the clips.

## Notes to relay if relevant
- First run downloads a speech-to-text model (a few hundred MB) once — expected.
- Everything runs locally; nothing is uploaded.
- The site is live only while this process runs. Closing it stops the app;
  invoke this skill again to relaunch.
- Speed depends on the computer. Suggest the `base` or `tiny` Whisper model for
  quick results.
