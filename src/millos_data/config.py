from __future__ import annotations

import os
from typing import ClassVar
from dataclasses import dataclass
from pathlib import Path


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def candidate_env_paths() -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()

    for base in (Path.cwd().resolve(), Path(__file__).resolve().parents[2]):
        for directory in (base, *base.parents):
            candidate = directory / ".env"
            if candidate not in seen:
                seen.add(candidate)
                paths.append(candidate)

    return paths


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
        for env_path in candidate_env_paths():
            load_env_file(env_path)

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
