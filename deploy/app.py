"""Fail-fast artifact-backed public app. Local src.api.main remains unchanged."""
import os
import re
from urllib.parse import urlsplit

from deploy.bundle import DEFAULT, verify
from src.api.main import create_app
from src.api.settings import Settings


def public_settings():
    origin = os.environ.get('FLEETPULSE_FRONTEND_ORIGIN', '')
    parsed = urlsplit(origin)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or
            parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment or
            parsed.netloc != parsed.hostname):
        raise ValueError('Set an exact HTTPS frontend origin; wildcards and ports are forbidden')
    if any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label)
           for label in parsed.hostname.split('.')):
        raise ValueError('Invalid frontend hostname')
    return Settings(root=DEFAULT, cors_origins=(f'https://{parsed.hostname}',),
                    cache_entries=16, analytics_memory_mb=32)


def create_public_app():
    verify(DEFAULT)
    app = create_app(public_settings())
    # Load once before accepting traffic; no scans, fitting, or artifact downloads.
    if not (app.state.analytics.ready() and app.state.model.ready() and app.state.evaluation.ready()):
        raise RuntimeError('Deployment artifacts are not ready')
    if app.state.model.identity() != app.state.evaluation.metrics().model_id:
        raise RuntimeError('Model/evaluation identities differ')
    from src.api.services.dashboard_reports import pipeline, cohorts
    pipeline(app.state.settings, app.state.analytics)
    cohorts(app.state.settings, 'test', 'powertrain')
    return app
