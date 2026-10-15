"""Focused native event ABI diagnosis; never a backend release receipt."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import traceback
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.development.native import command


def child(runtime, database, evidence):
    import faulthandler
    faulthandler.dump_traceback_later(45, repeat=True)
    import firebird.driver as native
    filename = runtime / ('fbclient.dll' if os.name == 'nt' else 'lib/libfbclient.dylib'
                          if sys.platform == 'darwin' else 'lib/libfbclient.so.5.0.4')
    native.driver_config.fb_client_library.value = str(filename)
    api = native.get_api()
    spec = importlib.util.spec_from_file_location('owned_event_abi',
        ROOT / 'web/pgadmin/cdeadmin/providers/firebird/event_abi.py')
    adapter = importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
    result = {'schema': 'cdeadmin.firebird-event-abi-diagnostic.v1', 'passed': False,
              'release_qualified': False, 'failures': []}
    connection = None
    collectors = []
    try:
        adapter.install(api)
        connection = native.create_database(str(database), user='SYSDBA', charset='UTF8')
        event = 'SR_ABI_' + uuid.uuid4().hex[:12]
        names = [event + '_' + str(index) for index in range(14)] + ['Ω' * 63 + 'X']
        for group in ([names[0]], names):
            collector = adapter.event_collector(connection, group)
            collectors.append(collector)
            collector.begin()
            deadline = time.monotonic() + 10
            while collector._EventCollector__event_blocks[0]._EventBlock__first:
                if time.monotonic() > deadline:
                    raise TimeoutError('Native event baseline was not delivered')
                time.sleep(.05)
        with connection.cursor() as cursor:
            cursor.execute("EXECUTE BLOCK AS BEGIN POST_EVENT '" + names[0] +
                           "'; POST_EVENT '" + names[-1] + "'; END")
        connection.commit()
        for collector, group in zip(collectors, ([names[0]], names)):
            deadline = time.monotonic() + 10
            expected = {name: int(name in (names[0], names[-1])) for name in group}
            while collector.wait(.05) != expected:
                if time.monotonic() > deadline:
                    raise TimeoutError('Native committed event was not delivered')
        result['committed_count'] = 1
        result['concurrent_collector_sizes'] = [1, 15]
        result['maximum_utf8_event_name_bytes'] = len(names[-1].encode('utf-8'))
        result['passed'] = True
    except BaseException as error:
        # Only generated local fixtures are used; no password is acquired or
        # supplied anywhere in this process. Preserve the actual ABI exception.
        result['failures'].append({'type': type(error).__name__, 'detail': str(error)})
        traceback.print_exc()
    finally:
        try:
            for collector in reversed(collectors): collector.close()
            if collectors:
                result['event_buffers_released'] = all(item.buffers_released for item in collectors)
                assert result['event_buffers_released']
            if connection is not None: connection.drop_database()
            result['handles_released'] = True
        except BaseException as error:
            result['passed'] = False
            result['failures'].append({'cleanup_type': type(error).__name__, 'detail': str(error)})
        (evidence / 'receipt.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    return result


def run(runtime, evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='owned-abi-') as temporary:
        root = Path(temporary);owned = root/'runtime'
        shutil.copytree(runtime, owned)
        (owned/'lock').mkdir(exist_ok=True)
        (owned/'firebird.conf').write_text('Providers = Engine13\nSecurityDatabase = '+str(owned/'security5.fdb')+'\n', encoding='utf-8')
        (owned/'databases.conf').write_text('', encoding='utf-8')
        env = dict(os.environ, FIREBIRD=str(owned), FIREBIRD_LOCK=str(owned/'lock'), PYTHONFAULTHANDLER='1')
        for key in ('ISC_USER', 'ISC_PASSWORD', 'ISC_ROLE', 'ISC_DATABASE'):
            env.pop(key, None)
        command([sys.executable, __file__, '--runtime-root', owned, '--database', root/'owned.fdb',
                 '--evidence', evidence], env=env, log=evidence/'child.log', timeout=180)
    return json.loads((evidence/'receipt.json').read_text(encoding='utf-8'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--database', type=Path)
    args = parser.parse_args()
    result = (child(args.runtime_root, args.database, args.evidence) if args.database
              else run(args.runtime_root, args.evidence))
    print(json.dumps(result), flush=True)
    raise SystemExit(0 if result['passed'] else 1)
