from dataclasses import dataclass
from pathlib import Path

from src.analytics.build_gold import ROOT


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    cache_entries: int = 32
    max_body_bytes: int = 65_536
    cors_origins: tuple[str,...] = ('http://localhost:5173','http://127.0.0.1:5173')

    def __post_init__(self):
        root=Path(self.root).resolve()
        if not root.is_relative_to(ROOT):
            raise ValueError('API resources must stay inside FleetPulse')
        object.__setattr__(self,'root',root)

    @property
    def gold(self):
        return self.root/'data/gold/ved'

    @property
    def evaluation(self):
        return self.root/'results/day6'

    @property
    def model(self):
        return self.root/'models/day6/hist_gradient_boosting.joblib'
