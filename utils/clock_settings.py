from utils.proxy_settings import load_settings, save_settings


DEFAULT_CLOCK_SHOW_WEEKDAY = True


def get_clock_show_weekday(default=DEFAULT_CLOCK_SHOW_WEEKDAY):
    """Return whether the floating clock should show weekday text."""
    settings = load_settings()
    ui = settings.get("ui")
    if isinstance(ui, dict) and "clock_show_weekday" in ui:
        return bool(ui.get("clock_show_weekday"))
    return bool(default)


def set_clock_show_weekday(enabled):
    """Persist whether the floating clock should show weekday text."""
    settings = load_settings()
    ui = settings.get("ui")
    if not isinstance(ui, dict):
        ui = {}
    ui["clock_show_weekday"] = bool(enabled)
    settings["ui"] = ui
    save_settings(settings)
