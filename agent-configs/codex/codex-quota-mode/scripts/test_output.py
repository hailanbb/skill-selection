"""Regression for Windows locale-independent JSON output."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

with tempfile.TemporaryDirectory(prefix='省额度输出 ') as directory:
    result = subprocess.run(
        [sys.executable, '-B', str(Path(__file__).with_name('quota_mode.py')), 'status', '--codex-home', directory],
        capture_output=True, check=True,
    )
    result.stdout.decode('ascii')
    parsed = json.loads(result.stdout)
    assert '新会话' in parsed['reload']
    assert parsed['saved_mode'] == 'off'
    assert not Path(directory, 'quota-mode').exists()
    print('ASCII JSON transport and Chinese roundtrip passed; status is read-only.')
