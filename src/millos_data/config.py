from __future__ import annotations

import os
from typing import ClassVar
from dataclasses import dataclass
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Naming convention shared by extract.py (writes) and consolidate.py (reads)
# for a season's stats folder, e.g. "Millonarios_2025_Stats_Detalladas".
STATS_DIRECTORY_PREFIX = "Millonarios_"
STATS_DIRECTORY_SUFFIX = "Stats_Detalladas"


def season_directory_name(season: int) -> str:
    return f"{STATS_DIRECTORY_PREFIX}{season}_{STATS_DIRECTORY_SUFFIX}"


@dataclass(frozen=True)
class ApiConfig:
    expected_team_id: ClassVar[int] = 1125
    expected_team_code: ClassVar[str] = "MIL"
    expected_team_name: ClassVar[str] = "Millonarios FC"
    api_key: str
    team_id: int = 1125
    base_url: str = "https://v3.football.api-sports.io"
    api_host: str = "v3.football.api-sports.io"
    request_delay_seconds: float = 1.0

    @property
    def headers(self) -> dict[str, str]:
        return {
            "x-rapidapi-host": self.api_host,
            "x-rapidapi-key": self.api_key,
        }

    @classmethod
    def from_env(cls) -> "ApiConfig":
        # Walks up from the current working directory (and from the repo
        # root as a fallback) looking for a .env file; existing environment
        # variables always win over what's in the file.
        load_dotenv(find_dotenv(usecwd=True))
        load_dotenv(Path(__file__).resolve().parents[2] / ".env")

        api_key = os.getenv("FOOTBALL_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "Missing FOOTBALL_API_KEY. Define it in your environment or in a .env file before downloading data."
            )

        team_id = int(os.getenv("MILLONARIOS_TEAM_ID", "1125"))
        base_url = os.getenv("FOOTBALL_API_BASE_URL", cls.base_url)
        api_host = os.getenv("FOOTBALL_API_HOST", cls.api_host)
        request_delay_seconds = float(os.getenv("FOOTBALL_API_DELAY_SECONDS", "1.0"))

        if team_id != cls.expected_team_id:
            raise ValueError(
                f"Unsupported team_id={team_id}. This project only supports "
                f"{cls.expected_team_name} ({cls.expected_team_code}, team_id={cls.expected_team_id})."
            )

        return cls(
            api_key=api_key,
            team_id=team_id,
            base_url=base_url,
            api_host=api_host,
            request_delay_seconds=request_delay_seconds,
        )
