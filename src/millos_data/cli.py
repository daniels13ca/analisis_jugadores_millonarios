from __future__ import annotations

import argparse
from pathlib import Path

from .config import ApiConfig
from .consolidate import consolidate_dataset
from .extract import download_season_matches


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Millonarios data utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    consolidate_parser = subparsers.add_parser("consolidate", help="Consolidate JSON files into a CSV")
    consolidate_parser.add_argument("--base-path", default=".", help="Repo root or data directory")
    consolidate_parser.add_argument(
        "--output",
        default="dataset_millonarios_consolidado.csv",
        help="Destination CSV path",
    )
    consolidate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Process files without writing the CSV",
    )

    season_parser = subparsers.add_parser("download-season", help="Download finished matches for a season")
    season_parser.add_argument("--season", type=int, required=True)
    season_parser.add_argument("--output-dir", default=None)

    return parser


def main() -> None:
    args = build_parser().parse_args()

    if args.command == "consolidate":
        result = consolidate_dataset(
            base_path=Path(args.base_path).resolve(),
            output_path=Path(args.output).resolve(),
            write_output=not args.dry_run,
        )
        print(
            f"scanned_files={result.scanned_files} "
            f"skipped_existing_matches={result.skipped_existing_matches} "
            f"empty_matches={result.empty_matches} "
            f"new_rows={result.new_rows} "
            f"total_rows={len(result.dataframe)}"
        )
        return

    config = ApiConfig.from_env()

    if args.command == "download-season":
        output_dir = Path(args.output_dir or f"Millonarios_{args.season}_Stats_Detalladas").resolve()
        stats = download_season_matches(config, season=args.season, output_dir=output_dir)
        print(stats)
        return


if __name__ == "__main__":
    main()
