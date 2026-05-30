import argparse

from .runtime import run_game


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run a Battlezone LAN client.")
    parser.add_argument("--host", default="127.0.0.1", help="Server LAN IP or hostname.")
    parser.add_argument("--port", default="51515", help="Server UDP port.")
    parser.add_argument("--tank", default="0", help="Tank slot to claim.")
    parser.add_argument("--controller", default="human", choices=["human", "autonomous", "auto", "ai"], help="Client controller.")
    parser.add_argument("--low-render", action="store_true", help="Use the lighter client renderer.")
    parser.add_argument("--full-render", action="store_true", help="Use the full client renderer.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    low_render = "1" if args.low_render and not args.full_render else "0"
    return run_game({
        "BATTLEZONE_NET_MODE": "client",
        "BATTLEZONE_NET_HOST": args.host,
        "BATTLEZONE_NET_PORT": args.port,
        "BATTLEZONE_NET_TANK": args.tank,
        "BATTLEZONE_NET_CONTROLLER": args.controller,
        "BATTLEZONE_NET_CLIENT_LOW_RENDER": low_render,
    })


if __name__ == "__main__":
    raise SystemExit(main())
