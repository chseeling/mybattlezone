import json
import sys
from argparse import ArgumentParser
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT_DIR / "models" / "digitization01_cleaned.json"
DEFAULT_OUTPUT = ROOT_DIR / "models" / "digitization01_cleaned_02.json"


def round_points(input_path=DEFAULT_INPUT, output_path=DEFAULT_OUTPUT, precision=3):
    input_path = Path(input_path)
    output_path = Path(output_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        points = json.load(f)

    points_round = [[round(num, precision) for num in point] for point in points]

    with output_path.open("w", encoding="utf-8") as outfile:
        json.dump(points_round, outfile)

    return output_path


def parse_args():
    parser = ArgumentParser(description="Round mountain point coordinates.")
    parser.add_argument("input", nargs="?", default=DEFAULT_INPUT, help="Source JSON point file.")
    parser.add_argument("output", nargs="?", default=DEFAULT_OUTPUT, help="Destination JSON point file.")
    parser.add_argument("--precision", type=int, default=3, help="Decimal places to keep.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    try:
        output = round_points(args.input, args.output, args.precision)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)

    print(f"Wrote rounded points to {output}")
