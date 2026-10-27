"""Owned MySQL9.7 application/SSH/native configuration diagnostics qualification.

Use --prepare-fixture to build an owned MySQL image with Python/OpenSSH and a
disposable test key. Otherwise supply an equivalent image and its private key.
No existing database or host is modified by this qualification.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'web'), str(ROOT / 'tools')]


def prepare_fixture(output, image):
    directory = output / 'fixture-build'; directory.mkdir()
    key = directory / 'private-key'
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(key)], check=True)
    (directory / 'authorized_keys').write_bytes(key.with_suffix('.pub').read_bytes())
    (directory / 'start.sh').write_text('#!/bin/bash\nset -e\n/usr/sbin/sshd -D >/tmp/scratchrobin-sshd.log 2>&1 &\nexec /usr/local/bin/docker-entrypoint.sh "$@"\n')
    (directory / 'Dockerfile').write_text('''FROM mysql:9.7.0
USER root
RUN microdnf install -y python3 openssh-server && microdnf clean all && ssh-keygen -A && mkdir -p /run/sshd /root/.ssh && chmod 700 /root/.ssh
COPY authorized_keys /root/.ssh/authorized_keys
RUN chmod 600 /root/.ssh/authorized_keys && printf '%s\\n' 'PermitRootLogin prohibit-password' 'PasswordAuthentication no' 'UsePAM no' 'PrintMotd no' > /etc/ssh/sshd_config.d/scratchrobin-fixture.conf
COPY start.sh /opt/scratchrobin-fixture-start.sh
ENTRYPOINT ["/bin/bash", "/opt/scratchrobin-fixture-start.sh"]
CMD ["mysqld"]
''')
    # Build context contains only the public key and recipe, never the key used
    # by the application. The private key stays outside that context.
    context = directory / 'context'; context.mkdir()
    for name in ('authorized_keys', 'Dockerfile', 'start.sh'):
        (context / name).write_bytes((directory / name).read_bytes())
    with (output / 'fixture-build.log').open('w') as log:
        subprocess.run(['docker', 'build', '-t', image, str(context)], stdout=log, stderr=subprocess.STDOUT, check=True)
    return key


def qualify(output, *, fixture_image, private_key=None, prepare=False, use_c=False, browser_binary=None, driver_binary=None, configuration_deployment=False,initialization=False):
    output = Path(output).resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError('Keep disposable native fixtures outside source')
    output.mkdir(parents=True, exist_ok=False)
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    app = setup_application(output)
    from flask import url_for
    from pgadmin.model import db, User, ServerGroup, Server
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from pgadmin.cdeadmin.workspace import service_for_app
    from pgadmin.cdeadmin.providers.mysql_family import mysql_host_transport as native
    from cdeadmin_mysql_family_object_live_orchestrator import _run, _wait_until_ready, _root_connection, _published_port, _image_identity
    client = app.test_client(); service = service_for_app(app)
    proof = {'complete': False, 'history_testing': 'not run', 'mysql_interface': 'c' if use_c else 'pure', 'checks': [], 'source_sha256': {}}
    for name in ('tools/cdeadmin_mysql_host_qualification.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_host_transport.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_host_worker.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_host_services.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_host_configuration.py',
                 'tools/mysql_host_configuration_qualification.py',
                 'tools/mysql_host_initialization_qualification.py',
                 'web/pgadmin/cdeadmin/providers/mysql_family/mysql_host_initialization.py',
                 'web/pgadmin/cdeadmin/workspace/mysql_host_service.py',
                 'web/pgadmin/cdeadmin/workspace/service.py',
                 'web/pgadmin/cdeadmin/context_menu.py',
                 'web/pgadmin/browser/server_groups/servers/__init__.py',
                 'web/pgadmin/browser/server_groups/servers/static/js/server.js',
                 'web/pgadmin/browser/static/js/ProviderContextMenu.js',
                 'web/pgadmin/static/js/Dialogs/index.jsx',
                 'web/pgadmin/static/js/Dialogs/MySQLHost.jsx'):
        proof['source_sha256'][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    containers = []; root = None
    try:
        key = prepare_fixture(output, fixture_image) if prepare else Path(private_key).resolve(strict=True)
        credential = {'private_key': key.read_text()}
        proof['fixture_image'] = _image_identity(fixture_image)
        hostname = 'sr-mysql-host-' + secrets.token_hex(6)
        def start(label):
            name = hostname + '-' + label
            _run(['docker', 'run', '-d', '--rm', '--name', name, '--hostname', hostname, *(['--cap-add=SYS_ADMIN'] if configuration_deployment else []),
                  '-e', 'MYSQL_ALLOW_EMPTY_PASSWORD=yes', '-p', '127.0.0.1::3306', '-p', '127.0.0.1::22',
                  fixture_image, 'mysqld', '--server-id=101', '--gtid-mode=ON', '--enforce-gtid-consistency=ON', '--log-bin=sr-host'])
            containers.append(name)
            port = _wait_until_ready('mysql', name, 300)
            ssh = _published_port(_run(['docker', 'port', name, '22/tcp']).stdout)
            host_key = _run(['docker', 'exec', name, 'cat', '/etc/ssh/ssh_host_ed25519_key.pub']).stdout.strip()
            return name, port, ssh, host_key
        name, port, ssh, host_key = start('source')
        _wrong_name, _wrong_port, wrong_ssh, _wrong_key = start('wrong-instance')
        root = _root_connection('mysql', port); root.autocommit = True
        password = 'native-host-' + secrets.token_urlsafe(24)
        with root.cursor() as query:
            query.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
            query.execute('CREATE DATABASE sr_host_diagnostic CHARACTER SET utf8mb4')
            query.execute('CREATE TABLE sr_host_diagnostic.t(id BIGINT PRIMARY KEY,body TEXT,payload LONGBLOB)')
            query.execute('INSERT INTO sr_host_diagnostic.t VALUES(%s,%s,%s)', (9007199254740993, 'native 😀 雪', b'\x00\xff'))
        with app.test_request_context('/'):
            uid = User.query.first().id
            group = ServerGroup.query.filter_by(user_id=uid).order_by(ServerGroup.id).first()
            app.blueprints['NODE-engine_type'].connector_visibility['mysql'].set(True, user_id=uid)
            def register(label,pending=False):
                item = Server(user_id=uid, servergroup_id=group.id, name=label, host='127.0.0.1',
                              port=port, username='root', maintenance_db=None, save_password=0)
                item._cde_endpoint_registration = registration_profile('mysql-native')
                item._cde_endpoint_route_configuration = {'host': 'initialization-pending.invalid' if pending else '127.0.0.1', 'port': port, 'user': 'root',
                    'use_pure': not use_c, 'credential_kinds': ['database_password']}
                db.session.add(item); db.session.commit()
                return item.id, url_for('NODE-server.verify_endpoint_id', gid=group.id, sid=item.id), url_for('NODE-server.cde_workspace_id', gid=group.id, sid=item.id)
            sid, verify, url = register('Owned MySQL host diagnostics')
            _other, other_verify, other_url = register('Independent MySQL registration')
            pending_sid,_pending_verify,pending_url=register('New native MySQL initialization',pending=True)
        with client.session_transaction() as session:
            session['_user_id'] = str(uid); session['_fresh'] = True
        assert client.post(verify, json={'password': password}).get_json()['success']
        assert client.post(other_verify, json={'password': password}).get_json()['success']
        def http(action, request, *, target=None, refused=False):
            response = client.post(target or url, json={'action': 'mysql_host_' + action, 'request': request})
            value = response.get_json()
            if refused:
                assert response.status_code == 400, value
                return value
            if response.status_code != 200 or not value.get('success'):
                (output / 'http-failure.json').write_text(json.dumps(value, indent=2) + '\n')
                raise AssertionError('Native database host HTTP failed: ' + action)
            return value['data']
        def review(selected, credentials=credential, **kwargs):
            return http('review', {'options': selected, 'credentials': credentials}, **kwargs)
        def admitted(value, credentials=credential):
            return {**{field: value[field] for field in ('job_id', 'review_digest')}, 'confirmed': True, 'credentials': credentials}
        def wait(value, state='native_process_returned'):
            deadline = time.monotonic() + 90
            while value['state'] in {'dispatching', 'active', 'cancel_requested'}:
                if time.monotonic() > deadline: raise TimeoutError('Owned native host diagnostic deadline')
                time.sleep(.05); value = http('status', {'job_id': value['job_id']})
            assert value['state'] == state, value
            return value
        selected = {'connection': {'host': '127.0.0.1', 'port': ssh, 'username': 'root', 'host_key': host_key,
                    'authentication': 'private_key', 'platform': 'posix', 'python': 'python3'},
                    'executable': '/usr/sbin/mysqld', 'configuration_file': None,
                    'workspace': '/tmp/scratchrobin-native-host', 'timeout_seconds': 60}
        binding = http('catalog', {})
        peer = http('peer', {'host': '127.0.0.1', 'port': ssh})
        assert peer['openssh_key'] == ' '.join(host_key.split()[:2]) and not peer['authenticated'] and not peer['remote_command_executed']
        proof['checks'].append('authenticated-application-native-source-binding-and-unauthenticated-SSH-peer-inspection')
        import paramiko
        wrong = deepcopy(selected); fake = paramiko.RSAKey.generate(2048)
        wrong['connection']['host_key'] = fake.get_name() + ' ' + fake.get_base64()
        review(wrong, refused=True)
        wrong = deepcopy(selected); wrong['connection']['port'] = wrong_ssh
        review(wrong, refused=True)
        proof['checks'].append('wrong-SSH-host-key-and-same-hostname-different-native-instance-refused')
        def config(content):
            subprocess.run(['docker', 'exec', '-i', name, 'python3', '-c',
                            'import sys;open("/tmp/selected.cnf","wb").write(sys.stdin.buffer.read())'],
                           input=content.encode('utf8'), check=True, capture_output=True)
        config('[mysqld]\nmax_connections=151\n')
        configured = {**selected, 'configuration_file': '/tmp/selected.cnf'}
        stale = review(configured)
        http('start', {**admitted(stale), 'confirmed': False}, refused=True)
        config('[mysqld]\nmax_connections=152\n')
        http('start', admitted(stale), refused=True)
        assert http('status', {'job_id': stale['job_id']})['state'] == 'reviewed'
        assert http('cancel', {'job_id': stale['job_id']})['state'] == 'cancelled'
        proof['checks'].append('explicit-confirmation-and-changed-native-root-configuration-refuse-before-admission')
        checked = wait(http('start', admitted(review(configured))))
        observed = checked['remote_receipt']
        assert checked['ssh_reply_observed'] and observed['result']['return_code'] == 0
        assert observed['result']['native_process_termination_observed'] and observed['result']['streams_closed']
        assert checked['remote_observation']['host']['server_uuid'] == binding['state']['host_binding']['server_uuid']
        assert checked['execution_host']['hostname'] == hostname
        assert checked['remote_observation']['host']['python_version'][:2] == [3, 9]
        assert http('start', admitted(checked, {}))['remote_receipt'] == observed
        http('status', {'job_id': checked['job_id']}, target=other_url, refused=True)
        assert http('list', {}, target=other_url)['total'] == 0
        proof['checks'].append('actual-native-mysqld-check-with-bounded-output-private-durable-receipt-no-replay-and-registration-isolation')
        config('[mysqld]\nunknown_scratchrobin_native_setting=1\n')
        invalid = wait(http('start', admitted(review(configured))))
        assert invalid['ssh_reply_observed'] and invalid['remote_receipt']['result']['return_code'] != 0
        proof['checks'].append('actual-native-configuration-error-is-a-returned-process-with-nonzero-exit')
        def remote(script):
            return _run(['docker', 'exec', name, 'python3', '-c', script])
        remote('from pathlib import Path;p=Path("/tmp/srconfig");p.mkdir();(p/"parts").mkdir();'
            '(p/"parts/a.cnf").write_text("[mysqld]\\nmax_connections=153\\n");'
            '(p/"parts/z.cnf").write_text("[mysqld]\\nmax_connections=154\\n");'
            '(p/"parts/ignored.CNF").write_text("[mysqld]\\nunknown_uppercase_extension=1\\n");'
            '(p/"parts/world.cnf").write_text("[mysqld]\\nunknown_world_writable=1\\n");(p/"parts/world.cnf").chmod(0o666);'
            '(p/"chain.cnf").write_text("!include srconfig/leaf.cnf\\n!include ~/srconfig/home.cnf\\n");'
            '(p/"leaf.cnf").write_text("[mysqld]\\nmax_connections=155\\n");'
            '(p/"home.cnf").write_text("[mysqld]\\nmax_connections=156\\n");'
            '(p/"linked.cnf").symlink_to(p/"leaf.cnf")')
        config('!includedir /tmp/srconfig/parts\n!include /tmp/srconfig/chain.cnf\n!include /tmp/srconfig/linked.cnf\n[mysqld]\n')
        graph_review = review(configured)
        graph = graph_review['remote_observation']['configuration']['graph']
        assert graph_review['remote_observation']['included_configuration_files_attested']
        assert graph['working_directory'] == '/tmp' and graph['home_directory'] == '/tmp'
        assert not graph['atomic_native_file_read_snapshot']
        assert any(row.get('selected_names') == ['a.cnf', 'world.cnf', 'z.cnf'] for row in graph['entries'])
        assert any(row['state'] == 'ignored_world_writable' for row in graph['entries'])
        graph_result = wait(http('start', admitted(graph_review)))
        assert graph_result['remote_receipt']['result']['return_code'] == 0
        assert graph_result['remote_receipt']['configuration_after_process']['matches_review']
        proof['checks'].append('actual-native-nested-relative-and-home-includes-directory-order-case-and-world-writable-ignore')
        for changed, script in (
            ('included-bytes', 'from pathlib import Path;Path("/tmp/srconfig/leaf.cnf").write_text("[mysqld]\\nmax_connections=157\\n")'),
            ('new-directory-member', 'from pathlib import Path;Path("/tmp/srconfig/parts/new.cnf").write_text("[mysqld]\\n")'),
            ('removed-directory-member', 'from pathlib import Path;Path("/tmp/srconfig/parts/new.cnf").unlink()'),
            ('symlink-target', 'from pathlib import Path;p=Path("/tmp/srconfig/linked.cnf");p.unlink();p.symlink_to("/tmp/srconfig/home.cnf")'),
            ('native-ignore-mode', 'from pathlib import Path;Path("/tmp/srconfig/parts/world.cnf").chmod(0o600)'),
        ):
            stale = review(configured); remote(script)
            http('start', admitted(stale), refused=True)
            assert http('status', {'job_id': stale['job_id']})['state'] == 'reviewed'
            http('cancel', {'job_id': stale['job_id']})
            proof['checks'].append('configuration-graph-refuses-changed-'+changed+'-before-admission')
        # Once its native ignore bit is removed, the same included unknown
        # option must be rejected by the actual mysqld parser.
        invalid_include = wait(http('start', admitted(review(configured))))
        assert invalid_include['remote_receipt']['result']['return_code'] != 0
        assert invalid_include['remote_receipt']['configuration_after_process']['matches_review']
        proof['checks'].append('actual-native-included-option-error-remains-native-process-result')
        remote('from pathlib import Path;Path("/tmp/srconfig/parts/world.cnf").chmod(0o666)')
        config('!include /tmp/srconfig/cycle.cnf\n[mysqld]\n')
        remote('from pathlib import Path;Path("/tmp/srconfig/cycle.cnf").write_text("!include /tmp/srconfig/cycle.cnf\\n[mysqld]\\n")')
        cycle = review(configured); cycle_entries = cycle['remote_observation']['configuration']['graph']['entries']
        assert len(cycle_entries) == 11 and cycle_entries[-1]['depth'] == 10
        assert cycle_entries[-1]['directives_skipped_at_native_depth_limit'] == [1]
        cycled = wait(http('start', admitted(cycle)))
        assert cycled['remote_receipt']['result']['return_code'] == 0
        proof['checks'].append('actual-native-tenth-recursion-limit-without-infinite-graph-traversal')
        remote('from pathlib import Path;p=Path("/tmp/srconfig");(p/"alias").symlink_to("/tmp",target_is_directory=True);'
            'Path("/tmp/~").mkdir();Path("/tmp/~/home.cnf").write_text("[mysqld]\\nunknown_literal_tilde=1\\n");'
            'Path("/tmp/home.cnf").write_text("[mysqld]\\nmax_connections=158\\n")')
        config('!include /tmp/srconfig/alias/../home.cnf\n!include /missing/~/home.cnf\n!includedir ~\n[mysqld]\n')
        paths = review(configured)
        path_entries = paths['remote_observation']['configuration']['graph']['entries']
        assert path_entries[1]['path'] == '/tmp/srconfig/home.cnf'
        assert path_entries[2]['path'] == '/tmp/home.cnf'
        assert path_entries[3]['path'] == '/tmp/~' and path_entries[4]['path'] == '/tmp/home.cnf'
        normalized = wait(http('start', admitted(paths)))
        assert normalized['remote_receipt']['result']['return_code'] == 0
        proof['checks'].append('actual-native-file-path-normalization-before-symlinks-and-distinct-includedir-tilde-handling')
        original = native.Transport.request; calls = []
        def lost(transport, request, *args, **kwargs):
            value = original(transport, request, *args, **kwargs)
            if request['action'] == 'validate_config':
                calls.append(value)
                raise OSError('Owned suppressed SSH reply after actual native process completion')
            return value
        uncertain_review = review(selected)
        native.Transport.request = lost
        try: uncertain = wait(http('start', admitted(uncertain_review)), 'unknown')
        finally: native.Transport.request = original
        assert len(calls) == 1 and calls[0]['result']['return_code'] == 0 and not uncertain.get('ssh_reply_observed')
        reconciled = http('reconcile', {'job_id': uncertain['job_id'], 'credentials': credential})
        assert reconciled['state'] == 'unknown' and not reconciled.get('ssh_reply_observed')
        assert reconciled['reconciliation']['remote_receipt'] == calls[0]
        assert reconciled['reconciliation']['original_ssh_acknowledgement_unchanged']
        assert http('start', admitted(uncertain, {}))['state'] == 'unknown' and len(calls) == 1
        proof['checks'].append('actual-completed-native-command-with-suppressed-SSH-reply-reconciles-without-changing-original-unknown-or-replaying')
        _run(['docker', 'exec', name, 'python3', '-c',
              'from pathlib import Path;import sys;Path(sys.argv[1]).unlink()',
              selected['workspace'] + '/' + uncertain['job_id'] + '/result.json'])
        missing = http('reconcile', {'job_id': uncertain['job_id'], 'credentials': credential})
        absent = missing['reconciliation']['remote_receipt']
        assert missing['state'] == 'unknown' and not missing.get('ssh_reply_observed')
        assert absent['state'] == 'unknown' and not absent['remote_receipt_available']
        assert absent['input_digest'] == uncertain['review_digest'] and len(calls) == 1
        proof['checks'].append('missing-remote-journal-is-an-explicit-unknown-observation-without-command-replay')
        # The same native key is reopened using its encrypted OpenSSH encoding.
        from cryptography.hazmat.primitives import serialization
        phrase = 'key-passphrase-' + secrets.token_urlsafe(20)
        opened = serialization.load_ssh_private_key(key.read_bytes(), password=None)
        encrypted = opened.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH,
                                         serialization.BestAvailableEncryption(phrase.encode('utf8'))).decode('ascii')
        encrypted_review = review(selected, {'private_key': encrypted, 'private_key_password': phrase})
        http('cancel', {'job_id': encrypted_review['job_id']})
        proof['checks'].append('actual-encrypted-private-key-authentication-with-separate-passphrase')
        # Enable password authentication only in this disposable fixture.
        ssh_password = 'ssh-native-' + secrets.token_urlsafe(24)
        subprocess.run(['docker', 'exec', '-i', name, 'chpasswd'], input=('root:' + ssh_password + '\n').encode(), check=True, capture_output=True)
        script = 'from pathlib import Path;import os,signal;Path("/etc/ssh/sshd_config.d/scratchrobin-fixture.conf").write_text("PermitRootLogin yes\\nPasswordAuthentication yes\\nUsePAM no\\nPrintMotd no\\n");os.kill(int(Path("/var/run/sshd.pid").read_text()),signal.SIGHUP)'
        _run(['docker', 'exec', name, 'python3', '-c', script])
        password_options = deepcopy(selected); password_options['connection']['authentication'] = 'password'
        password_review = review(password_options, {'password': ssh_password})
        http('cancel', {'job_id': password_review['job_id']})
        proof['checks'].append('actual-pinned-host-SSH-password-authentication')
        if configuration_deployment:
            from mysql_host_configuration_qualification import qualify as install_configuration
            proof['checks'].extend(install_configuration(review,http,admitted,wait,config,remote,root,output,selected))
        if initialization:
            from mysql_host_initialization_qualification import qualify as initialize
            proof['checks'].extend(initialize(http,admitted,remote,output,selected,credential,pending_url))
        if browser_binary:
            config('[mysqld]\nmax_connections=151\n')
            proof['browser'] = browser(app, output, sid, selected, key, browser_binary, driver_binary,configuration_deployment,initialization)
            proof['checks'].append('built-application-context-menu-review-confirm-native-process-and-reconciliation-with-zero-browser-errors')
        with root.cursor() as query:
            query.execute('SELECT CAST(id AS CHAR),body,HEX(payload) FROM sr_host_diagnostic.t')
            assert query.fetchall() == [('9007199254740993', 'native 😀 雪', '00FF')]
        root.close(); root = None
        assert service.mysql_host_jobs.close()
        for path in Path(str(service.mysql_host_jobs.path) + '.jobs').glob('*.json'):
            data = path.read_text()
            assert key.read_text() not in data and encrypted not in data and phrase not in data and ssh_password not in data
        _run(['docker', 'stop', name]); containers.remove(name)
        assert http('status', {'job_id': uncertain['job_id']})['state'] == 'unknown'
        assert http('list', {})['total'] >= 6
        proof['checks'].append('exact-wide-Unicode-BLOB-source-data-preserved-credentials-absent-from-receipts-and-offline-local-status')
        proof.update(complete=True, native_binding=binding, native_program=checked['remote_observation']['program'])
        (output / 'native-result.json').write_text(json.dumps(checked, indent=2) + '\n')
        (output / 'unknown-reconciled.json').write_text(json.dumps(reconciled, indent=2) + '\n')
    finally:
        if root is not None: root.close()
        jobs = getattr(service, 'mysql_host_jobs', None)
        if jobs is not None: proof['owned_jobs_stopped'] = jobs.close()
        stopped = []
        for name in reversed(containers):
            logs = _run(['docker', 'logs', name], check=False)
            (output / (name + '.log')).write_text(logs.stdout + logs.stderr)
            stopped.append(_run(['docker', 'stop', name], check=False).returncode == 0)
        proof['owned_servers_stopped'] = all(stopped)
        (output / 'summary.json').write_text(json.dumps(proof, indent=2) + '\n')
    return proof


def browser(app, output, sid, selected, key, binary, driver_binary,configuration_deployment=False,initialization=False):
    import threading
    from werkzeug.serving import make_server
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    from selenium.webdriver.common.by import By
    from selenium.webdriver import ActionChains
    from selenium.webdriver.support.ui import WebDriverWait
    from cdeadmin_ui_evidence import ensure_data_explorer, expand
    http = make_server('127.0.0.1', 0, app, threaded=True)
    thread = threading.Thread(target=http.serve_forever, daemon=True); thread.start(); driver = None
    try:
        options = webdriver.ChromeOptions(); options.binary_location = binary
        for flag in ('--headless=new', '--no-sandbox', '--disable-dev-shm-usage', '--window-size=1800,1400'):
            options.add_argument(flag)
        options.add_argument('--user-data-dir=' + str(output / 'browser-profile'))
        options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
        driver = webdriver.Chrome(options=options, service=Service(driver_binary))
        driver.get('http://127.0.0.1:' + str(http.server_port) + '/browser/')
        wait = WebDriverWait(driver, 90); ensure_data_explorer(wait); expand(wait, 'Connectors'); expand(wait, 'MySQL')
        def target(browser):
            return next((node for node in browser.find_elements(By.CSS_SELECTOR, '.file-name') if node.is_displayed() and browser.execute_script(
                'const t=window.pgAdmin.Browser.tree;const d=t.itemData(t.itemFrom(arguments[0].closest(".file-entry")));return d?._type==="server" && String(d._id ?? d.id)===String(arguments[1]);', node, sid)), None)
        ActionChains(driver).context_click(wait.until(target)).perform()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if node.is_displayed() and node.text.strip() == 'Maintenance'), None)).click()
        wait.until(lambda browser: next((node for node in browser.find_elements(By.CSS_SELECTOR, '[role="menuitem"]') if node.is_displayed() and 'MySQL database-host administration' in node.text), None)).click()
        def click(label):
            def attempt(browser):
                for node in browser.find_elements(By.TAG_NAME, 'button'):
                    if node.is_enabled() and node.get_attribute('textContent').strip() == label:
                        browser.execute_script('arguments[0].scrollIntoView({block:"center"});', node)
                        if node.is_displayed(): node.click(); return True
                return False
            wait.until(attempt)
        def field(label, value):
            from selenium.webdriver.common.keys import Keys
            node = wait.until(lambda browser: browser.find_element(By.XPATH, '//label[normalize-space()="'+label+'"]'))
            control = driver.find_element(By.ID, node.get_attribute('for'))
            control.click(); control.send_keys(Keys.CONTROL, 'a')
            control.send_keys(Keys.BACKSPACE if str(value)=='' else str(value))
            wait.until(lambda _browser: control.get_attribute('value') == str(value))
        field('Database SSH host', selected['connection']['host']); field('SSH port', selected['connection']['port'])
        field('SSH username', 'root'); field('Expected OpenSSH public host key', selected['connection']['host_key'])
        label = driver.find_element(By.XPATH, '//label[normalize-space()="SSH authentication"]')
        driver.find_element(By.ID, label.get_attribute('for')).click()
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, 'li[data-value="private_key"]')).click()
        driver.find_element(By.CSS_SELECTOR, 'input[type="file"]').send_keys(str(key))
        field('Native mysqld executable', selected['executable'])
        field('Private workspace on SSH host', selected['workspace'])
        click('Review native host configuration check')
        wait.until(lambda browser: browser.find_element(By.CSS_SELECTOR, '[aria-label="Native host diagnostic review"]'))
        checkbox = driver.find_element(By.XPATH, '//label[contains(normalize-space(),"Authorize the reviewed native mysqld")]//input')
        driver.execute_script('arguments[0].click()', checkbox)
        click('Confirm native host configuration check')
        wait.until(lambda browser: any('native_process_returned' in node.get_attribute('textContent') for node in browser.find_elements(By.CSS_SELECTOR, '[role="alert"]')))
        click('Reconcile native host receipt')
        wait.until(lambda browser: 'original_ssh_acknowledgement_unchanged' in browser.find_element(By.CSS_SELECTOR, '[aria-label="Native host diagnostic receipt"]').get_attribute('textContent'))
        if configuration_deployment:
            field('Native configuration file (blank: no defaults)','/tmp/selected.cnf')
            label=driver.find_element(By.XPATH,'//label[normalize-space()="Native host operation"]')
            driver.find_element(By.ID,label.get_attribute('for')).click()
            wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'li[data-value="deploy_config"]')).click()
            field('Proposed native option-file text (UTF-8)','[mysqld]\n# native configuration 雪\nmax_connections=177\n')
            click('Review native option-file installation')
            wait.until(lambda browser:'configuration_deployment' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native host diagnostic review"]').get_attribute('textContent'))
            checkbox=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Authorize the reviewed option-file installation")]//input')
            driver.execute_script('arguments[0].click()',checkbox)
            click('Confirm native option-file installation')
            wait.until(lambda browser:'"installed": true' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native host diagnostic receipt"]').get_attribute('textContent'))
        if initialization:
            field('Native configuration file (blank: no defaults)','')
            label=driver.find_element(By.XPATH,'//label[normalize-space()="Native host operation"]')
            driver.find_element(By.ID,label.get_attribute('for')).click()
            wait.until(lambda browser:browser.find_element(By.CSS_SELECTOR,'li[data-value="initialize_data"]')).click()
            field('Native initialization data directory','/tmp/sr-desktop-initialization')
            click('Review native data-directory initialization')
            wait.until(lambda browser:'initialization_plan' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native host diagnostic review"]').get_attribute('textContent'))
            assert 'authenticated_ssh_host_before_native_initialization' in driver.find_element(By.CSS_SELECTOR,'[aria-label="Native host diagnostic review"]').get_attribute('textContent')
            checkbox=driver.find_element(By.XPATH,'//label[contains(normalize-space(),"Authorize the reviewed native data-directory initialization")]//input')
            driver.execute_script('arguments[0].click()',checkbox)
            click('Confirm native data-directory initialization')
            wait.until(lambda browser:'"native_initialization_returned": true' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native host diagnostic receipt"]').get_attribute('textContent'))
            click('Reconcile native host receipt')
            wait.until(lambda browser:'"process_termination_confirmed": true' in browser.find_element(By.CSS_SELECTOR,'[aria-label="Native host diagnostic receipt"]').get_attribute('textContent'))
        driver.execute_script('document.querySelectorAll("input,textarea").forEach(e=>e.style.visibility="hidden")')
        driver.save_screenshot(str(output / 'native-host-diagnostics.png'))
        errors = [entry for entry in driver.get_log('browser') if entry['level'] == 'SEVERE']
        (output / 'browser-console.json').write_text(json.dumps(errors, indent=2) + '\n')
        assert not errors
        return {'complete': True, 'console_errors': 0, 'native_review_confirm_and_receipt_reconciliation': True,'native_option_file_installation':configuration_deployment,'native_data_directory_initialization':initialization}
    except BaseException:
        if driver is not None:
            driver.execute_script('document.querySelectorAll("input,textarea").forEach(e=>e.style.visibility="hidden")')
            driver.save_screenshot(str(output / 'browser-failure.png'))
            (output / 'browser-failure-text.txt').write_text(driver.find_element(By.TAG_NAME, 'body').text)
        raise
    finally:
        if driver is not None: driver.quit()
        http.shutdown(); http.server_close(); thread.join(timeout=5)
        if thread.is_alive(): raise RuntimeError('Owned native host HTTP server did not stop')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--fixture-image', default='scratchrobin-mysql-host-fixture:current')
    parser.add_argument('--ssh-private-key')
    parser.add_argument('--prepare-fixture', action='store_true')
    parser.add_argument('--use-c', action='store_true');parser.add_argument('--configuration-deployment', action='store_true');parser.add_argument('--initialization', action='store_true')
    parser.add_argument('--browser-binary'); parser.add_argument('--driver-binary')
    args = parser.parse_args()
    if not args.prepare_fixture and not args.ssh_private_key:
        parser.error('Supply --prepare-fixture or --ssh-private-key for the owned fixture image')
    result = qualify(args.output, fixture_image=args.fixture_image, private_key=args.ssh_private_key,
                     prepare=args.prepare_fixture, use_c=args.use_c, browser_binary=args.browser_binary, driver_binary=args.driver_binary,configuration_deployment=args.configuration_deployment,initialization=args.initialization)
    print(json.dumps({'complete': result['complete'], 'checks': len(result['checks'])}))
