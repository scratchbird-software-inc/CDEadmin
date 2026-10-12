#!/usr/bin/env python3
"""Real browser/file-writer qualification of the unchanged BLOB pump module.

Uses origin-private files, not the user picker or a native database. Those
integration layers require separate evidence. All browser state is temporary.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading

from selenium import webdriver
from selenium.webdriver.chrome.service import Service


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / 'web/pgadmin/static/js/Dialogs/firebirdBlobFile.js'
PAGE = b'''<!doctype html><title>Owned Firebird file pump qualification</title>
<script type="importmap">{"imports":{"sources/gettext":"/gettext.js"}}</script>
<script type="module">
import {saveFirebirdBlob} from '/pump.js';
window.saveFirebirdBlob = saveFirebirdBlob;
</script>'''
SCRIPT = '''
const done = arguments[0];
(async () => {
  const root = await navigator.storage.getDirectory();
  const file = await root.getFileHandle('owned.bin', {create: true});
  const size = 3600000;
  let largestWrite = 0, writing = false, calls = 0;
  const native = await file.createWritable({keepExistingData: false});
  const writer = {
    async write(data) {
      writing = true;
      largestWrite = Math.max(largestWrite, data.length);
      await native.write(data);
      writing = false;
    },
    close: () => native.close(), abort: () => native.abort(),
  };
  const count = await window.saveFirebirdBlob({writer, reference: 'owned',
    stopped: () => false, progress: () => {},
    read: async offset => {
      if (writing) throw new Error('Read overlapped write');
      calls++;
      const end = Math.min(size, offset + 65536);
      let binary = '';
      for (let n = offset; n < end; n++) {
        binary += String.fromCharCode(n % 251);
      }
      return {blob_reference: 'owned', offset, next_offset: end,
        data: btoa(binary), encoding: 'base64', complete: end === size};
    },
  });
  // Full materialization is only the test oracle, outside the pump.
  const digest = await crypto.subtle.digest('SHA-256',
    await (await file.getFile()).arrayBuffer());
  const sha256 = [...new Uint8Array(digest)]
    .map(n => n.toString(16).padStart(2, '0')).join('');
  const reset = await file.createWritable();
  await reset.write('retained original');
  await reset.close();
  let stop = false, stoppedError;
  const abortWriter = await file.createWritable({keepExistingData: false});
  try {
    await window.saveFirebirdBlob({writer: abortWriter, reference: 'owned',
      stopped: () => stop, progress: () => {}, read: async offset => {
        if (offset > 0) stop = true;
        return {blob_reference: 'owned', offset, next_offset: offset + 1,
          data: 'eA==', encoding: 'base64', complete: false};
      },
    });
  } catch (error) { stoppedError = error.message; }
  const retained = await (await file.getFile()).text();
  await root.removeEntry('owned.bin');
  return {count, sha256, largestWrite, calls, stoppedError,
    aborted_file_preserved: retained === 'retained original'};
})().then(result => done({result}))
  .catch(error => done({error: error.message}));
'''


def run(chrome, chromedriver, evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    source = MODULE.read_bytes()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            routes = {'/': ('text/html', PAGE),
                      '/pump.js': ('text/javascript', source),
                      '/gettext.js': ('text/javascript',
                                      b'export default value => value;')}
            if self.path not in routes:
                self.send_error(404)
                return
            kind, body = routes[self.path]
            self.send_response(200)
            self.send_header('Content-Type', kind)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix='fb-file-') as profile:
            options = webdriver.ChromeOptions()
            options.binary_location = str(chrome)
            for flag in ('--headless=new', '--no-sandbox',
                         '--disable-dev-shm-usage',
                         '--user-data-dir=' + profile):
                options.add_argument(flag)
            with webdriver.Chrome(service=Service(str(chromedriver)),
                                  options=options) as browser:
                browser.get(f'http://127.0.0.1:{server.server_port}/')
                browser.set_script_timeout(60)
                result = browser.execute_async_script(SCRIPT)
                result['browser'] = browser.capabilities['browserVersion']
                result['module_sha256'] = hashlib.sha256(source).hexdigest()
                (evidence / 'result.json').write_text(
                    json.dumps(result, indent=2) + '\n')
                assert 'error' not in result, result
                observed = result['result']
                expected = hashlib.sha256(bytes(
                    n % 251 for n in range(3600000))).hexdigest()
                assert observed['count'] == 3600000
                assert observed['sha256'] == expected
                assert observed['largestWrite'] == 65536
                assert observed['calls'] == 55
                assert observed['stoppedError'] == 'BLOB save stopped.'
                assert observed['aborted_file_preserved']
    finally:
        server.shutdown()
        worker.join(timeout=5)
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chrome', type=Path, required=True)
    parser.add_argument('--chromedriver', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.chrome, args.chromedriver, args.evidence_root)
