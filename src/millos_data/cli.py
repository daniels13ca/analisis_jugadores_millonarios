from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .config import ApiConfig, season_directory_name
from .consolidate import consolidate_dataset
from .dedupe import archive_duplicate_matches
from .extract import download_season_matches


def _add_base_path_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--base-path", default=".", help="Repo root or data directory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Millonarios data utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)

    consolidate_parser = subparsers.add_parser("consolidate", help="Consolidate JSON files into a CSV")
    _add_base_path_argument(consolidate_parser)
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
    consolidate_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Ignore the existing output CSV and regenerate it from scratch using only the JSON files on disk",
    )

    season_parser = subparsers.add_parser("download-season", help="Download finished matches for a season")
    season_parser.add_argument("--season", type=int, required=True)
    season_parser.add_argument("--output-dir", default=None)

    dedupe_parser = subparsers.add_parser(
        "dedupe-matches",
        help="Find JSON match files that represent the same real match (e.g. a rival team rename) and archive the redundant copies",
    )
    _add_base_path_argument(dedupe_parser)
    dedupe_parser.add_argument(
        "--archive-dir",
        default="_archived_duplicates",
        help="Where redundant JSON files are moved to (never deleted)",
    )
    dedupe_parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually move the duplicate files. Without this flag, only a report is printed.",
    )

    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    args = build_parser().parse_args()

    if args.command == "consolidate":
        result = consolidate_dataset(
            base_path=Path(args.base_path).resolve(),
            output_path=Path(args.output).resolve(),
            write_output=not args.dry_run,
            rebuild=args.rebuild,
        )
        print(
            f"scanned_files={result.scanned_files} "
            f"skipped_existing_matches={result.skipped_existing_matches} "
            f"empty_matches={result.empty_matches} "
            f"new_rows={result.new_rows} "
            f"total_rows={len(result.dataframe)}"
        )
        return

    if args.command == "dedupe-matches":
        result = archive_duplicate_matches(
            base_path=Path(args.base_path).resolve(),
            archive_dir=Path(args.archive_dir).resolve(),
            dry_run=not args.apply,
        )
        mode = "DRY-RUN (use --apply to move files)" if result.dry_run else "APPLIED"
        print(
            f"[{mode}] scanned_files={result.scanned_files} "
            f"duplicate_groups={len(result.duplicate_groups)} "
            f"archived_files={len(result.archived_files)} "
            f"ambiguous_groups={len(result.ambiguous_groups)}"
        )
        for group in result.duplicate_groups:
            fecha, condicion, resultado = group.key
            print(f"  match {fecha} {condicion} ({resultado}): keeping {group.kept}")
            for duplicate in group.archived:
                print(f"    -> archiving {duplicate}")
        for ambiguous in result.ambiguous_groups:
            fecha, condicion, resultado = ambiguous.key
            print(f"  AMBIGUOUS (left alone, review manually) {fecha} {condicion} ({resultado}):")
            for file_path in ambiguous.files:
                print(f"    - {file_path}")
        return

    config = ApiConfig.from_env()

    if args.command == "download-season":
        output_dir = Path(args.output_dir or season_directory_name(args.season)).resolve()
        stats = download_season_matches(config, season=args.season, output_dir=output_dir)
        print(stats)
        return


if __name__ == "__main__":
    main()
