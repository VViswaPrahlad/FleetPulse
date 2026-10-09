"""Small shared serving contracts; no ingestion or training imports."""
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TABLES = ('trip_analytics', 'vehicle_analytics', 'daily_fleet', 'monthly_fleet',
          'powertrain_fleet', 'fleet_overview', 'quality_metrics')


def local(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Artifact path must stay inside FleetPulse')
    return path


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()
