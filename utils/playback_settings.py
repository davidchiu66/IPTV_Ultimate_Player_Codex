from utils.proxy_settings import load_settings, save_settings


DEFAULT_LOCAL_PLAYBACK_MODE = "smooth"
LOCAL_PLAYBACK_MODES = {"smooth", "quality", "extreme"}
DEFAULT_LIVE_PLAYBACK_MODE = "smooth"
LIVE_PLAYBACK_MODES = {"smooth", "quality"}


def get_local_playback_mode(default=DEFAULT_LOCAL_PLAYBACK_MODE):
    settings = load_settings()
    playback = settings.get("playback")
    if not isinstance(playback, dict):
        return default
    mode = str(playback.get("local_mode") or default).strip().lower()
    return mode if mode in LOCAL_PLAYBACK_MODES else default


def set_local_playback_mode(mode):
    settings = load_settings()
    playback = settings.get("playback")
    if not isinstance(playback, dict):
        playback = {}
    mode = str(mode or DEFAULT_LOCAL_PLAYBACK_MODE).strip().lower()
    playback["local_mode"] = mode if mode in LOCAL_PLAYBACK_MODES else DEFAULT_LOCAL_PLAYBACK_MODE
    settings["playback"] = playback
    save_settings(settings)


def get_live_playback_mode(default=DEFAULT_LIVE_PLAYBACK_MODE):
    settings = load_settings()
    playback = settings.get("playback")
    if not isinstance(playback, dict):
        return default
    mode = str(playback.get("live_mode") or default).strip().lower()
    return mode if mode in LIVE_PLAYBACK_MODES else default


def set_live_playback_mode(mode):
    settings = load_settings()
    playback = settings.get("playback")
    if not isinstance(playback, dict):
        playback = {}
    mode = str(mode or DEFAULT_LIVE_PLAYBACK_MODE).strip().lower()
    playback["live_mode"] = mode if mode in LIVE_PLAYBACK_MODES else DEFAULT_LIVE_PLAYBACK_MODE
    settings["playback"] = playback
    save_settings(settings)
