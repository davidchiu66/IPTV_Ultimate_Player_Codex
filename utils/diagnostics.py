import json
import os
import re
import sys
import time
import uuid
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from utils.proxy_settings import load_settings, save_settings
from utils.logging_utils import append_capped_log_line, app_log_path


DIAGNOSTICS_LOG_PATH = str(app_log_path())
DEFAULT_LEVEL = "error"
LEVELS = ("off", "error", "info", "debug")
LEVEL_RANK = {"off": 0, "error": 1, "info": 2, "debug": 3}

SENSITIVE_KEY_NAMES = {
    "authorization",
    "cookie",
    "set-cookie",
    "keys",
    "license",
    "licenseurl",
    "license_url",
    "drm",
}
SENSITIVE_KEY_PARTS = (
    "token",
    "session",
    "signature",
    "secret",
    "password",
    "auth",
    "license",
    "key",
)
SENSITIVE_QUERY_PARTS = (
    "token",
    "session",
    "signature",
    "sig",
    "auth",
    "license",
    "key",
    "jwt",
    "expires",
    "expire",
    "hdnts",
)


def new_trace_id():
    return uuid.uuid4().hex[:12]


def get_diagnostics_settings():
    settings = load_settings()
    diagnostics = settings.get("diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}

    enabled = bool(diagnostics.get("enabled", False))
    level = str(diagnostics.get("level") or DEFAULT_LEVEL).strip().lower()
    if level not in LEVELS:
        level = DEFAULT_LEVEL

    return {
        "enabled": enabled,
        "level": level,
        "log_path": DIAGNOSTICS_LOG_PATH,
        "browser_probe_details": bool(diagnostics.get("browser_probe_details", True)),
    }


def set_diagnostics_settings(enabled, level=DEFAULT_LEVEL):
    settings = load_settings()
    diagnostics = settings.get("diagnostics")
    if not isinstance(diagnostics, dict):
        diagnostics = {}
    level = str(level or DEFAULT_LEVEL).strip().lower()
    if level not in LEVELS:
        level = DEFAULT_LEVEL
    diagnostics["enabled"] = bool(enabled)
    diagnostics["level"] = level
    settings["diagnostics"] = diagnostics
    save_settings(settings)


def should_log(level="info"):
    diagnostics = get_diagnostics_settings()
    if not diagnostics.get("enabled"):
        return False
    current_level = diagnostics.get("level") or DEFAULT_LEVEL
    level = str(level or "info").lower()
    return LEVEL_RANK.get(current_level, 0) >= LEVEL_RANK.get(level, 2)


def _is_sensitive_key(key):
    lowered = str(key or "").strip().lower()
    if lowered in SENSITIVE_KEY_NAMES:
        return True
    return any(part in lowered for part in SENSITIVE_KEY_PARTS)


def sanitize_url(url):
    if not isinstance(url, str) or not url:
        return url
    try:
        parsed = urlparse(url)
    except Exception:
        return url
    if not parsed.scheme or not parsed.netloc:
        return url
    query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if any(part in lowered for part in SENSITIVE_QUERY_PARTS):
            query.append((key, "***"))
        else:
            query.append((key, value))
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True, safe="*")))


def sanitize(value, key=""):
    if _is_sensitive_key(key):
        return "***"
    if isinstance(value, dict):
        return {str(k): sanitize(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(item, key) for item in value[:80]]
    if isinstance(value, tuple):
        return [sanitize(item, key) for item in value[:80]]
    if isinstance(value, str):
        return sanitize_url(value)
    return value


def summarize_channel(channel):
    if not isinstance(channel, dict):
        return {}
    return sanitize(
        {
            "name": channel.get("Name", ""),
            "category": channel.get("Category", ""),
            "manifest": channel.get("Manifest", ""),
            "manifest_type": channel.get("ManifestType", ""),
            "drm_type": channel.get("DrmType", ""),
            "cdm_type": channel.get("CdmType", ""),
            "use_local_proxy": channel.get("UseLocalProxy", False),
            "proxy": channel.get("Proxy", ""),
            "manifest_proxy": channel.get("ManifestProxy", ""),
            "media_proxy": channel.get("MediaProxy", ""),
            "referer": channel.get("Referer", ""),
            "user_agent": channel.get("UserAgent", ""),
        }
    )


def log_event(event, level="info", trace_id="", channel=None, force=False, **data):
    if not force and not should_log(level):
        return False
    diagnostics = get_diagnostics_settings()
    path = diagnostics.get("log_path") or DIAGNOSTICS_LOG_PATH
    record = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "time": time.time(),
        "level": level,
        "event": event,
        "trace_id": trace_id or "",
    }
    if channel is not None:
        record["channel"] = summarize_channel(channel)
    record.update(sanitize(data))

    try:
        line = "diag: " + json.dumps(record, ensure_ascii=False, default=str)
        session_log_path = os.environ.get("IPTV_SESSION_LOG_PATH", "")
        if session_log_path and os.path.abspath(session_log_path) == os.path.abspath(path):
            sys.stderr.write(line + "\n")
            return True
        return append_capped_log_line(line, path)
    except Exception:
        return False


