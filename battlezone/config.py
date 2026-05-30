import os


TRUTHY_VALUES = {"1", "true", "yes", "on"}
SERVER_LOG_UI_MODES = {"log", "logs", "json", "headless"}
SERVER_HEADLESS_UI_MODES = SERVER_LOG_UI_MODES | {"none", "off"}

DEFAULT_NETWORK_HOST = "127.0.0.1"
DEFAULT_NETWORK_PORT = "51515"
DEFAULT_SERVER_BIND_HOST = "0.0.0.0"
DEFAULT_SERVER_UI = "logs"
DEFAULT_SERVER_LOG_INTERVAL = "5"
DEFAULT_SERVER_WINDOW = "minimized"
DEFAULT_SERVER_TUI_WINDOW = "minimized"
DEFAULT_CLIENT_TANK_ID = "0"
DEFAULT_CLIENT_CONTROLLER = "human"
DEFAULT_CLIENT_LOW_RENDER_SIZE = (960, 540)
DEFAULT_SERVER_LOW_RENDER_SIZE = (720, 405)


def env_bool(name, default=False, env=None):
    env = env or os.environ
    default_value = "1" if default else "0"
    return env.get(name, default_value).lower() in TRUTHY_VALUES


def env_float(name, default, env=None):
    env = env or os.environ
    try:
        return float(env.get(name, default))
    except (TypeError, ValueError):
        return float(default)


def env_size(name, default, env=None):
    env = env or os.environ
    raw = env.get(name, "")
    if not raw:
        return default
    parts = raw.lower().replace(",", "x").split("x")
    if len(parts) != 2:
        return default
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError:
        return default
    if width < 320 or height < 200:
        return default
    return (width, height)


def configured_server_ui_mode(env=None):
    env = env or os.environ
    requested = env.get("BATTLEZONE_SERVER_UI", "").lower()
    if requested:
        return requested

    legacy_tui = env.get("BATTLEZONE_SERVER_TUI", "").lower()
    if legacy_tui in {"1", "true", "yes", "on", "tui", "curses"}:
        return "tui"
    return "panda"


def configured_network_mode(env=None):
    env = env or os.environ
    mode = env.get("BATTLEZONE_NET_MODE", "").lower()
    return "host" if mode == "server" else mode


def configured_network_mode_label(env=None):
    env = env or os.environ
    return "server" if env.get("BATTLEZONE_NET_MODE", "").lower() == "server" else configured_network_mode(env)


def client_controller_default(tank_id):
    return "human" if str(tank_id) == "0" else "autonomous"


def client_low_render_default(tank_id):
    return "0" if str(tank_id) == "0" else "1"


def should_silence_server_startup(env=None):
    env = env or os.environ
    net_mode = env.get("BATTLEZONE_NET_MODE", "").lower()
    server_ui = env.get("BATTLEZONE_SERVER_UI", "").lower()
    return net_mode in {"server", "host"} and server_ui in SERVER_HEADLESS_UI_MODES
