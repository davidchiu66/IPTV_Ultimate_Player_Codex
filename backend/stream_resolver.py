import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from html import unescape
from typing import Any

from utils.proxy_settings import get_effective_proxy
from utils.url_cleaning import clean_media_url


DEFAULT_TIMEOUT = 15
MAX_BODY_BYTES = 512 * 1024
DEFAULT_BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
DEFAULT_CH_UA = '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"'

_CACHE: dict[tuple[Any, ...], dict[str, Any]] = {}

_JSON_MEDIA_KEYS = {
    "url",
    "playurl",
    "play_url",
    "liveurl",
    "live_url",
    "videourl",
    "video_url",
    "streamurl",
    "stream_url",
    "manifest",
    "manifesturl",
    "manifest_url",
    "hls",
    "hlsurl",
    "hls_url",
    "dash",
    "dashurl",
    "dash_url",
    "m3u8",
    "mpd",
    "flv",
    "mp4",
}

_SCRIPT_JSON_PATTERNS = [
    r"__NEXT_DATA__\s*=\s*(\{.*?\})\s*;",
    r"__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
    r"__NUXT__\s*=\s*(\{.*?\})\s*;",
    r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\})\s*;",
    r"window\.__NEXT_DATA__\s*=\s*(\{.*?\})\s*;",
    r"window\.__NUXT__\s*=\s*(\{.*?\})\s*;",
    r"window\.__APOLLO_STATE__\s*=\s*(\{.*?\})\s*;",
    r"window\.__DATA__\s*=\s*(\{.*?\})\s*;",
    r"window\.__data__\s*=\s*(\{.*?\})\s*;",
    r"window\.__PLAYER_CONFIG__\s*=\s*(\{.*?\})\s*;",
    r"window\.__PLAY_INFO__\s*=\s*(\{.*?\})\s*;",
    r"window\.__LIVE_DATA__\s*=\s*(\{.*?\})\s*;",
    r"window\.playerConfig\s*=\s*(\{.*?\})\s*;",
    r"window\.playInfo\s*=\s*(\{.*?\})\s*;",
    r"window\.liveInfo\s*=\s*(\{.*?\})\s*;",
]


def _now() -> float:
    return time.time()


def _notify(progress_callback: Callable[[str], None] | None, message: str) -> None:
    if progress_callback is None or not message:
        return
    try:
        progress_callback(str(message))
    except Exception:
        pass


def _is_cancelled(cancel_callback: Callable[[], bool] | None) -> bool:
    if cancel_callback is None:
        return False
    try:
        return bool(cancel_callback())
    except Exception:
        return False


def _cancelled_result(url: str = "", message: str = "解析已取消") -> dict[str, Any]:
    return _make_result(
        status="cancelled",
        final_url=url,
        message=message,
    )


def _make_result(
    *,
    status: str,
    media_url: str = "",
    media_type: str = "unknown",
    http_status: int | None = None,
    final_url: str = "",
    message: str = "",
    need_js_probe: bool = False,
    resolved_from: str = "",
    candidates: list[str] | None = None,
) -> dict[str, Any]:
    media_url = clean_media_url(media_url)
    final_url = clean_media_url(final_url)
    clean_candidates = [clean_media_url(item) for item in (candidates or [])]
    return {
        "status": status,
        "media_url": media_url or "",
        "media_type": media_type or "unknown",
        "http_status": int(http_status) if isinstance(http_status, int) else http_status,
        "final_url": final_url or "",
        "message": message or "",
        "need_js_probe": bool(need_js_probe),
        "resolved_from": resolved_from or "",
        "candidates": [item for item in clean_candidates if item],
    }


def _cache_key(channel: dict[str, Any]) -> tuple[Any, ...]:
    headers = channel.get("Headers") or {}
    header_items = tuple(sorted((str(k), str(v)) for k, v in headers.items()))
    proxy_value, proxy_source = get_effective_proxy(channel)
    return (
        channel.get("Manifest") or "",
        channel.get("UserAgent") or "",
        channel.get("Referer") or "",
        header_items,
        proxy_value or "",
        proxy_source or "",
    )


