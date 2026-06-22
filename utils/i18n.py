import json
import os

from utils.proxy_settings import load_settings, save_settings


DEFAULT_LANGUAGE = "zh_CN"
SUPPORTED_LANGUAGES = ("zh_CN", "en_US")
_CACHE = {}


def _i18n_path(language):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "i18n", f"{language}.json")


def _load_catalog(language):
    language = language if language in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    if language in _CACHE:
        return _CACHE[language]
    try:
        with open(_i18n_path(language), "r", encoding="utf-8") as handle:
            data = json.load(handle)
            catalog = data if isinstance(data, dict) else {}
    except Exception:
        catalog = {}
    _CACHE[language] = catalog
    return catalog


def get_language(default=DEFAULT_LANGUAGE):
    settings = load_settings()
    ui = settings.get("ui")
    if not isinstance(ui, dict):
        return default
    language = str(ui.get("language") or default).strip()
    return language if language in SUPPORTED_LANGUAGES else default


def set_language(language):
    language = str(language or DEFAULT_LANGUAGE).strip()
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    settings = load_settings()
    ui = settings.get("ui")
    if not isinstance(ui, dict):
        ui = {}
    ui["language"] = language
    settings["ui"] = ui
    save_settings(settings)


def tr(key, default=""):
    language = get_language()
    catalog = _load_catalog(language)
    if key in catalog:
        return str(catalog[key])
    fallback = _load_catalog(DEFAULT_LANGUAGE)
    return str(fallback.get(key, default or key))
