import json
import os
import urllib.request


SETTINGS_PATH = os.path.join("config", "app_settings.json")
DEFAULT_BROWSER_PROBE_TIMEOUT_MS = 30000
MIN_BROWSER_PROBE_TIMEOUT_MS = 3000
MAX_BROWSER_PROBE_TIMEOUT_MS = 120000
DEFAULT_BROWSER_PORT = 8000
MIN_BROWSER_PORT = 1024
MAX_BROWSER_PORT = 65535


def _ensure_config_dir():
    config_dir = os.path.dirname(SETTINGS_PATH)
    if config_dir and not os.path.exists(config_dir):
        os.makedirs(config_dir)


def load_settings():
    if not os.path.exists(SETTINGS_PATH):
        return {}
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(settings):
    _ensure_config_dir()
    with open(SETTINGS_PATH, "w", encoding="utf-8") as handle:
        json.dump(settings or {}, handle, ensure_ascii=False, indent=2)


def _clamp_browser_probe_timeout_ms(value, default=DEFAULT_BROWSER_PROBE_TIMEOUT_MS):
    try:
        timeout_ms = int(value)
    except (TypeError, ValueError):
        timeout_ms = int(default)
    if timeout_ms < MIN_BROWSER_PROBE_TIMEOUT_MS:
        return MIN_BROWSER_PROBE_TIMEOUT_MS
    if timeout_ms > MAX_BROWSER_PROBE_TIMEOUT_MS:
        return MAX_BROWSER_PROBE_TIMEOUT_MS
    return timeout_ms


def _clamp_browser_port(value, default=DEFAULT_BROWSER_PORT):
    try:
        port = int(value)
    except (TypeError, ValueError):
        port = int(default)
    if port < MIN_BROWSER_PORT:
        return MIN_BROWSER_PORT
    if port > MAX_BROWSER_PORT:
        return MAX_BROWSER_PORT
    return port


def get_user_proxy():
    settings = load_settings()
    proxy = settings.get("proxy", {}) if isinstance(settings.get("proxy"), dict) else {}
    enabled = proxy.get("enabled", True)
    value = proxy.get("user_proxy", "")
    if not enabled:
        return ""
    return value.strip() if isinstance(value, str) else ""


def set_user_proxy(proxy_value, enabled=True):
    settings = load_settings()
    settings["proxy"] = {
        "enabled": bool(enabled),
        "user_proxy": (proxy_value or "").strip(),
    }
    save_settings(settings)


def get_system_proxy():
    try:
        proxies = urllib.request.getproxies()
    except Exception:
        proxies = {}

    if not isinstance(proxies, dict):
        return ""

    for key in ("https", "http", "all"):
        value = proxies.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def get_effective_proxy(channel=None):
    system_proxy = get_system_proxy()
    if system_proxy:
        return system_proxy, "system"

    user_proxy = get_user_proxy()
    if user_proxy:
        return user_proxy, "user"

    if isinstance(channel, dict):
        for key in ("Proxy", "ManifestProxy", "MediaProxy", "ScriptProxy"):
            value = channel.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip(), "channel"

    return "", "direct"


def get_browser_probe_timeout_ms(default=DEFAULT_BROWSER_PROBE_TIMEOUT_MS):
    settings = load_settings()
    browser_probe = settings.get("browser_probe", {})
    if isinstance(browser_probe, dict) and "timeout_ms" in browser_probe:
        return _clamp_browser_probe_timeout_ms(browser_probe.get("timeout_ms"), default)

    legacy_value = settings.get("browser_probe_timeout_ms")
    if legacy_value is not None:
        return _clamp_browser_probe_timeout_ms(legacy_value, default)

    return _clamp_browser_probe_timeout_ms(default, default)


def set_browser_probe_timeout_ms(timeout_ms):
    settings = load_settings()
    browser_probe = settings.get("browser_probe")
    if not isinstance(browser_probe, dict):
        browser_probe = {}
    browser_probe["timeout_ms"] = _clamp_browser_probe_timeout_ms(timeout_ms)
    settings["browser_probe"] = browser_probe
    save_settings(settings)


def get_browser_port(default=DEFAULT_BROWSER_PORT):
    settings = load_settings()
    browser = settings.get("browser", {})
    if isinstance(browser, dict) and "port" in browser:
        return _clamp_browser_port(browser.get("port"), default)

    legacy_value = settings.get("browser_port")
    if legacy_value is not None:
        return _clamp_browser_port(legacy_value, default)

    return _clamp_browser_port(default, default)


def set_browser_port(port):
    settings = load_settings()
    browser = settings.get("browser")
    if not isinstance(browser, dict):
        browser = {}
    browser["port"] = _clamp_browser_port(port)
    settings["browser"] = browser
    save_settings(settings)
