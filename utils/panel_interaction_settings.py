from utils.proxy_settings import load_settings, save_settings


PANEL_INTERACTION_HOVER = "hover"
PANEL_INTERACTION_CLICK = "click"
DEFAULT_PANEL_INTERACTION_MODE = PANEL_INTERACTION_HOVER
VALID_PANEL_INTERACTION_MODES = {
    PANEL_INTERACTION_HOVER,
    PANEL_INTERACTION_CLICK,
}


def normalize_panel_interaction_mode(mode: str | None) -> str:
    value = str(mode or "").strip().lower()
    if value in VALID_PANEL_INTERACTION_MODES:
        return value
    return DEFAULT_PANEL_INTERACTION_MODE


def get_panel_interaction_mode() -> str:
    settings = load_settings()
    ui = settings.get("ui")
    if not isinstance(ui, dict):
        ui = {}
    return normalize_panel_interaction_mode(ui.get("panel_interaction_mode"))


def set_panel_interaction_mode(mode: str | None) -> None:
    settings = load_settings()
    ui = settings.get("ui")
    if not isinstance(ui, dict):
        ui = {}
    ui["panel_interaction_mode"] = normalize_panel_interaction_mode(mode)
    settings["ui"] = ui
    save_settings(settings)