def infer_http_status(error_info):
    http_status = error_info.get("http_status") if isinstance(error_info, dict) else None
    if isinstance(http_status, int):
        return http_status
    code = str((error_info or {}).get("code") or "")
    match = re.search(r"http[-_ ]?([0-9]{3})", code, re.IGNORECASE)
    if match:
        return int(match.group(1))
    detail = str((error_info or {}).get("detail") or "")
    match = re.search(r"\b(4[0-9]{2}|5[0-9]{2})\b", detail)
    return int(match.group(1)) if match else None


def _http_message(http_status):
    if http_status in {401, 403}:
        return "源站拒绝访问，可能需要 Referer、Cookie、地区权限或有效签名", "可尝试浏览器播放，或检查请求头、代理和源地址时效。"
    if http_status in {404, 410, 451}:
        return "直播链接不存在或已失效", "建议切换其他频道，或尝试播放下一个频道。"
    if http_status == 400:
        return "直播链接请求无效，可能签名过期或参数不完整", "建议刷新源列表或重新探测页面真实地址。"
    if http_status in {408, 429}:
        return "源站响应超时或请求过于频繁", "建议稍后重试，或调整代理后再试。"
    if http_status and 500 <= http_status < 600:
        return "源站服务器异常", "建议稍后重试，或切换其他线路。"
    if http_status and 400 <= http_status < 500:
        return "直播链接当前不可用", "建议检查源地址、请求头或改用浏览器播放。"
    return "", ""


def classify_failure(error_info):
    error_info = error_info or {}
    code = str(error_info.get("code") or "").strip().lower()
    stage = str(error_info.get("failure_stage") or "").strip().lower()
    http_status = infer_http_status(error_info)

    if http_status:
        summary, suggestion = _http_message(http_status)
        if summary:
            return {
                "title": summary,
                "summary": summary,
                "suggestion": suggestion,
                "stage_label": _stage_label(stage),
                "http_status": http_status,
            }

    mapping = {
        "source-dead": ("直播链接不存在或已失效", "建议切换其他频道，或尝试播放下一个频道。"),
        "need-js-probe": ("页面型直播源需要进一步探测", "程序会尝试受控浏览器嗅探真实直播地址。"),
        "unresolved-media": ("未识别到真实媒体地址", "可尝试重试探测，或改用浏览器播放。"),
        "probe-timeout": ("网页探测超时", "页面可能加载较慢、需要交互或网络不稳定，可重试探测或调大超时时长。"),
        "probe-failed": ("网页探测未找到可播放源", "可重试探测，或改用浏览器播放。"),
        "idle-active": ("播放器未成功打开媒体", "该地址可能是页面型源或源站拒绝直接播放，程序会尝试网页探测。"),
        "loadfile": ("libmpv 加载媒体失败", "可能是源地址、请求头、防盗链、代理或格式兼容问题。"),
        "unavailable": ("libmpv 未初始化成功", "请检查 libmpv DLL、运行库和播放器窗口初始化状态。"),
        "cenc-timeout": ("CENC 解密轨道未建立", "可能是 Keys、KID、音视频轨道或解密链路异常。"),
        "audio-timeout": ("音频轨道初始化超时", "视频已就绪但音频轨等待过久，可重试或切换音轨/频道。"),
        "resolve-failed": ("媒体解析失败", "未能从当前地址解析出可播放媒体。"),
    }
    summary, suggestion = mapping.get(code, ("播放失败", "可重试当前频道，或改用浏览器播放。"))
    return {
        "title": summary,
        "summary": summary,
        "suggestion": suggestion,
        "stage_label": _stage_label(stage),
        "http_status": http_status,
    }


def _stage_label(stage):
    return {
        "resolve": "媒体解析",
        "probe": "网页探测",
        "mpv": "libmpv 播放",
        "browser-probe": "网页探测",
    }.get(stage or "", stage or "未知阶段")


def format_failure_details(error_info, extra=None):
    payload = {
        "failure": error_info or {},
        "extra": extra or {},
    }
    try:
        return json.dumps(sanitize(payload), ensure_ascii=False, indent=2, default=str)
    except Exception:
        return str(sanitize(payload))
