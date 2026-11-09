# Video editing workspace

This folder is Matthew's video editing journey. Read `README.md` for the layout and `JOURNAL.md` for history before starting.

## Conventions

- One folder per video in `projects/<yyyy-mm-dd>-<short-name>/` (older ones may lack the date). Keep each project's notes (brief, decisions, review) in that folder.
- Raw footage lives in `footage/`, finished videos in `exports/`. Both are git-ignored: never commit large media. A project's own small render may stay in its `renders/`.
- After each session, add a short entry to the top of `JOURNAL.md` (made / learned / next) and update the Projects table in `README.md`.

## Tools and how to use them

- Motion graphics, titles, captions and overlays: HyperFrames. Load the `/hyperframes` skill first. Vendor GSAP into `assets/` if the CDN is unreachable.
- Cutting, joining, converting, loudness: FFmpeg. Always write to a new file; never overwrite originals in `footage/`.
- Transcripts: Whisper (or `npx hyperframes transcribe`). Cut talking-head footage by transcript.
- Downloads: yt-dlp, only for content Matthew has the rights to use.
- DaVinci Resolve handoff: export the edit as FCPXML, EDL or OpenTimelineIO next to the project.

## Working style

- Ask what the video is for (platform, length, aspect ratio) if it isn't stated.
- Only put facts on screen that Matthew gave or that the source shows.
- Before delivering, sample frames from the render and check them; say plainly what was checked and what wasn't (audio is measured, not heard).
