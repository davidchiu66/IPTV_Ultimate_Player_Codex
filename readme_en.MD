# IPTV Ultimate Player 📺

[中文](README.md) | [English](readme_en.MD)

🚀 **Promo page**: open [docs/index.html](docs/index.html), or publish the `docs/` directory with GitHub Pages.

📌 **Project About**: see [ABOUT.md](docs/ABOUT.md).

📺 A Windows desktop IPTV and local media player built with **PySide6 + libmpv**. The project aims to combine live channel management, local playback, browser-assisted stream resolving, diagnostics, and a modern player UI in one maintainable application.

> 🚧 This project is still evolving quickly. It is suitable for personal use, development, and feature validation. Complex live streams may depend on source-site policies, regional networks, expiring tokens, DRM, and browser compatibility.

## Features

- **Live TV Playback**
  - Supports M3U, M3U8, TXT, JSON, CFG and similar channel resource files.
  - Supports common live formats such as HLS, DASH/MPD, FLV, and TS.
  - Channel groups, channel list, channel details, and channel favorites.
  - Open with the default browser or choose a browser manually.

- **Smart Resolving and Diagnostics**
  - Browser probing for pages that require JavaScript or user interaction before exposing the real media URL.
  - Configurable probe timeout, proxy, and browser server port.
  - Failure classification for HTTP errors, probe timeout, mpv 403/404, CENC decryption failures, and more.

- **Local Media Playback**
  - Plays local video, audio, GIF, and image files supported by libmpv.
  - Local rendering modes: smooth, quality, and extreme quality.
  - Playback speed, pause/resume, seek, volume, stop, and fullscreen controls.

- **Resources and Favorites**
  - Resource library panel with directory scanning.
  - Resource favorites and channel favorites.
  - Persistent favorites with invalid resource indicators.

- **Playlists**
  - Local playback albums.
  - Create albums from folders.
  - Auto play next item.
  - Per-album intro/outro skipping settings.

- **User Interface**
  - Implemented with PySide6 QWidget, not QML.
  - Apple TV inspired glassmorphism player controls.
  - Unified visual style across toolbar, resource library, playlist, settings, and player controls.
  - Floating clock and basic Chinese/English language switching.

## Requirements

- Windows 10/11 64-bit (Windows 10 minimum; Windows 7 is not supported)
- Python 3.12+ recommended
- PySide6
- libmpv

> Windows 7 is not a supported target. The current stack depends on PySide6/Qt6, Qt WebEngine, and modern libmpv runtimes that are intended for Windows 10/11.

By default, the application loads libmpv from:

```text
plugins/Mpv/libmpv-2.dll
```

If you rebuild or reorganize the repository, make sure a compatible libmpv runtime exists under `plugins/Mpv`.

## Quick Start

1. Clone the repository:

```powershell
git clone https://github.com/<your-name>/<your-repo>.git
cd <your-repo>
```

2. Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install dependencies:

```powershell
pip install -r requirements.txt
```

4. Run:

```powershell
python main.py
```

You can also run:

```powershell
.\start.bat
```

## Project Layout

```text
backend/       Resolving, proxy, EPG, favorites, playlists, and backend logic
frontend/      Browser playback page template
i18n/          Language resources
models/        Qt models and proxy models
plugins/       Runtime plugins such as libmpv
ui/            PySide6 UI components
utils/         Settings, diagnostics, media types, and utility modules
widevine/      Optional Widevine related notes or runtime files
main.py        Application entry point
pyside_main.py Startup, logging, QtWebEngine and libmpv runtime setup
```

Runtime folders are generated or used automatically under the per-user data directory:

```text
%LocalAppData%/IPTV_Ultimate_Player_Codex/Channels/   Channel resources and local media directory
%LocalAppData%/IPTV_Ultimate_Player_Codex/EPGs/       EPG cache
%LocalAppData%/IPTV_Ultimate_Player_Codex/config/     Settings, favorites, and playlists
%LocalAppData%/IPTV_Ultimate_Player_Codex/logs/       Per-start log files
```

On first run, the app tries to migrate bundled `Channels/` and legacy `config/` data into the user data directory. Installed builds do not write runtime data into `C:\Program Files`.

## GitHub Actions Packaging

The repository includes a Windows installer workflow:

```text
.github/workflows/windows-installer.yml
```

The workflow:

1. Runs on `windows-latest`.
2. Installs Python dependencies and PyInstaller.
3. Builds a one-dir Windows application with PyInstaller.
4. Creates a `.exe` installer with Inno Setup.
5. Uploads the installer as a workflow artifact.
6. Creates a GitHub Release with the installer when a `v*` tag is pushed.

Release example:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

## Notes

- Use live streams only when you have the legal right to access and play them.
- DRM/Widevine playback depends on the local environment, license model, and source-site policy.
- Browser probing is intended to resolve media URLs from pages the user can already access. It is not guaranteed to work for every website.
- Some sources may require a regional network, proxy, Referer/User-Agent headers, or short-lived tokens.

## Development Suggestions

- Keep UI code decoupled from playback and resolving logic.
- Document major feature requirements before implementation.
- Preserve diagnostic logs and failure classification for complex stream issues.
- The repository includes a `.gitignore` that excludes `backup/`, `logs/`, `config/`, `Channels/`, `EPGs/`, `__pycache__/`, `*.pyc`, and similar runtime artifacts by default.

## License

This project is licensed under the **GNU General Public License v3.0 or later** (`GPL-3.0-or-later`). See [LICENSE](LICENSE).

GPL-3.0-or-later is chosen because the player core depends on libmpv. When distributing binary installers, also preserve and comply with the license requirements of libmpv/mpv, Qt/PySide6, and other third-party components, especially license texts, source availability, and binary redistribution notices.
