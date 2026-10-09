"""Audit exact index blobs before committing; never print matched secret values."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = {'data','results','.venv','venv','env','__pycache__','.pytest_cache',
    '.vscode','.idea','.aws','.ssh','.codex','.agents','models','artifacts','outputs',
    'logs','spark-warehouse','metastore_db','build','dist','node_modules','coverage',
    'playwright-report','test-results','.npm'}
FORBIDDEN_SUFFIXES = {'.csv','.parquet','.7z','.zip','.rar','.tar','.gz','.bz2','.xz',
    '.db','.sqlite','.sqlite3','.duckdb','.wal','.pyc','.pyo','.log',
    '.pkl','.pickle','.joblib','.onnx','.pt','.pth','.h5','.keras','.bin','.model',
    '.safetensors','.ckpt','.npy','.npz','.pem','.key','.p12','.pfx','.tsbuildinfo'}
PATTERNS = {
    'private key': re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----'),
    'GitHub token': re.compile(rb'(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,})'),
    'AWS access key': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'credential URL': re.compile(rb'https?://[^\s/\x22\x27]+:[^\s/@\x22\x27]+@'),
    'literal credential assignment': re.compile(
        rb'(?im)^\s*(?:password|passwd|api_key|access_token|secret_key|client_secret)\s*[:=]\s*[\x22\x27][^\x22\x27\r\n]{8,}[\x22\x27]'),
}


def git(*args):
    return subprocess.run(['git','-C',str(ROOT),*args],check=True,capture_output=True).stdout


def audit():
    records = git('ls-files','--stage','-z').split(b'\0')
    files=[]
    failures=[]
    warnings=[]
    for record in filter(None,records):
        header,raw_path=record.split(b'\t',1)
        mode,oid,stage=header.decode().split()
        name=raw_path.decode('utf-8')
        path=Path(name)
        if stage!='0' or mode not in ('100644','100755'):
            failures.append({'file':name,'reason':'unmerged, symlink or nonregular index entry'})
        placeholder=path.name=='.gitkeep'
        if (any(p.lower() in FORBIDDEN_DIRS for p in path.parts) and not placeholder
            or path.suffix.lower() in FORBIDDEN_SUFFIXES
            or path.name.lower().startswith('.env')
            or path.name.lower()=='credentials.json'
            or path.name.lower().startswith('service-account')):
            failures.append({'file':name,'reason':'forbidden dataset/artifact/secret path'})
        blob=git('cat-file','blob',oid)
        files.append({'file':name,'bytes':len(blob)})
        if len(blob)>5_000_000:
            failures.append({'file':name,'reason':'blob exceeds 5 MB'})
        elif len(blob)>1_000_000:
            warnings.append({'file':name,'reason':'blob exceeds 1 MB; review'})
        for label,pattern in PATTERNS.items():
            for match in pattern.finditer(blob):
                failures.append({'file':name,'line':blob[:match.start()].count(b'\n')+1,'reason':label})
    result={'passed':not failures,'indexed_files':len(files),
        'total_blob_bytes':sum(f['bytes'] for f in files),
        'largest_files':sorted(files,key=lambda f:f['bytes'],reverse=True)[:10],
        'failures':failures,'warnings':warnings}
    print(json.dumps(result,indent=2))
    return result


if __name__=='__main__':
    sys.exit(0 if audit()['passed'] else 1)
