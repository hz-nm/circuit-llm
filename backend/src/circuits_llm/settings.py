"""Application settings, read from ``CIRCUITS_LLM_*`` environment variables or a ``.env`` file."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from platformdirs import user_data_path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    return user_data_path("circuits-llm", appauthor=False)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CIRCUITS_LLM_", env_file=".env", extra="ignore")

    host: str = "127.0.0.1"
    port: Annotated[int, Field(ge=0, le=65_535)] = 8765
    data_dir: Path = Field(default_factory=_default_data_dir)
    ngspice_path: Path | None = None
    simulation_timeout_s: Annotated[float, Field(gt=0, le=300)] = 30.0
    simulate_during_design: bool = True
    # Plan each design first: pick component families and sketch the circuit (one extra
    # short LLM call; keeps the design prompt focused for weaker models).
    plan_before_design: bool = True
    open_browser: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    @property
    def database_path(self) -> Path:
        return self.data_dir / "circuits-llm.sqlite3"
