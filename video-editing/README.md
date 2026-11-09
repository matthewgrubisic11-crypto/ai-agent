# Video editing journey

Everything about learning to edit videos with Claude: setup, projects, what worked, what didn't.

## Layout

| Folder | What goes in it |
| --- | --- |
| `projects/<name>/` | One folder per video: the edit, its notes and the final export |
| `footage/` | Raw clips you shoot or download. **Not committed to git** (too big) |
| `exports/` | Finished videos to share. **Not committed to git** |
| `templates/` | Reusable things: caption styles, intros, end cards, LUTs |
| `SETUP.md` | How to run Claude Code on your own computer with the editing tools |
| `JOURNAL.md` | A running log: one entry per session or project |

## Projects

| Date | Project | What it was | Status |
| --- | --- | --- | --- |
| 2026-11-09 | [patrick-half-a-million](projects/patrick-half-a-million/) | 21 s motion-graphics test built with HyperFrames (no footage) | Done, silent |

## Toolbox

- **HyperFrames**: motion graphics and titles written as HTML, rendered to video (skills in `.claude/skills/`)
- **FFmpeg**: cutting, joining, converting, audio, exporting
- **Whisper**: transcribing speech, so edits and captions can follow what was said
- **yt-dlp**: downloading source clips you have the rights to use
- **DaVinci Resolve**: final polish; Claude can hand over a timeline (EDL / FCPXML / OpenTimelineIO)
