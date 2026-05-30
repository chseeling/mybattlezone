import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from battlezone.config import DEFAULT_CLIENT_CONTROLLER, DEFAULT_CLIENT_TANK_ID, DEFAULT_NETWORK_HOST, DEFAULT_NETWORK_PORT


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "client_config.json"
GAME_PATH = APP_DIR / "test02.py"

DEFAULT_CONFIG = {
    "server_host": DEFAULT_NETWORK_HOST,
    "server_port": DEFAULT_NETWORK_PORT,
    "tank_id": DEFAULT_CLIENT_TANK_ID,
    "controller": DEFAULT_CLIENT_CONTROLLER,
    "low_render": False,
}


def load_config():
    config = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                config.update({key: data[key] for key in config if key in data})
        except (OSError, json.JSONDecodeError):
            pass
    return config


def save_config(config):
    CONFIG_PATH.write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalized_config(config):
    next_config = dict(DEFAULT_CONFIG)
    next_config.update(config)
    next_config["server_host"] = str(next_config["server_host"]).strip() or DEFAULT_CONFIG["server_host"]
    next_config["server_port"] = str(next_config["server_port"]).strip() or DEFAULT_CONFIG["server_port"]
    next_config["tank_id"] = str(next_config["tank_id"]).strip() or DEFAULT_CONFIG["tank_id"]
    next_config["controller"] = str(next_config["controller"]).strip().lower() or DEFAULT_CONFIG["controller"]
    next_config["low_render"] = bool(next_config["low_render"])
    return next_config


def validate_config(config):
    errors = []
    try:
        port = int(config["server_port"])
        if port < 1 or port > 65535:
            errors.append("Server port must be between 1 and 65535.")
    except (TypeError, ValueError):
        errors.append("Server port must be a number.")

    try:
        tank_id = int(config["tank_id"])
        if tank_id < 0:
            errors.append("Tank must be 0 or higher.")
    except (TypeError, ValueError):
        errors.append("Tank must be a number.")

    if config["controller"] not in {"human", "auto", "autonomous", "ai"}:
        errors.append("Controller must be human or autonomous.")

    if not GAME_PATH.exists():
        errors.append("Could not find test02.py beside the launcher.")

    return errors


def launch_client(config):
    config = normalized_config(config)
    errors = validate_config(config)
    if errors:
        raise ValueError("\n".join(errors))

    env = os.environ.copy()
    env.update({
        "BATTLEZONE_NET_MODE": "client",
        "BATTLEZONE_NET_HOST": config["server_host"],
        "BATTLEZONE_NET_PORT": str(config["server_port"]),
        "BATTLEZONE_NET_TANK": str(config["tank_id"]),
        "BATTLEZONE_NET_CONTROLLER": config["controller"],
        "BATTLEZONE_NET_CLIENT_LOW_RENDER": "1" if config["low_render"] else "0",
    })
    save_config(config)
    return subprocess.Popen([sys.executable, str(GAME_PATH)], cwd=str(APP_DIR), env=env)


def prompt_for_config(config):
    config = normalized_config(config)
    print("Battlezone Client")
    print("Press Enter to keep the current value.")
    host = input("Server IP [{}]: ".format(config["server_host"])).strip()
    port = input("Server port [{}]: ".format(config["server_port"])).strip()
    tank = input("Tank [{}]: ".format(config["tank_id"])).strip()
    controller = input("Controller [{}]: ".format(config["controller"])).strip()
    low_render_default = "y" if config["low_render"] else "n"
    low_render = input("Low render mode [{}]: ".format(low_render_default)).strip().lower()

    if host:
        config["server_host"] = host
    if port:
        config["server_port"] = port
    if tank:
        config["tank_id"] = tank
    if controller:
        config["controller"] = controller
    if low_render:
        config["low_render"] = low_render in {"1", "true", "yes", "y", "on"}
    return normalized_config(config)


def run_terminal(config):
    while True:
        config = prompt_for_config(config)
        errors = validate_config(config)
        if not errors:
            process = launch_client(config)
            print("Started Battlezone client with PID {}.".format(process.pid))
            return process.wait()
        print("\n".join(errors))