def _cache_ttl(result: dict[str, Any]) -> int:
    status = result.get("status")
    http_status = result.get("http_status")
    need_js_probe = bool(result.get("need_js_probe"))

    if status == "ok":
        return 600
    if http_status in {404, 410, 451}:
        return 120
    if http_status in {401, 403, 405, 408, 412, 416, 429}:
        return 90
    if http_status in {500, 502, 503, 504}:
        return 45
    if need_js_probe:
        return 45
    return 30


def _get_cached(channel: dict[str, Any], force: bool) -> dict[str, Any] | None:
    if force:
        return None
    key = _cache_key(channel)
    item = _CACHE.get(key)
    if not item:
        return None
    if item["expires_at"] <= _now():
        _CACHE.pop(key, None)
        return None
    result = dict(item["result"])
    result["message"] = f"{result.get('message') or 'cache hit'} [cache]"
    return result


def _set_cached(channel: dict[str, Any], result: dict[str, Any]) -> None:
    _CACHE[_cache_key(channel)] = {
        "result": dict(result),
        "expires_at": _now() + _cache_ttl(result),
    }


def _classify_http_status(http_status: int | None) -> str:
    if http_status is None:
        return "unknown"
    if 200 <= http_status < 300:
        return "success"
    if 300 <= http_status < 400:
        return "redirect"
    if http_status in {404, 410, 451}:
        return "dead"
    if http_status in {401, 403, 405, 406, 408, 409, 412, 416, 429}:
        return "request_error"
    if 400 <= http_status < 500:
        return "client_error"
    if 500 <= http_status < 600:
        return "server_error"
    return "unknown"


def _guess_media_type(url: str, content_type: str, body_bytes: bytes) -> str:
    lower_url = (url or "").lower()
    lower_type = (content_type or "").lower()
    if ".m3u8" in lower_url or "mpegurl" in lower_type:
        return "hls"
    if ".mpd" in lower_url or "dash" in lower_type:
        return "dash"
    if ".flv" in lower_url or "x-flv" in lower_type or "flv" in lower_type:
        return "flv"
    if ".mp4" in lower_url or "video/mp4" in lower_type or "mp4" in lower_type:
        return "mp4"
    if body_bytes.startswith(b"#EXTM3U"):
        return "hls"
    if len(body_bytes) >= 3 and body_bytes[:3] == b"FLV":
        return "flv"
    if b"ftyp" in body_bytes[:64]:
        return "mp4"
    return "unknown"


def _guess_direct_media_type(url: str) -> str:
    """Return a media type when the URL itself is an explicit media URL."""
    lower_url = (url or "").lower()
    if ".m3u8" in lower_url:
        return "hls"
    if ".mpd" in lower_url:
        return "dash"
    if ".flv" in lower_url:
        return "flv"
    if ".mp4" in lower_url or ".m4v" in lower_url or ".mov" in lower_url:
        return "mp4"
    if ".ts" in lower_url:
        return "hls"
    return "unknown"


def _is_explicit_media_url(url: str) -> bool:
    """Return whether the URL already points at a known media resource."""
    return _guess_direct_media_type(url) != "unknown"


def _direct_media_result(
    url: str,
    *,
    http_status: int | None = None,
    final_url: str = "",
    message: str = "explicit media url passthrough",
) -> dict[str, Any]:
    """Build a successful resolver result for explicit media URLs."""
    resolved_url = clean_media_url(final_url or url)
    media_type = _guess_direct_media_type(resolved_url)
    if media_type == "unknown":
        media_type = _guess_direct_media_type(url)
    return _make_result(
        status="ok",
        media_url=resolved_url,
        media_type=media_type,
        http_status=http_status,
        final_url=resolved_url,
        message=message,
        resolved_from="direct",
    )


def _looks_like_html(content_type: str, body_text: str) -> bool:
    lower_type = (content_type or "").lower()
    if "text/html" in lower_type or "application/xhtml" in lower_type:
        return True
    sample = (body_text or "").strip().lower()
    return sample.startswith("<!doctype html") or sample.startswith("<html") or "<script" in sample


