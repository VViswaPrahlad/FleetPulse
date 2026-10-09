"""Render build-only fetch: trusted HTTPS archive + out-of-band expected hash.

No startup downloads. Do not execute until artifact publication is approved.
"""
import hashlib
import io
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from urllib.request import urlopen
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deploy.bundle import DEFAULT, FILES, artifact_path, verify
from src.runtime import local

MAX_BYTES = 16_000_000


def unpack(blob, expected, destination=DEFAULT):
    destination = local(destination)
    if not re.fullmatch('[0-9a-f]{64}', expected) or hashlib.sha256(blob).hexdigest() != expected:
        raise ValueError('Deployment archive hash mismatch')
    allowed = set(FILES) | {'bundle_manifest.json'}
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        members = archive.infolist()
        if (len(members) != len(allowed) or {item.filename for item in members} != allowed or
                sum(item.file_size for item in members) > MAX_BYTES):
            raise ValueError('Archive size/member allowlist mismatch')
        for item in members:
            if item.flag_bits & 1 or (item.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Encrypted/symlink archive members forbidden')
        if archive.testzip() is not None:
            raise ValueError('Archive CRC failure')
        for item in members:
            target = artifact_path(destination, item.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(item))
    verify(destination)


def main():
    url = os.environ.get('FLEETPULSE_BUNDLE_URL', '')
    expected = os.environ.get('FLEETPULSE_BUNDLE_SHA256', '')
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('Set a trusted HTTPS bundle URL')
    if not re.fullmatch('[0-9a-f]{64}', expected):
        raise ValueError('Set the independently verified archive SHA-256 before downloading')
    with urlopen(url, timeout=60) as response:
        if urlsplit(response.url).scheme != 'https':
            raise ValueError('Bundle redirected to insecure URL')
        blob = response.read(MAX_BYTES + 1)
    if len(blob) > MAX_BYTES:
        raise ValueError('Bundle archive exceeds size limit')
    unpack(blob, expected)
    print('Serving-only bundle verified and unpacked')


if __name__ == '__main__':
    main()
