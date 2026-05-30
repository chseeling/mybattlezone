import argparse

from .runtime import run_game


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the authoritative Battlezone LAN server.")
    parser.add_argument("--host", default="0.0.0.0", help="Server bind address.")
    parser.add_argument("--port", default="51515", help="Server UDP port.")
    parser.add_argument("--ui", default="logs", choices=["panda", "tui", "logs", "json", "headless", "none"], help="Server operator UI.")
    parser.add_argument("--log-interval", default="5", help="Seconds between JSON status logs.")
    parser.add_argument("--window", default="minimized", help="Server window mode.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    return run_game({
        "BATTLEZONE_NET_MODE": "server",
        "BATTLEZONE_NET_HOST": args.host,
        "BATTLEZONE_NET_PORT": args.port,
        "BATTLEZONE_SERVER_UI": args.ui,
        "BATTLEZONE_SERVER_LOG_INTERVAL": args.log_interval,
        "BATTLEZONE_SERVER_WINDOW": args.window,
    })


if __name__ == "__main__":
    raise SystemExit(main())