def _normalize_page_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url or "")
    host = (parsed.netloc or "").lower()
    if host == "m.gdtv.cn" and parsed.path.startswith("/tvChannelDetail/"):
        return urllib.parse.urlunparse(
            (
                parsed.scheme or "https",
                "www.gdtv.cn",
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    if parsed.scheme == "http" and host.endswith(".xhscdn.com") and "sns-video" in host:
        return urllib.parse.urlunparse(
            (
                "https",
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    return url


def _absolutize_candidate(base_url: str, value: str) -> str:
    text = clean_media_url(value)
    if not text:
        return ""
    if text.startswith("//"):
        parsed_base = urllib.parse.urlparse(base_url or "")
        scheme = parsed_base.scheme or "https"
        return clean_media_url(f"{scheme}:{text}")
    return clean_media_url(urllib.parse.urljoin(base_url or "", text))


def _candidate_sort_key(url: str) -> tuple[int, int]:
    lower = (url or "").lower()
    if ".mpd" in lower:
        return (0, len(url))
    if ".m3u8" in lower:
        return (1, len(url))
    if ".flv" in lower:
        return (2, len(url))
    if ".mp4" in lower:
        return (3, len(url))
    return (9, len(url))


def _dedupe_candidates(candidates: list[str]) -> list[str]:
    unique: list[str] = []
    seen = set()
    for item in candidates:
        clean = clean_media_url(item)
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    unique.sort(key=_candidate_sort_key)
    return unique


def _extract_candidates_from_html(text: str, base_url: str = "") -> list[str]:
    if not text:
        return []
    decoded = unescape(text)
    patterns = [
        r"https?://[^\s'\"<>]+\.m3u8(?:\?[^\s'\"<>]*)?",
        r"https?://[^\s'\"<>]+\.mpd(?:\?[^\s'\"<>]*)?",
        r"https?://[^\s'\"<>]+\.mp4(?:\?[^\s'\"<>]*)?",
        r"https?://[^\s'\"<>]+\.flv(?:\?[^\s'\"<>]*)?",
        r"(?:source|file|url|playlist|manifest|stream|hls|dash|playUrl|liveUrl)\s*[:=]\s*['\"]([^'\"<>]+)['\"]",
    ]
    candidates: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, decoded, flags=re.IGNORECASE):
            value = match if isinstance(match, str) else ""
            if not value:
                continue
            abs_value = _absolutize_candidate(base_url, value)
            lower = abs_value.lower()
            if (
                lower.startswith("http://")
                or lower.startswith("https://")
                or ".m3u8" in lower
                or ".mpd" in lower
                or ".mp4" in lower
                or ".flv" in lower
            ):
                candidates.append(abs_value)
    return _dedupe_candidates(candidates)


def _walk_json_for_media(obj: Any, candidates: list[str], base_url: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            key_text = str(key).strip().lower()
            if key_text in _JSON_MEDIA_KEYS and isinstance(value, str):
                abs_value = _absolutize_candidate(base_url, value)
                lower = abs_value.lower()
                if any(token in lower for token in (".m3u8", ".mpd", ".mp4", ".flv")):
                    candidates.append(abs_value)
            _walk_json_for_media(value, candidates, base_url)
    elif isinstance(obj, list):
        for item in obj:
            _walk_json_for_media(item, candidates, base_url)
    elif isinstance(obj, str):
        abs_value = _absolutize_candidate(base_url, obj)
        lower = abs_value.lower()
        if any(token in lower for token in (".m3u8", ".mpd", ".mp4", ".flv")):
            candidates.append(abs_value)


def _extract_candidates_from_script_json(text: str, base_url: str = "") -> list[str]:
    if not text:
        return []
    decoded = unescape(text)
    candidates: list[str] = []
    for pattern in _SCRIPT_JSON_PATTERNS:
        for match in re.findall(pattern, decoded, flags=re.IGNORECASE | re.DOTALL):
            if not isinstance(match, str):
                continue
            try:
                data = json.loads(match)
            except Exception:
                continue
            _walk_json_for_media(data, candidates, base_url)
    return _dedupe_candidates(candidates)


def _extract_candidates_from_inline_scripts(text: str, base_url: str = "") -> list[str]:
    if not text:
        return []
    decoded = unescape(text)
    patterns = [
        r"(?:playUrl|play_url|liveUrl|live_url|videoUrl|video_url|streamUrl|stream_url|manifestUrl|manifest_url|source|src)\s*[:=]\s*['\"]([^'\"<>]+)['\"]",
        r"(?:playUrl|play_url|liveUrl|live_url|videoUrl|video_url|streamUrl|stream_url|manifestUrl|manifest_url|source|src)\s*[:=]\s*(https?://[^\s'\"<>]+)",
        r"https?://[^\s'\"<>]+(?:manifest|playlist|stream|play|live|media|video|api)[^\s'\"<>]*",
        r"['\"]((?:/|https?://)[^'\"<>]*(?:manifest|playlist|stream|play|live|media|video|api)[^'\"<>]*)['\"]",
    ]
    candidates: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, decoded, flags=re.IGNORECASE):
            value = match if isinstance(match, str) else ""
            if not value:
                continue
            candidates.append(_absolutize_candidate(base_url, value))
    return _dedupe_candidates(candidates)


def _extract_candidate_api_urls(text: str, base_url: str = "") -> list[str]:
    if not text:
        return []
    decoded = unescape(text)
    patterns = [
        r"https?://[^\s'\"<>]+(?:channel|detail|live|play|stream|video|api)[^\s'\"<>]*",
        r"['\"]((?:/|https?://)[^'\"<>]*(?:channel|detail|live|play|stream|video|api)[^'\"<>]*)['\"]",
    ]
    results: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, decoded, flags=re.IGNORECASE):
            value = match if isinstance(match, str) else ""
            if not value:
                continue
            results.append(_absolutize_candidate(base_url, value))
    return _dedupe_candidates(results)


def _request_context(channel: dict[str, Any]) -> dict[str, Any]:
    headers = {}
    if isinstance(channel.get("Headers"), dict):
        headers.update({str(k): str(v) for k, v in channel["Headers"].items()})
    if channel.get("UserAgent"):
        headers["User-Agent"] = str(channel["UserAgent"])
    if channel.get("Referer"):
        headers["Referer"] = str(channel["Referer"])
    proxy_value, _proxy_source = get_effective_proxy(channel)
    return {
        "url": _normalize_page_url(clean_media_url(channel.get("Manifest") or "")),
        "headers": headers,
        "proxy": proxy_value or "",
    }


def _add_default_header(req: urllib.request.Request, existing_headers: dict[str, str], key: str, value: str) -> None:
    """Add a browser-like request header unless the channel already supplied it."""
    lower_existing = {str(name).lower() for name in existing_headers}
    if key.lower() not in lower_existing:
        req.add_header(key, value)


def _add_browser_like_headers(
    req: urllib.request.Request,
    existing_headers: dict[str, str],
    *,
    url: str,
    method: str,
    use_range: bool,
) -> None:
    """Make resolver probes look like normal Chromium navigation/media requests."""
    explicit_media = _is_explicit_media_url(url)
    _add_default_header(req, existing_headers, "User-Agent", DEFAULT_BROWSER_USER_AGENT)
    _add_default_header(req, existing_headers, "Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
    _add_default_header(req, existing_headers, "sec-ch-ua", DEFAULT_CH_UA)
    _add_default_header(req, existing_headers, "sec-ch-ua-mobile", "?0")
    _add_default_header(req, existing_headers, "sec-ch-ua-platform", '"Windows"')
    _add_default_header(req, existing_headers, "DNT", "1")
    _add_default_header(req, existing_headers, "Connection", "keep-alive")

    if explicit_media:
        _add_default_header(req, existing_headers, "Accept", "*/*")
        _add_default_header(req, existing_headers, "Sec-Fetch-Site", "none")
        _add_default_header(req, existing_headers, "Sec-Fetch-Mode", "no-cors")
        _add_default_header(req, existing_headers, "Sec-Fetch-Dest", "video")
        _add_default_header(req, existing_headers, "Pragma", "no-cache")
        _add_default_header(req, existing_headers, "Cache-Control", "no-cache")
    else:
        _add_default_header(
            req,
            existing_headers,
            "Accept",
            "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        )
        _add_default_header(req, existing_headers, "Sec-Fetch-Site", "none")
        _add_default_header(req, existing_headers, "Sec-Fetch-Mode", "navigate")
        _add_default_header(req, existing_headers, "Sec-Fetch-Dest", "document")
        _add_default_header(req, existing_headers, "Upgrade-Insecure-Requests", "1")

    if use_range:
        _add_default_header(req, existing_headers, "Range", "bytes=0-4095")


def _build_opener(proxy_value: str) -> urllib.request.OpenerDirector:
    handlers: list[Any] = []
    if proxy_value:
        handlers.append(urllib.request.ProxyHandler({"http": proxy_value, "https": proxy_value}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))
    handlers.append(urllib.request.HTTPRedirectHandler())
    return urllib.request.build_opener(*handlers)


def _perform_request(channel: dict[str, Any], method: str, use_range: bool = False) -> dict[str, Any]:
    ctx = _request_context(channel)
    url = ctx["url"]
    opener = _build_opener(ctx["proxy"])
    req = urllib.request.Request(url, method=method)
    for key, value in ctx["headers"].items():
        req.add_header(key, value)
    _add_browser_like_headers(req, ctx["headers"], url=url, method=method, use_range=use_range)

    body_bytes = b""
    body_text = ""
    final_url = url
    content_type = ""
    http_status: int | None = None

    try:
        with opener.open(req, timeout=DEFAULT_TIMEOUT) as response:
            http_status = response.status
            final_url = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            if method != "HEAD":
                body_bytes = response.read(MAX_BODY_BYTES)
    except urllib.error.HTTPError as exc:
        http_status = exc.code
        final_url = exc.geturl() or url
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        if method != "HEAD":
            try:
                body_bytes = exc.read(MAX_BODY_BYTES)
            except Exception:
                body_bytes = b""
    except urllib.error.URLError as exc:
        return {
            "http_status": 502,
            "final_url": final_url,
            "content_type": content_type,
            "body_bytes": body_bytes,
            "body_text": body_text,
            "error": f"upstream connection error: {exc.reason}",
        }
    except Exception as exc:
        return {
            "http_status": 500,
            "final_url": final_url,
            "content_type": content_type,
            "body_bytes": body_bytes,
            "body_text": body_text,
            "error": f"request error: {exc}",
        }

    if body_bytes:
        try:
            body_text = body_bytes.decode("utf-8", errors="ignore")
        except Exception:
            body_text = ""

    return {
        "http_status": http_status,
        "final_url": final_url,
        "content_type": content_type,
        "body_bytes": body_bytes,
        "body_text": body_text,
        "error": "",
    }


def _probe_detail_api_candidates(
    channel: dict[str, Any],
    page_url: str,
    body_text: str,
    progress_callback: Callable[[str], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> list[str]:
    parsed = urllib.parse.urlparse(page_url or "")
    path = parsed.path or ""
    match = re.search(r"/tvChannelDetail/(\d+)", path)
    candidates = _extract_candidate_api_urls(body_text, page_url)

    if match and parsed.netloc.lower().endswith("gdtv.cn"):
        channel_id = match.group(1)
        base_candidates = [
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/tvChannelDetail/{channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/tvChannelDetail?id={channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/tv/channel/detail/{channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/tv/channel/detail?id={channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/channel/detail/{channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/channel/detail?id={channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/tvChannel/playUrl?id={channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/tvChannel/liveUrl?id={channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/playUrl?channelId={channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/liveUrl?channelId={channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/channel/play?id={channel_id}",
            f"{parsed.scheme or 'https'}://{parsed.netloc}/api/channel/live?id={channel_id}",
        ]
        candidates.extend(base_candidates)

    results: list[str] = []
    for api_url in _dedupe_candidates(candidates):
        if _is_cancelled(cancel_callback):
            break
        if not api_url:
            continue
        _notify(progress_callback, f"正在探测页面接口：{api_url}")
        api_channel = dict(channel or {})
        api_channel["Manifest"] = api_url
        info = _perform_request(api_channel, "GET", use_range=False)
        if info.get("error"):
            continue
        body = info.get("body_text") or ""
        if not body:
            continue
        new_candidates = _extract_candidates_from_html(body, api_url)
        new_candidates.extend(_extract_candidates_from_script_json(body, api_url))
        new_candidates.extend(_extract_candidates_from_inline_scripts(body, api_url))
        if not new_candidates:
            try:
                data = json.loads(body)
            except Exception:
                data = None
            if data is not None:
                temp: list[str] = []
                _walk_json_for_media(data, temp, api_url)
                new_candidates.extend(temp)
        if new_candidates:
            results.extend(new_candidates)
            break
    return _dedupe_candidates(results)


def resolve_channel(
    channel: dict[str, Any],
    *,
    force: bool = False,
    progress_callback: Callable[[str], None] | None = None,
    cancel_callback: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    if _is_cancelled(cancel_callback):
        return _cancelled_result(channel.get("Manifest", ""))

    cached = _get_cached(channel, force=force)
    if cached is not None:
        _notify(progress_callback, "已命中解析缓存，正在准备播放...")
        return cached

    url = _normalize_page_url(clean_media_url(channel.get("Manifest") or ""))
    if not url:
        result = _make_result(status="error", message="缺少直播地址")
        _set_cached(channel, result)
        return result

    normalized_channel = dict(channel or {})
    normalized_channel["Manifest"] = url
    explicit_media_url = _is_explicit_media_url(url)

    _notify(progress_callback, "正在检测直播链接...")
    if _is_cancelled(cancel_callback):
        return _cancelled_result(url)
    if explicit_media_url:
        _notify(progress_callback, "正在以浏览器媒体请求检测直连地址...")
        response_info = _perform_request(normalized_channel, "GET", use_range=True)
    else:
        response_info = _perform_request(normalized_channel, "HEAD")
    http_status = response_info.get("http_status")
    status_class = _classify_http_status(http_status)

    if explicit_media_url and status_class in {"request_error", "client_error", "unknown"}:
        _notify(progress_callback, "直连媒体地址浏览器探测不可用，正在重试 GET 检测...")
        if _is_cancelled(cancel_callback):
            return _cancelled_result(url)
        response_info = _perform_request(normalized_channel, "GET", use_range=True)
        http_status = response_info.get("http_status")
        status_class = _classify_http_status(http_status)
    elif http_status == 405:
        _notify(progress_callback, "源站不支持 HEAD，正在改用 GET 检测...")
        if _is_cancelled(cancel_callback):
            return _cancelled_result(url)
        response_info = _perform_request(normalized_channel, "GET", use_range=True)
        http_status = response_info.get("http_status")
        status_class = _classify_http_status(http_status)
    elif http_status == 416:
        _notify(progress_callback, "Range 探测不可用，正在改用普通 GET...")
        if _is_cancelled(cancel_callback):
            return _cancelled_result(url)
        response_info = _perform_request(normalized_channel, "GET", use_range=False)
        http_status = response_info.get("http_status")
        status_class = _classify_http_status(http_status)
    elif status_class in {"success", "redirect"} and http_status not in {204, 205, 304}:
        _notify(progress_callback, "正在分析响应内容...")
        if _is_cancelled(cancel_callback):
            return _cancelled_result(url)
        response_info = _perform_request(normalized_channel, "GET", use_range=True)
        http_status = response_info.get("http_status")
        status_class = _classify_http_status(http_status)

    if _is_cancelled(cancel_callback):
        return _cancelled_result(url)

    if response_info.get("error"):
        if explicit_media_url:
            result = _direct_media_result(
                url,
                final_url=response_info.get("final_url") or url,
                message=f"explicit media url passthrough after probe error: {response_info['error']}",
            )
            _set_cached(normalized_channel, result)
            return result
        result = _make_result(
            status="error",
            http_status=response_info.get("http_status"),
            final_url=response_info.get("final_url") or url,
            message=response_info["error"],
        )
        _set_cached(normalized_channel, result)
        return result

    final_url = _normalize_page_url(response_info.get("final_url") or url)
    content_type = response_info.get("content_type") or ""
    body_bytes = response_info.get("body_bytes") or b""
    body_text = response_info.get("body_text") or ""

    if status_class == "dead":
        result = _make_result(
            status="dead",
            http_status=http_status,
            final_url=final_url,
            message="直播链接已不存在或不可用",
        )
        _set_cached(normalized_channel, result)
        return result

    if status_class == "server_error":
        if explicit_media_url:
            result = _direct_media_result(
                url,
                http_status=http_status,
                final_url=final_url,
                message="explicit media url passthrough after server-side probe error",
            )
            _set_cached(normalized_channel, result)
            return result
        result = _make_result(
            status="error",
            http_status=http_status,
            final_url=final_url,
            message="源站或网关异常",
        )
        _set_cached(normalized_channel, result)
        return result

    if status_class == "request_error":
        if explicit_media_url and http_status not in {401, 403, 404, 410, 451}:
            result = _direct_media_result(
                url,
                http_status=http_status,
                final_url=final_url,
                message="explicit media url passthrough after request probe rejection",
            )
            _set_cached(normalized_channel, result)
            return result
        message_map = {
            401: "源地址存在，但当前请求未授权",
            403: "源地址存在，但当前请求被拒绝",
            405: "源站不支持当前探测方式",
            406: "请求内容不被接受",
            408: "请求超时",
            409: "请求冲突",
            412: "请求前置条件失败",
            416: "Range 探测失败",
            429: "请求过于频繁，已被限流",
        }
        result = _make_result(
            status="error",
            http_status=http_status,
            final_url=final_url,
            message=message_map.get(http_status, "请求异常"),
        )
        _set_cached(normalized_channel, result)
        return result

    if http_status in {204, 205}:
        result = _make_result(
            status="unresolved",
            http_status=http_status,
            final_url=final_url,
            message="源地址响应正常，但当前没有可用媒体内容",
        )
        _set_cached(normalized_channel, result)
        return result

    if http_status == 304:
        result = _make_result(
            status="unresolved",
            http_status=http_status,
            final_url=final_url,
            message="命中缓存状态，但当前没有可复用的解析结果",
        )
        _set_cached(normalized_channel, result)
        return result

    media_type = _guess_media_type(final_url, content_type, body_bytes)
    if media_type != "unknown":
        _notify(progress_callback, "已识别媒体地址，正在准备播放...")
        resolved_from = "redirect" if clean_media_url(final_url) != clean_media_url(url) else "direct"
        result = _make_result(
            status="ok",
            media_url=final_url,
            media_type=media_type,
            http_status=http_status,
            final_url=final_url,
            message=f"resolved from {media_type}",
            resolved_from=resolved_from,
        )
        _set_cached(normalized_channel, result)
        return result

    if explicit_media_url:
        _notify(progress_callback, "已识别直连媒体地址，正在准备播放...")
        result = _direct_media_result(
            url,
            http_status=http_status,
            final_url=final_url,
            message="resolved from explicit media url",
        )
        _set_cached(normalized_channel, result)
        return result

    if _looks_like_html(content_type, body_text):
        _notify(progress_callback, "正在嗅探页面中的媒体地址...")
        if _is_cancelled(cancel_callback):
            return _cancelled_result(final_url)
        candidates = _extract_candidates_from_html(body_text, final_url)
        candidates.extend(_extract_candidates_from_script_json(body_text, final_url))
        candidates.extend(_extract_candidates_from_inline_scripts(body_text, final_url))
        candidates = _dedupe_candidates(candidates)
        if not candidates:
            _notify(progress_callback, "静态页面未命中，正在探测详情接口...")
            if _is_cancelled(cancel_callback):
                return _cancelled_result(final_url)
            candidates = _probe_detail_api_candidates(
                normalized_channel,
                final_url,
                body_text,
                progress_callback,
                cancel_callback,
            )
        if candidates:
            first = candidates[0]
            guessed = _guess_media_type(first, "", b"")
            _notify(progress_callback, "已从页面中找到媒体地址，正在准备播放...")
            result = _make_result(
                status="ok",
                media_url=first,
                media_type=guessed if guessed != "unknown" else "hls",
                http_status=http_status,
                final_url=final_url,
                message="resolved from html",
                resolved_from="html",
                candidates=candidates,
            )
            _set_cached(normalized_channel, result)
            return result
        result = _make_result(
            status="page",
            http_status=http_status,
            final_url=final_url,
            message="页面型源需要进一步 JS 嗅探",
            need_js_probe=True,
            resolved_from="html",
        )
        _set_cached(normalized_channel, result)
        return result

    result = _make_result(
        status="unresolved",
        http_status=http_status,
        final_url=final_url,
        message="未能识别媒体类型",
    )
    _set_cached(normalized_channel, result)
    return result
