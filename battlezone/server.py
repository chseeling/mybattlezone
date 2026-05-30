import argparse

from .config import DEFAULT_NETWORK_PORT, DEFAULT_SERVER_BIND_HOST, DEFAULT_SERVER_LOG_INTERVAL, DEFAULT_SERVER_UI, DEFAULT_SERVER_WINDOW
from .runtime import run_game


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the authoritative Battlezone LAN server.")
    parser.add_argument("--host", default=DEFAULT_SERVER_BIND_HOST, help="Server bind address.")
    parser.add_argument("--port", default=DEFAULT_NETWORK_PORT, help="Server UDP port.")
    parser.add_argument("--ui", default=DEFAULT_SERVER_UI, choices=["panda", "tui", "logs", "json", "headless", "none"], help="Server operator UI.")
    parser.add_argument("--log-interval", default=DEFAULT_SERVER_LOG_INTERVAL, help="Seconds between JSON status logs.")
    parser.add_argument("--window", default=DEFAULT_SERVER_WINDOW, help="Server window mode.")
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
