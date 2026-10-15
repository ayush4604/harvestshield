"""Run `python -m backend.cli demo`, `train --mode real`, or `audit --mode real`."""
import argparse
import json

from .config import Settings
from .data import ProjectError, Store, demo_frame, parse_csv
from .models import ModelService
from .feed import refresh_feed


def main():
    parser = argparse.ArgumentParser(description="HarvestShield data/model commands")
    parser.add_argument("command", choices=["demo", "train", "audit", "import", "refresh", "backtest"])
    parser.add_argument("--mode", choices=["demo", "real"], default="demo")
    parser.add_argument("--file")
    parser.add_argument("--source", default="")
    parser.add_argument("--state", default="")
    parser.add_argument("--commodity", default="")
    parser.add_argument("--market", default="")
    parser.add_argument("--series-id", action="append", help="Repeat to select a focused training/backtest cohort.")
    args = parser.parse_args()
    store = Store(Settings.default())
    models = ModelService(store)
    try:
        if args.command == "demo":
            if store.frame("demo").empty:
                print(json.dumps(store.ingest(demo_frame(), "demo", "SYNTHETIC: fictional demo; seed 42"), indent=2))
            path, _ = models.paths("demo")
            result = models.report("demo") if path.exists() else models.train("demo")
        elif args.command == "train":
            result = models.train(args.mode, series_ids=args.series_id)
        elif args.command == "backtest":
            result = models.backtest(args.mode, series_ids=args.series_id)
        elif args.command == "audit":
            result = store.audit(args.mode)
        elif args.command == "refresh":
            if not args.state or not args.commodity:
                parser.error("refresh requires --state and --commodity")
            result = refresh_feed(store, args.state, args.commodity, args.market)
        else:
            if not args.file or not args.source:
                parser.error("import requires --file and --source; imported files are always real-mode records")
            from pathlib import Path
            content = Path(args.file).read_bytes()
            result = store.ingest(parse_csv(content), "real", args.source)
        print(json.dumps(result, indent=2, allow_nan=False))
    except ProjectError as exc:
        parser.exit(1, f"HarvestShield: {exc}\n")


if __name__ == "__main__":
    main()
