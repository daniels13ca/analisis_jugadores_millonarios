from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .analytics import build_match_results, build_player_match_features, build_player_season_summary
from .config import ApiConfig, season_directory_name
from .consolidate import consolidate_dataset, read_existing_dataset
from .dedupe import archive_duplicate_matches
from .extract import download_season_matches
from .pipeline import run_refresh
from .validate import run_validations


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

    analytics_parser = subparsers.add_parser(
        "build-analytics",
        help="Build dashboard-ready tables: match results, player-match features, player season summary",
    )
    _add_base_path_argument(analytics_parser)
    analytics_parser.add_argument(
        "--dataset",
        default="dataset_millonarios_consolidado.csv",
        help="Path to the consolidated player-match CSV (from `consolidate`)",
    )
    analytics_parser.add_argument(
        "--output-dir",
        default="analytics",
        help="Where to write the derived CSVs",
    )

    validate_parser = subparsers.add_parser(
        "validate-analytics",
        help="Run sanity checks over the analytics tables (duplicate matches, negative stats, "
        "goal reconciliation, player name variants, ...)",
    )
    _add_base_path_argument(validate_parser)
    validate_parser.add_argument(
        "--dataset",
        default="dataset_millonarios_consolidado.csv",
        help="Path to the consolidated player-match CSV (from `consolidate`)",
    )

    refresh_parser = subparsers.add_parser(
        "refresh",
        help="Run the full pipeline in one shot: consolidate -> build-analytics -> validate-analytics "
        "(plus a read-only check for duplicate matches)",
    )
    _add_base_path_argument(refresh_parser)
    refresh_parser.add_argument(
        "--dataset",
        default="dataset_millonarios_consolidado.csv",
        help="Path to the consolidated player-match CSV",
    )
    refresh_parser.add_argument(
        "--analytics-dir",
        default="analytics",
        help="Where to write the derived analytics CSVs",
    )
    refresh_parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Passed through to `consolidate`: ignore the existing CSV and regenerate it from scratch",
    )
    refresh_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with a non-zero status if validate-analytics finds any ERROR",
    )

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Launch the Streamlit dashboard (requires: pip install -e '.[dashboard]')",
    )
    dashboard_parser.add_argument(
        "--analytics-dir",
        default="analytics",
        help="Folder with the tables from `build-analytics`",
    )
    dashboard_parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Port to run Streamlit on (defaults to Streamlit's own default, 8501)",
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

    if args.command == "build-analytics":
        base_path = Path(args.base_path).resolve()
        output_dir = Path(args.output_dir).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        match_results = build_match_results(base_path)
        player_match_df = read_existing_dataset(Path(args.dataset).resolve())
        player_features = build_player_match_features(player_match_df)
        season_summary = build_player_season_summary(player_features)

        match_results.to_csv(output_dir / "match_results.csv", index=False, encoding="utf-8-sig")
        player_features.to_csv(output_dir / "player_match_features.csv", index=False, encoding="utf-8-sig")
        season_summary.to_csv(output_dir / "player_season_summary.csv", index=False, encoding="utf-8-sig")

        print(
            f"match_results={len(match_results)} "
            f"player_match_features={len(player_features)} "
            f"player_season_summary={len(season_summary)} "
            f"-> {output_dir}"
        )
        return

    if args.command == "validate-analytics":
        report = run_validations(
            base_path=Path(args.base_path).resolve(),
            dataset_path=Path(args.dataset).resolve(),
        )
        print(f"errors={len(report.errors)} warnings={len(report.warnings)}")
        for issue in report.issues:
            print(f"  [{issue.severity.upper()}] {issue.check}: {issue.message}")
        if not report.ok:
            sys.exit(1)
        return

    if args.command == "refresh":
        result = run_refresh(
            base_path=Path(args.base_path).resolve(),
            dataset_path=Path(args.dataset).resolve(),
            analytics_output_dir=Path(args.analytics_dir).resolve(),
            rebuild=args.rebuild,
        )
        c = result.consolidation
        print(
            f"consolidate: scanned_files={c.scanned_files} new_rows={c.new_rows} "
            f"total_rows={len(c.dataframe)}"
        )
        print(
            f"analytics: match_results={result.match_results_rows} "
            f"player_match_features={result.player_match_features_rows} "
            f"player_season_summary={result.player_season_summary_rows}"
        )
        if result.duplicate_match_groups or result.ambiguous_match_groups:
            print(
                f"duplicate check: {result.duplicate_match_groups} grupo(s) duplicado(s) confirmados "
                f"(correr `dedupe-matches --apply`), {result.ambiguous_match_groups} ambiguo(s) "
                "(revisar manualmente)"
            )
        v = result.validation
        print(f"validate: errors={len(v.errors)} warnings={len(v.warnings)}")
        for issue in v.issues:
            print(f"  [{issue.severity.upper()}] {issue.check}: {issue.message}")
        if args.strict and not v.ok:
            sys.exit(1)
        return

    if args.command == "dashboard":
        import os
        import subprocess

        app_path = Path(__file__).resolve().parent / "dashboard" / "app.py"
        env = os.environ.copy()
        env["MILLOS_ANALYTICS_DIR"] = str(Path(args.analytics_dir).resolve())

        command = ["streamlit", "run", str(app_path)]
        if args.port is not None:
            command.extend(["--server.port", str(args.port)])

        try:
            subprocess.run(command, env=env, check=True)
        except FileNotFoundError:
            print(
                "No se encontro el comando `streamlit`. Instala el extra del dashboard con:\n"
                "  python -m pip install -e '.[dashboard]'"
            )
            sys.exit(1)
        return

    config = ApiConfig.from_env()

    if args.command == "download-season":
        output_dir = Path(args.output_dir or season_directory_name(args.season)).resolve()
        stats = download_season_matches(config, season=args.season, output_dir=output_dir)
        print(stats)
        return


if __name__ == "__main__":
    main()
