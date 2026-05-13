from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiConfig:
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
        api_key = os.getenv("FOOTBALL_API_KEY", "").strip()
        if not api_key:
            raise ValueError(
                "Missing FOOTBALL_API_KEY. Set it in your environment before downloading data."
            )

        team_id = int(os.getenv("MILLONARIOS_TEAM_ID", "1125"))
        base_url = os.getenv("FOOTBALL_API_BASE_URL", cls.base_url)
        api_host = os.getenv("FOOTBALL_API_HOST", cls.api_host)
        request_delay_seconds = float(os.getenv("FOOTBALL_API_DELAY_SECONDS", "1.0"))

        return cls(
            api_key=api_key,
            team_id=team_id,
            base_url=base_url,
            api_host=api_host,
            request_delay_seconds=request_delay_seconds,
        )
