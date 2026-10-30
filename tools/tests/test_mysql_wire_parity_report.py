"""The MySQL-wire parity matrix in the docs matches the committed results."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / 'tools/cdeadmin_mysql_wire_parity_report.py'


def test_matrix_matches_committed_probe_results():
    result = subprocess.run([sys.executable, str(REPORT), '--check'],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
