#!/usr/bin/env python3
"""Owned Linux Firebird dashboard/collector qualification, isolated per process."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.cdeadmin_firebird_local_fixture import run_local
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client
from pgadmin.cdeadmin.security.secrets import SecretLease

SCENARIOS = ('network', 'host', 'embedded')


class Permissions:
    def __init__(self, password):
        self.password = password
        self.secret_reads = 0
    def require(self, *_):
        return True
    def acquire_secret(self, *_):
        self.secret_reads += 1
        return SecretLease(self.password)


def eventually(predicate, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError('Owned native observation timed out')


def host_checks(native, admin, route, password, temporary, evidence, embedded):
    from flask import Flask
    from pgadmin.cdeadmin.workspace.monitoring_host import MonitoringHost
    if embedded:
        from pgadmin.cdeadmin.providers.firebird.provider import _database_create_arguments
        from pgadmin.cdeadmin.providers.firebird.database_creation import create_database
        from firebird.driver import core
        route = {'database':str(temporary/'embedded-collector.fdb'), 'user':'SYSDBA',
                 'charset':'UTF8', 'filesystem_root':str(temporary), 'attachment_mode':'embedded'}
        admin = create_database(native, core, **_database_create_arguments(route, route['database'], {'sql_dialect':3}, native))
    else:
        admin.execute_immediate("CREATE USER DDN_COLLECTOR PASSWORD '"+password+"' USING PLUGIN Srp")
        admin.execute_immediate('CREATE ROLE DDN_MONITOR SET SYSTEM PRIVILEGES TO MONITOR_ANY_ATTACHMENT')
        admin.execute_immediate('GRANT DDN_MONITOR TO USER DDN_COLLECTOR')
        admin.commit()
    admin.execute_immediate('CREATE TABLE COLLECTOR_HELD (V INTEGER)')
    admin.commit()
    admin.execute_immediate('INSERT INTO COLLECTOR_HELD VALUES (1)')
    transaction = admin.main_transaction.info.id
    app = Flask(__name__)
    app.config.update(CDEADMIN_MONITORING_PROCESS_MODE='single',
        CDEADMIN_MONITORING_LOCK_PATH=str(temporary/'collector.lock'),
        CDEADMIN_MONITORING_WORKER_KEYS={} if embedded else {'owned':base64.b64encode(os.urandom(32)).decode()},
        CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID=None if embedded else 'owned')
    host = MonitoringHost(app, None)
    permissions = Permissions(password)
    admitted = [True]
    profile = SimpleNamespace(profile_id='firebird-embedded' if embedded else 'firebird-native',
        database_targets=[SimpleNamespace(id='owned-db',display_name='Owned DB')])
    def owner(owner, sid):
        if (owner,sid)!=(1,7):
            raise PermissionError('Wrong owner')
        return SimpleNamespace(name='Owned Firebird',endpoint_profile=profile)
    def scope(owner_id, sid, target):
        owner(owner_id, sid)
        if not admitted[0] or target not in ('owned-db',None):
            raise PermissionError('Scope revoked')
        selected = dict(route)
        if target is None and not embedded:
            selected.pop('database',None)
        return {'endpoint_id':'owned-endpoint','generation':'owned-generation',
                'route':selected,'permissions':permissions}
    host._owned_server, host._scope = owner, scope
    body = {'heartbeat_enabled':True}
    if not embedded:
        body['credentials'] = {'username':'DDN_COLLECTOR','password':password,'role':'DDN_MONITOR'}
    result = {}
    try:
        # Viewing must neither acquire a worker key nor start a collector.
        assert host.snapshot(1,7,'owned-db')['state']=='disabled'
        assert not host._grants and host.ownership.fd is None
        started = host.enable(1,7,'owned-db',body)
        grant = host._grants[(1,7,'owned-db')]
        eventually(lambda: len(host.snapshot(1,7,'owned-db')['samples'])>=2)
        observed = host.snapshot(1,7,'owned-db')
        samples = observed['samples']
        (evidence/'observations.json').write_text(json.dumps(observed,indent=2))
        assert all(row['status'] in ('available','partial') for row in samples), samples[-1].get('error_type')
        assert samples[0]['collector']['transaction_id'] != samples[1]['collector']['transaction_id']
        assert all(row['transaction_refresh']['status']=='completed' for row in samples)
        assert observed['heartbeat']['status']=='observed'
        assert observed['authentication']['mode']==('local-file' if embedded else 'dedicated')
        assert samples[-1]['coverage']=='database'
        assert samples[-1]['collector']['user']==('SYSDBA' if embedded else 'DDN_COLLECTOR')
        assert admin.main_transaction.info.id==transaction
        assert permissions.secret_reads==0
        from pgadmin.cdeadmin.workspace.monitoring_fleet import fleet_snapshot
        server_snapshot = host.snapshot(1,7,None)
        fleet = fleet_snapshot([{'server_id':7,'name':'Owned Firebird',
            'databases':[{'target_id':'owned-db','name':'Owned DB'}]}],
            lambda sid,target:host.snapshot(1,sid,target))
        publication = subprocess.run(['node',str(ROOT/'tools/tests/check_firebird_dashboard.mjs')],
            input=json.dumps({'database':observed,'server':server_snapshot,'engine':fleet}),
            text=True,capture_output=True,timeout=60)
        (evidence/'publication.json').write_text(publication.stdout)
        (evidence/'publication.stderr').write_text(publication.stderr)
        assert publication.returncode==0
        result['native_observations_published_and_rebound']=json.loads(publication.stdout)
        assert host.enable(1,7,'owned-db',{'heartbeat_enabled':True})['revision']==started['revision']
        job = host.runtime._jobs[grant.policy.key]
        source = job.source._source
        assert not source._connection.main_transaction.is_active()
        epoch = samples[-1]['source_epoch']
        with source._lock:
            source._connection.close()  # Owned transport interruption.
        eventually(lambda: any(row.get('source_epoch') != epoch and
            row['status'] in ('available','partial') for row in host.snapshot(1,7,'owned-db')['samples']),20)
        recovered = host.snapshot(1,7,'owned-db')['samples']
        assert any(row['status']=='unavailable' for row in recovered)
        assert recovered[-1]['rates']['status']=='gap'
        assert admin.main_transaction.info.id==transaction
        result['native_reconnect_resets_counter_epoch']=True
        # Native release failure must retain ownership and refuse replacement.
        close = source._client.close
        fail_release = [True]
        def uncertain_release():
            if fail_release[0]:
                raise OSError('Owned release failure injection')
            return close()
        source._client.close = uncertain_release
        assert host.disable(1,7,'owned-db')['released'] is False
        try:
            host.enable(1,7,'owned-db',body)
        except (PermissionError,ValueError):
            pass
        else:
            raise AssertionError('Replaced unreleased collector')
        fail_release[0] = False
        assert host.disable(1,7,'owned-db')['released'] is True
        assert source._connection is None
        # Lease expiry closes the native source without any viewer heartbeat.
        expiring = {**body,'lease_seconds':5}
        host.enable(1,7,'owned-db',expiring)
        current = host._grants[(1,7,'owned-db')]
        eventually(lambda: host.runtime.snapshot(current.policy,lambda *_:True)['state']=='expired')
        assert host.runtime._jobs[current.policy.key].source is None
        assert host.disable(1,7,'owned-db')['released']
        # Reconfiguration is an explicit stop/start. Registration reuse seals
        # its password once, independently of any interactive attachment.
        host.enable(1,7,'owned-db',{'heartbeat_enabled':True})
        current = host._grants[(1,7,'owned-db')]
        eventually(lambda: bool(host.snapshot(1,7,'owned-db')['samples']))
        assert host.snapshot(1,7,'owned-db')['samples'][-1]['status'] in ('available','partial')
        assert permissions.secret_reads==(0 if embedded else 1)
        admitted[0]=False
        eventually(lambda: host.runtime.snapshot(current.policy,lambda *_:True)['state']=='authorization-denied')
        try:
            host.snapshot(1,7,'owned-db')
        except PermissionError:
            pass
        else:
            raise AssertionError('Published revoked samples')
        assert host.disable(1,7,'owned-db')['released']
        admitted[0]=True
        if not embedded:
            bad = {**body,'credentials':{**body['credentials'],'password':secrets.token_urlsafe(24)}}
            host.enable(1,7,'owned-db',bad)
            eventually(lambda: bool(host.snapshot(1,7,'owned-db')['samples']))
            failed = host.snapshot(1,7,'owned-db')
            assert failed['samples'][-1]['status']=='unavailable'
            assert failed['heartbeat']['status']=='unknown'
            assert host.disable(1,7,'owned-db')['released']
        else:
            try:
                host.enable(1,7,'owned-db',{**body,'credentials':{'username':'SYSDBA','password':'unused'}})
            except ValueError:
                pass
            else:
                raise AssertionError('Embedded password presented as authentication')
        assert admin.main_transaction.info.id==transaction
        result.update(passive_viewer=True, two_native_background_samples=True,
            independent_transactions=True, interactive_transaction_unchanged=True,
            native_visibility=True, confirmed_release_before_replacement=True,
            native_expiry_cleanup=True, registration_reuse=True, revocation_cleanup=True,
            authentication='local-file' if embedded else 'dedicated-native-role',
            worker_keys_required=not embedded, wrong_password_not_a_heartbeat=not embedded)
    finally:
        assert host.close()
        admin.rollback()
        if embedded:
            admin.close()
    return result


def run(runtime,evidence,scenario):
    details={}
    def check(native,admin,route,accounts,target,temporary):
        password=secrets.token_urlsafe(24)
        admin.execute_immediate("ALTER USER SYSDBA PASSWORD '"+password+"' USING PLUGIN Srp")
        admin.commit()
        scoped={**route,'user':'SYSDBA','credential_reference_id':'owned','principal_reference':'owner:1'}
        if scenario=='network':
            from tools.cdeadmin_firebird_monitoring_gate import run as qualify
            # A quiet disposable server need not have created its log yet.
            (Path(os.environ['FIREBIRD'])/'firebird.log').touch(exist_ok=True)
            profiles=temporary/'private-profiles.json'
            profiles.write_text(json.dumps({'profiles':[{**scoped,'engine':'firebird','password':password}]}))
            profiles.chmod(0o600)
            try:
                result=qualify(profiles)
            finally:
                profiles.unlink()
            (target/'network.json').write_text(json.dumps(result,indent=2))
            assert result['status']=='passed',result['failures']
            details.update(result)
        else:
            details.update(host_checks(native,admin,scoped,password,temporary,target,scenario=='embedded'))
    receipt=run_local(runtime,evidence/'fixture',check)
    document={'complete':receipt['complete'],'native':receipt,'details':details}
    (evidence/'summary.json').write_text(json.dumps(document,indent=2))
    return document


def source_state():
    status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True)
    changed=subprocess.check_output(['git','diff','--name-only','-z'],cwd=ROOT).split(b'\0')
    added=subprocess.check_output(['git','ls-files','--others','--exclude-standard','-z'],cwd=ROOT).split(b'\0')
    names={os.fsdecode(name) for name in changed+added if name}
    files={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
           for name in sorted(names) if (ROOT/name).is_file()}
    manifest=ROOT/'web/pgadmin/static/vendor/ddn/current/resource-manifest.json'
    return {'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'status':status,'changed_files':files,'ddn_manifest_sha256':hashlib.sha256(manifest.read_bytes()).hexdigest(),
            'ddn_revision':json.loads(manifest.read_text())['source']['revision']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root',required=True,type=Path)
    parser.add_argument('--evidence',required=True,type=Path)
    parser.add_argument('--scenario',choices=SCENARIOS)
    args=parser.parse_args()
    args.evidence.mkdir(parents=True,exist_ok=False)
    baseline=source_state()
    (args.evidence/'inputs.json').write_text(json.dumps(baseline,indent=2))
    if args.scenario:
        result=run(args.runtime_root,args.evidence,args.scenario)
    else:
        results=[]
        for scenario in SCENARIOS:
            with (args.evidence/(scenario+'.log')).open('wb') as log:
                process=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),
                    '--runtime-root',str(args.runtime_root),'--evidence',str(args.evidence/scenario),
                    '--scenario',scenario],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                try:
                    code=process.wait(timeout=300)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGTERM)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL)
                        process.wait()
                    code=-1
            path=args.evidence/scenario/'summary.json'
            results.append({'scenario':scenario,'exit_code':code,
                'result':json.loads(path.read_text()) if path.exists() else {'complete':False}})
        result={'complete':all(row['exit_code']==0 and row['result']['complete'] for row in results),'scenarios':results}
        (args.evidence/'summary.json').write_text(json.dumps(result,indent=2))
    result['source_unchanged']=source_state()==baseline
    result['complete']=result['complete'] and result['source_unchanged']
    (args.evidence/'summary.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['complete'] else 1)
