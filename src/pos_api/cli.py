"""`restaurant-pos-api`: prepare demo data if needed, then serve the POS API."""

import argparse
import sys

import uvicorn

from pos_api.db.seed import ensure_demo_data


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the mock restaurant POS API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    print("Preparing demo data (first run takes ~15 seconds)...", file=sys.stderr)
    print(f"Demo data: {ensure_demo_data()}", file=sys.stderr)
    uvicorn.run("pos_api.main:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
