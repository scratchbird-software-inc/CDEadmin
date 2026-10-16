"""Install the reproducible PostgreSQL parser in the current native environment."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request

from cdeadmin_build_postgresql_parser import build, SOURCE_SHA256, LIBRARY_SHA256, LIBRARY_COMMIT


def install(output):
    output = output.resolve()
    repository = Path(__file__).resolve().parents[1]
    if output == repository or repository in output.parents:
        raise ValueError('Parser installation evidence must be outside the repository')
    downloads = output.with_name(output.name + '-downloads')
    downloads.mkdir(parents=True, exist_ok=True)
    archives = []
    for name, url, expected in (
        ('pglast-8.5.tar.gz', 'https://files.pythonhosted.org/packages/62/b1/8f87ff97d3ebb6f6635f96e67f33863952ba73354890f77280dd371540c7/pglast-8.5.tar.gz', SOURCE_SHA256),
        ('libpg-query.tar.gz', 'https://codeload.github.com/pganalyze/libpg_query/tar.gz/' + LIBRARY_COMMIT, LIBRARY_SHA256),
    ):
        archive = downloads / name
        if not archive.exists():
            with urllib.request.urlopen(url, timeout=120) as source, archive.open('wb') as target:
                shutil.copyfileobj(source, target)
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
            raise ValueError('Native parser source hash differs: ' + name)
        archives.append(archive)
    wheel = build(*archives, output)
    with (output / 'install.log').open('wb') as log:
        subprocess.run([sys.executable, '-B', '-m', 'pip', 'install', '--ignore-installed', '--no-deps', str(wheel)],
            check=True, stdout=log, stderr=subprocess.STDOUT)
        subprocess.run([sys.executable, '-B', '-c',
            "from pglast import parser; assert parser.CDEADMIN_PARSE_OPTIONS_REVISION == 2; "
            "assert parser.get_postgresql_version() == (18, 6); "
            "parser.parse_sql_json(\"SELECT 'it\\\\'s'\", 96); "
            "parser.parse_plpgsql_json(\"DO $$BEGIN PERFORM 'it\\\\'s'; END$$\", 96, 96)"],
            check=True, stdout=log, stderr=subprocess.STDOUT)
    receipt = json.loads((output / 'build.json').read_text())
    receipt['installation_verified'] = True
    (output / 'installation.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    install(parser.parse_args().output)