def run_gui(config):
    try:
        import tkinter as tk
        from tkinter import messagebox
    except ImportError:
        return run_terminal(config)

    config = normalized_config(config)
    try:
        root = tk.Tk()
    except tk.TclError:
        return run_terminal(config)
    root.title("Battlezone Client")
    root.resizable(False, False)

    server_host = tk.StringVar(value=config["server_host"])
    server_port = tk.StringVar(value=str(config["server_port"]))
    tank_id = tk.StringVar(value=str(config["tank_id"]))
    controller = tk.StringVar(value=config["controller"])
    low_render = tk.BooleanVar(value=bool(config["low_render"]))
    status = tk.StringVar(value="Ready")

    frame = tk.Frame(root, padx=16, pady=14)
    frame.grid(row=0, column=0, sticky="nsew")

    def row(label, variable, index, width=24):
        tk.Label(frame, text=label, anchor="w").grid(row=index, column=0, sticky="w", pady=4)
        entry = tk.Entry(frame, textvariable=variable, width=width)
        entry.grid(row=index, column=1, sticky="ew", pady=4)
        return entry

    row("Server IP", server_host, 0)
    row("Port", server_port, 1, width=10)
    row("Tank", tank_id, 2, width=10)

    tk.Label(frame, text="Controller", anchor="w").grid(row=3, column=0, sticky="w", pady=4)
    controller_menu = tk.OptionMenu(frame, controller, "human", "autonomous")
    controller_menu.grid(row=3, column=1, sticky="ew", pady=4)

    tk.Checkbutton(frame, text="Low render", variable=low_render).grid(row=4, column=1, sticky="w", pady=6)

    status_label = tk.Label(frame, textvariable=status, anchor="w")
    status_label.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 10))

    def current_config():
        return normalized_config({
            "server_host": server_host.get(),
            "server_port": server_port.get(),
            "tank_id": tank_id.get(),
            "controller": controller.get(),
            "low_render": low_render.get(),
        })

    def save_current():
        next_config = current_config()
        errors = validate_config(next_config)
        if errors:
            messagebox.showerror("Battlezone Client", "\n".join(errors))
            return
        save_config(next_config)
        status.set("Saved")

    def play():
        next_config = current_config()
        errors = validate_config(next_config)
        if errors:
            messagebox.showerror("Battlezone Client", "\n".join(errors))
            return
        try:
            process = launch_client(next_config)
        except OSError as exc:
            messagebox.showerror("Battlezone Client", str(exc))
            return
        status.set("Started PID {}".format(process.pid))

    buttons = tk.Frame(frame)
    buttons.grid(row=6, column=0, columnspan=2, sticky="e")
    tk.Button(buttons, text="Save", command=save_current, width=10).grid(row=0, column=0, padx=(0, 8))
    tk.Button(buttons, text="Play", command=play, width=10).grid(row=0, column=1)

    frame.columnconfigure(1, weight=1)
    root.mainloop()
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Launch the Battlezone LAN client.")
    parser.add_argument("--host", help="Server LAN IP or hostname.")
    parser.add_argument("--port", help="Server UDP port.")
    parser.add_argument("--tank", help="Tank slot to claim.")
    parser.add_argument("--controller", choices=["human", "autonomous", "auto", "ai"], help="Client controller.")
    parser.add_argument("--low-render", action="store_true", help="Use the lighter client renderer.")
    parser.add_argument("--full-render", action="store_true", help="Use the full client renderer.")
    parser.add_argument("--terminal", action="store_true", help="Use terminal prompts instead of the GUI.")
    parser.add_argument("--play", action="store_true", help="Launch immediately using config and flags.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv if argv is not None else sys.argv[1:])
    config = load_config()
    if args.host:
        config["server_host"] = args.host
    if args.port:
        config["server_port"] = args.port
    if args.tank:
        config["tank_id"] = args.tank
    if args.controller:
        config["controller"] = args.controller
    if args.low_render:
        config["low_render"] = True
    if args.full_render:
        config["low_render"] = False

    if args.play:
        try:
            process = launch_client(config)
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2
        return process.wait()

    if args.terminal:
        return run_terminal(config)
    return run_gui(config)


if __name__ == "__main__":
    raise SystemExit(main())
