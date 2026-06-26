"""GitHub release update helpers."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from utils.app_paths import executable_root, user_data_dir
from utils.app_version import get_app_version


GITHUB_REPO = "davidchiu66/IPTV_Ultimate_Player_Codex"
LATEST_RELEASE_API = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{GITHUB_REPO}/releases"
REQUEST_TIMEOUT = 20


@dataclass
class ReleaseInfo:
    version: str
    tag_name: str
    html_url: str
    body: str
    assets: list[dict]


@dataclass
class UpdateCheckResult:
    local_version: str
    latest_version: str
    has_update: bool
    release: ReleaseInfo | None
    message: str


def normalize_version(version: str) -> str:
    """Normalize a display/tag version to a comparable text."""
    text = str(version or "").strip()
    if text.lower().startswith("v"):
        text = text[1:]
    return text.strip()


def _version_parts(version: str) -> tuple[list[int], int, int]:
    text = normalize_version(version).lower()
    match = re.match(r"^(\d+(?:\.\d+)*)(?:[-_.]?([a-z]+)(\d*)?)?", text)
    if not match:
        raise ValueError(f"无法解析版本号：{version}")

    numbers = [int(part) for part in match.group(1).split(".")]
    stage_text = (match.group(2) or "").lower()
    stage_number = int(match.group(3) or 0)
    stage_rank = {
        "dev": -40,
        "alpha": -30,
        "a": -30,
        "beta": -20,
        "b": -20,
        "rc": -10,
        "preview": -10,
        "": 0,
    }.get(stage_text, -50)
    return numbers, stage_rank, stage_number


def compare_versions(local: str, remote: str) -> int:
    """Compare versions. Return -1 if local is lower than remote."""
    left_numbers, left_stage, left_stage_number = _version_parts(local)
    right_numbers, right_stage, right_stage_number = _version_parts(remote)
    width = max(len(left_numbers), len(right_numbers))
    left_numbers += [0] * (width - len(left_numbers))
    right_numbers += [0] * (width - len(right_numbers))
    if left_numbers < right_numbers:
        return -1
    if left_numbers > right_numbers:
        return 1
    if left_stage < right_stage:
        return -1
    if left_stage > right_stage:
        return 1
    if left_stage_number < right_stage_number:
        return -1
    if left_stage_number > right_stage_number:
        return 1
    return 0


def fetch_latest_release() -> ReleaseInfo:
    """Fetch the latest GitHub release metadata."""
    response = requests.get(
        LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "IPTV-Ultimate-Player-Updater",
        },
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    tag_name = str(data.get("tag_name") or "").strip()
    version = normalize_version(tag_name)
    return ReleaseInfo(
        version=version,
        tag_name=tag_name,
        html_url=str(data.get("html_url") or RELEASES_URL),
        body=str(data.get("body") or ""),
        assets=list(data.get("assets") or []),
    )


def check_for_updates() -> UpdateCheckResult:
    """Check GitHub latest release against the bundled app version."""
    local_version = normalize_version(get_app_version())
    release = fetch_latest_release()
    comparison = compare_versions(local_version, release.version)
    has_update = comparison < 0
    message = (
        f"发现新版本：{release.version}（当前版本：{local_version}）"
        if has_update
        else f"当前已是最新版本：{local_version}"
    )
    return UpdateCheckResult(
        local_version=local_version,
        latest_version=release.version,
        has_update=has_update,
        release=release,
        message=message,
    )


def update_download_dir() -> Path:
    """Return the writable update download directory."""
    path = user_data_dir() / "updates"
    path.mkdir(parents=True, exist_ok=True)
    return path


def detect_distribution_kind() -> str:
    """Return source, portable, installer or unknown."""
    if not getattr(sys, "frozen", False):
        return "source"

    root = executable_root()
    if (root / "README_PORTABLE.txt").is_file():
        return "portable"

    root_text = str(root).lower()
    program_dirs = [
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
    ]
    for value in program_dirs:
        if value and root_text.startswith(str(Path(value)).lower()):
            return "installer"
    return "unknown"


def select_update_asset(release: ReleaseInfo, preferred_kind: str) -> dict | None:
    """Select an installer or portable asset from a release."""
    assets = list(release.assets or [])
    if preferred_kind == "portable":
        preferred = [
            asset for asset in assets
            if str(asset.get("name") or "").lower().endswith(".zip")
            and "portable" in str(asset.get("name") or "").lower()
        ]
        if preferred:
            return preferred[0]

    installer = [
        asset for asset in assets
        if str(asset.get("name") or "").lower().endswith(".exe")
        and any(token in str(asset.get("name") or "").lower() for token in ("setup", "installer"))
    ]
    if preferred_kind in {"installer", "unknown", "source"} and installer:
        return installer[0]

    portable = [
        asset for asset in assets
        if str(asset.get("name") or "").lower().endswith(".zip")
        and "portable" in str(asset.get("name") or "").lower()
    ]
    if portable:
        return portable[0]
    return installer[0] if installer else None


def download_asset(
    asset: dict,
    cancel_event: threading.Event | None = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
) -> Path:
    """Download a GitHub release asset and report byte progress."""
    url = str(asset.get("browser_download_url") or "")
    name = str(asset.get("name") or "update-package").strip() or "update-package"
    if not url:
        raise ValueError("Release 资产缺少下载地址")

    target = update_download_dir() / name
    part = target.with_suffix(target.suffix + ".part")
    if part.exists():
        try:
            part.unlink()
        except OSError:
            pass

    with requests.get(
        url,
        stream=True,
        timeout=REQUEST_TIMEOUT,
        headers={"User-Agent": "IPTV-Ultimate-Player-Updater"},
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or asset.get("size") or 0)
        downloaded = 0
        with part.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 256):
                if cancel_event is not None and cancel_event.is_set():
                    raise RuntimeError("下载已取消")
                if not chunk:
                    continue
                handle.write(chunk)
                downloaded += len(chunk)
                if progress_callback is not None:
                    progress_callback(downloaded, total, name)

    if target.exists():
        target.unlink()
    part.replace(target)
    return target


def launch_installer(installer_path: str | os.PathLike[str]) -> None:
    """Launch an installer package."""
    subprocess.Popen([str(installer_path)], close_fds=True)


def create_portable_update_script(zip_path: str | os.PathLike[str]) -> Path:
    """Create a PowerShell script that applies a portable package after exit."""
    zip_file = Path(zip_path).resolve()
    app_dir = executable_root().resolve()
    exe_path = Path(sys.executable).resolve()
    script_path = update_download_dir() / "apply_portable_update.ps1"
    log_path = update_download_dir() / "update_apply.log"
    extract_dir = update_download_dir() / f"portable_extract_{int(time.time())}"

    if not zip_file.is_file():
        raise FileNotFoundError(f"更新包不存在：{zip_file}")
    if not app_dir.is_dir() or len(str(app_dir)) < 4:
        raise ValueError(f"应用目录不安全：{app_dir}")

    def ps_quote(value: str | os.PathLike[str]) -> str:
        text = str(value)
        return "'" + text.replace("'", "''") + "'"

    script = f"""
