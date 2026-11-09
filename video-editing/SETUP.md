# Setting up Claude Code on your computer for video editing

Running Claude on your own computer means it can work directly on your footage, with no uploads and no cloud size limits, and later drive DaVinci Resolve.

## 1. Install Claude Code

Pick one:

- **Desktop app** (easiest): download the Claude desktop app from https://claude.ai/download and open the **Code** tab.
- **Terminal**:
  - Mac or Linux: `curl -fsSL https://claude.ai/install.sh | bash`
  - Windows (PowerShell): `irm https://claude.ai/install.ps1 | iex`

  Then sign in by running `claude` once.

Docs: https://code.claude.com/docs

## 2. Get this repository onto your computer

```bash
git clone https://github.com/matthewgrubisic11-crypto/ai-agent.git
cd ai-agent
```

Open Claude Code in the `ai-agent` folder (the repository root), so it loads the HyperFrames skills from `.claude/skills/`. Its instructions for editing are in `video-editing/CLAUDE.md`; Claude reads them when working in that folder.

## 3. Install the editing tools

**Mac**, in the Terminal app:

1. Install Homebrew (skip if `brew --version` already works). When it finishes, run the two "Next steps" lines it prints.

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. Install the tools. Whisper goes through `pipx`, because Homebrew's Python refuses a plain `pip3 install` with an "externally-managed-environment" error.

   ```bash
   brew install ffmpeg node yt-dlp pipx git
   pipx ensurepath
   pipx install openai-whisper
   ```

3. Close and reopen Terminal so the new commands are found.

**Windows** (in PowerShell):

```powershell
winget install Gyan.FFmpeg OpenJS.NodeJS.LTS Python.Python.3.12 yt-dlp.yt-dlp
pip install openai-whisper
```

HyperFrames needs no install: Claude runs it with `npx hyperframes`.

Check everything works:

```bash
ffmpeg -version
yt-dlp --version
whisper --help
npx hyperframes --version
```

## 4. Optional: DaVinci Resolve

- **Free Resolve:** Claude makes a timeline file (FCPXML, EDL or OpenTimelineIO). You import it with File > Import > Timeline.
- **Resolve Studio (paid):** also lets Claude control Resolve with scripts: create projects, import media, build timelines, queue renders. Turn on Preferences > System > General > External scripting using: Local.

## 5. Optional: music for HyperFrames videos

```bash
npx hyperframes auth login
```

Free sign-in; it unlocks the HeyGen music library and sound effects.

## 6. First real session

Put a clip in `video-editing/footage/`, open Claude Code in `ai-agent`, and say something like:

> Edit video-editing/footage/my-clip.mp4 into a 60 s vertical video: cut the ums and dead air, add captions and a music bed, then give me a Resolve timeline too.
