import argparse
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from src.publish_existing import publish_existing_session


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish an already rendered session video without rerunning the pipeline.")
    parser.add_argument("--session", required=True, help="Existing session directory, e.g. ./output/VN/20260622095230_vi")
    parser.add_argument("--platform", choices=["youtube", "facebook"], required=True, help="Target platform to publish")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = publish_existing_session(args.session, args.platform)
    if result.get("success"):
        print(f"Publish succeeded: {result.get('url')}")
        return

    print(f"Publish failed: {result.get('error')}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
