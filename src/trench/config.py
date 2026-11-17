"""Runtime settings. Everything is overridable by environment variable."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def lake_dir(self) -> Path:
        return self.data_dir / "lake"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(data_dir=Path(os.environ.get("TRENCH_DATA_DIR", "data")).resolve())