$ErrorActionPreference = "Stop"
$pidToWait = {os.getpid()}
$zipPath = {ps_quote(zip_file)}
$appDir = {ps_quote(app_dir)}
$exePath = {ps_quote(exe_path)}
$extractDir = {ps_quote(extract_dir)}
$logPath = {ps_quote(log_path)}

function Write-UpdateLog($message) {{
  $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -LiteralPath $logPath -Value "[$timestamp] $message"
}}

try {{
  Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
  Write-UpdateLog "waiting for process $pidToWait"
  Wait-Process -Id $pidToWait -ErrorAction SilentlyContinue
  if (Test-Path -LiteralPath $extractDir) {{
    Remove-Item -LiteralPath $extractDir -Recurse -Force
  }}
  New-Item -ItemType Directory -Force -Path $extractDir | Out-Null
  Expand-Archive -LiteralPath $zipPath -DestinationPath $extractDir -Force
  $packageRoot = Get-ChildItem -LiteralPath $extractDir -Directory | Select-Object -First 1
  if ($null -eq $packageRoot) {{
    throw "portable package root not found"
  }}
  $newExe = Get-ChildItem -LiteralPath $packageRoot.FullName -Filter "*.exe" | Select-Object -First 1
  if ($null -eq $newExe) {{
    throw "portable package exe not found"
  }}
  Write-UpdateLog "copying files to $appDir"
  Copy-Item -Path (Join-Path $packageRoot.FullName "*") -Destination $appDir -Recurse -Force
  Write-UpdateLog "starting $exePath"
  Start-Process -FilePath $exePath -WorkingDirectory $appDir
  Write-UpdateLog "update applied"
}} catch {{
  Write-UpdateLog ("update failed: " + $_.Exception.Message)
  [System.Windows.Forms.MessageBox]::Show("便携版更新失败，请查看日志：$logPath", "在线更新")
}}
"""
    script_path.write_text(script.strip() + "\n", encoding="utf-8")
    return script_path


def launch_portable_updater(zip_path: str | os.PathLike[str]) -> Path:
    """Launch the generated portable updater script."""
    script_path = create_portable_update_script(zip_path)
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        close_fds=True,
    )
    return script_path


def zip_contains_executable(zip_path: str | os.PathLike[str]) -> bool:
    """Return whether a zip package contains an executable."""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            return any(name.lower().endswith(".exe") for name in archive.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def remove_path_quietly(path: str | os.PathLike[str]) -> None:
    """Remove a file or directory without raising."""
    try:
        target = Path(path)
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    except OSError:
        pass
