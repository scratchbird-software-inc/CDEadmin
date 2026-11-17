"""Create an owned ODS13.0 upgrade input with a separately supplied Firebird4 runtime.

Qualification bootstrap only: neither this runtime nor vendor executables are
shipped by ScratchRobin. The child uses the native client API, with no listener.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def worker(runtime, output):
    import firebird.driver as native
    library = runtime/'lib/libfbclient.so.4.0.5'
    native.driver_config.fb_client_library.value = str(library)
    config = native.driver_config.register_database('owned_legacy_fixture')
    config.database.value = str(output)
    config.config.value = 'Providers=Engine13'
    connection = native.create_database('owned_legacy_fixture', user='SYSDBA',
        password='fixture-only', charset='UTF8', overwrite=False)
    try:
        connection.execute_immediate('CREATE TABLE UPGRADE_DATA(ID INTEGER NOT NULL PRIMARY KEY, LABEL VARCHAR(50))')
        connection.commit()
        connection.execute_immediate("INSERT INTO UPGRADE_DATA VALUES(17,'preserved across upgrade')")
        connection.commit()
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT RDB$GET_CONTEXT('SYSTEM','ENGINE_VERSION'),MON$ODS_MAJOR,MON$ODS_MINOR FROM MON$DATABASE")
            observed = cursor.fetchone()
        finally: cursor.close(); connection.rollback()
        assert observed == ('4.0.5', 13, 0), observed
    finally: connection.close()
    proof = {'runtime_version': observed[0], 'ods': list(observed[1:]),
        'database_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
        'native_client_sha256': hashlib.sha256(library.read_bytes()).hexdigest(),
        'fixture_only': True, 'network_listener': False}
    output.with_suffix('.json').write_text(json.dumps(proof, indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--library-dir', type=Path, action='append', default=[],
                        help='Additional task-owned runtime dependency directory')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    runtime, output = args.runtime.resolve(), args.output.resolve()
    if args.worker:
        worker(runtime, output)
        return
    source = Path(__file__).resolve().parents[1]
    if sys.platform != 'linux' or output == source or source in output.parents:
        parser.error('Use Linux and a disposable output outside source')
    if output.exists() or output.with_suffix('.json').exists():
        parser.error('Fixture output must not exist; never overwrite a database')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='legacy-engine13-', dir=output.parent) as folder:
        stage = Path(folder)/'runtime'
        shutil.copytree(runtime, stage, symlinks=True)
        (stage/'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = '+str(stage/'security4.fdb')+'\n')
        (stage/'databases.conf').write_text('')
        env = dict(os.environ, FIREBIRD=str(stage), FIREBIRD_LOCK=str(Path(folder)/'lock'),
            LD_LIBRARY_PATH=':'.join(str(p.resolve()) for p in [stage/'lib', *args.library_dir]))
        subprocess.run([sys.executable, '-B', str(Path(__file__).resolve()), '--worker',
            '--runtime', str(stage), '--output', str(output)], env=env, check=True, timeout=60)


if __name__ == '__main__': main()
