"""Serving-bundle integrity and public/local isolation regression tests."""
import hashlib
import io
import zipfile

import pytest

from deploy.app import public_settings
from deploy.bundle import FILES, artifact_path, encode, project, verify
from deploy.fetch_bundle import unpack
from src.api.settings import Settings
from src.runtime import ROOT, sha256


def test_local_settings_unchanged():
    assert Settings().cors_origins == ('http://localhost:5173', 'http://127.0.0.1:5173')
    old_positional = Settings(ROOT, 32, 65_536, ('https://fixture.invalid',))
    assert old_positional.cors_origins == ('https://fixture.invalid',)
    assert old_positional.analytics_memory_mb == 128


@pytest.mark.parametrize('origin', ['', '*', 'http://host', 'https://host/path',
                                   'https://user@host', 'https://host:443', 'https://*'])
def test_public_cors_requires_exact_https_origin(monkeypatch, origin):
    monkeypatch.setenv('FLEETPULSE_FRONTEND_ORIGIN', origin)
    with pytest.raises(ValueError):
        public_settings()


def test_public_origin_does_not_allow_localhost(monkeypatch):
    monkeypatch.setenv('FLEETPULSE_FRONTEND_ORIGIN', 'https://fleetpulse.onrender.com')
    assert public_settings().cors_origins == ('https://fleetpulse.onrender.com',)


def test_report_projection_preserves_values_excludes_training_payload():
    data = {'model_sha256': 'a' * 64, 'selection': {'selected_candidate': 3,
            'selected_parameters': {'learning_rate': .05}, 'random_state': 20261009,
            'candidate_scores': ['not needed']}, 'metrics': {'test': 10.886851},
            'strongest_baseline': 'last_observed_speed', 'improvement_vs_strongest_baseline': {},
            'vehicle_cluster_bootstrap': {}, 'input_sha256': {'private': 'not served'}}
    projected = project('results/day6/training_run.json', data)
    assert projected['metrics'] == data['metrics']
    assert 'input_sha256' not in projected and 'candidate_scores' not in projected['selection']


def test_bad_archive_hash_is_rejected_before_writes(tmp_path):
    with pytest.raises(ValueError, match='hash'):
        unpack(b'bad archive', '0' * 64, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_path_traversal_archive_rejected_before_writes(tmp_path):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('../outside', b'bad')
    blob = stream.getvalue()
    with pytest.raises(ValueError, match='allowlist'):
        unpack(blob, hashlib.sha256(blob).hexdigest(), tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_bundle_path_cannot_reach_original_artifacts(tmp_path):
    with pytest.raises(ValueError, match='escapes'):
        artifact_path(tmp_path, '../original.joblib')


def test_bundle_integrity_detects_changed_file(tmp_path):
    manifest = {'version': 1, 'files': {}}
    for name in FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'integrity fixture')
        manifest['files'][name] = {'bytes': path.stat().st_size, 'sha256': sha256(path)}
    (tmp_path / 'bundle_manifest.json').write_bytes(encode(manifest))
    verify(tmp_path)
    (tmp_path / FILES[0]).write_bytes(b'changed fixture')
    with pytest.raises(ValueError, match='integrity'):
        verify(tmp_path)


def test_missing_sha_rejected_before_network(monkeypatch):
    from deploy import fetch_bundle
    monkeypatch.setenv('FLEETPULSE_BUNDLE_URL', 'https://fixture.invalid/archive.zip')
    monkeypatch.delenv('FLEETPULSE_BUNDLE_SHA256', raising=False)
    monkeypatch.setattr(fetch_bundle, 'urlopen', lambda *args, **kwargs: pytest.fail('Network called'))
    with pytest.raises(ValueError, match='before downloading'):
        fetch_bundle.main()


def test_linux_wheel_tags_do_not_accept_newer_python_or_windows():
    from deploy.audit_runtime import compatible_wheel
    assert compatible_wheel('fixture-1.0-cp39-abi3-manylinux_2_17_x86_64.whl')
    assert compatible_wheel('fixture-1.0-py3-none-any.whl')
    assert not compatible_wheel('fixture-1.0-cp313-abi3-manylinux_2_17_x86_64.whl')
    assert not compatible_wheel('fixture-1.0-cp312-cp312-win_amd64.whl')
