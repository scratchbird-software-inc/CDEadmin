"""The verification runner's bookkeeping (tools/cdeadmin_verify.py)."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))

import cdeadmin_verify as verify  # noqa: E402


def run_with(tmp_path, known):
    run = object.__new__(verify.Run)
    run.known, run.stages, run.out = known, [], tmp_path
    run.args = SimpleNamespace(tier=['quick'], engines='')
    return run


def test_new_known_and_fixed_failures_are_kept_apart(tmp_path):
    run = run_with(tmp_path, {'python': [{'id': 'a'}, {'id': 'b'}]})
    stage = verify.Stage('python-contracts', 'p', 'l')
    run.compare(stage, 'python', {'a', 'c'})
    assert (stage.new_failures, stage.known_open, stage.fixed) == (
        ['c'], ['a'], ['b'])
    assert stage.status == 'failed'
    run.compare(stage, 'python', {'a'})
    assert stage.status == 'known failures only'


def test_known_failures_are_never_a_pass_in_the_verdict(tmp_path):
    run = run_with(tmp_path, {'python': [{'id': 'a'}]})
    stage = verify.Stage('python-contracts', 'p', 'l')
    run.compare(stage, 'python', {'a'})
    run.stages.append(stage)
    skipped = verify.Stage('ddn', 'p', 'l')
    skipped.status = 'skipped'
    run.stages.append(skipped)
    assert verify.report(run) == 0
    document = json.loads((tmp_path / 'report.json').read_text())
    assert document['verdict'] == ('no new failures; 1 known failures still '
                                   'open; not proven: ddn (skipped)')


def test_new_failures_fail_the_run_and_are_only_proposed(tmp_path):
    run = run_with(tmp_path, {})
    stage = verify.Stage('jest', 'p', 'l')
    run.compare(stage, 'jest', {'x.spec.js › t'})
    run.stages.append(stage)
    assert verify.report(run) == 1
    proposed = json.loads(
        (tmp_path / 'proposed_known_failures.json').read_text())
    assert proposed == [{'id': 'x.spec.js › t', 'error': '', 'date': '',
                         'reason': ''}]


def test_junit_and_jest_reports_are_read(tmp_path):
    xml = tmp_path / 'r.xml'
    xml.write_text(
        '<testsuites><testsuite>'
        '<testcase classname="tools.tests.test_a" name="test_ok"/>'
        '<testcase classname="tools.tests.test_a" name="test_bad">'
        '<failure/></testcase>'
        '<testcase classname="tools.tests.test_b" name="">'
        '<error/></testcase>'
        '<testcase classname="tools.tests.test_a" name="test_skip">'
        '<skipped/></testcase>'
        '</testsuite></testsuites>')
    assert verify.junit_failures(xml) == {
        'tools/tests/test_a.py::test_bad', 'tools/tests/test_b.py'}
    assert verify.junit_total(xml) == 4
    assert verify.junit_skips(xml) == {'test_skip'}
    assert verify.junit_failures(tmp_path / 'missing.xml') == {
        '<pytest did not report>'}
    report = tmp_path / 'j.json'
    report.write_text(json.dumps({'numTotalTests': 3, 'testResults': [
        {'name': str(verify.WEB / 'regression/a.spec.js'),
         'status': 'failed', 'assertionResults': [
             {'status': 'failed', 'fullName': 'A fails'},
             {'status': 'passed', 'fullName': 'A passes'}]},
        {'name': str(verify.WEB / 'regression/b.spec.js'),
         'status': 'failed', 'assertionResults': []}]}))
    assert verify.jest_failures(report) == {
        'regression/a.spec.js › A fails',
        'regression/b.spec.js › <suite failed to run>'}
    assert verify.jest_total(report) == 3


def test_live_settings_come_from_the_demo_profiles():
    assert verify.live_settings('immudb') == {
        'host': '127.0.0.1', 'port': 55435, 'user': 'immudb',
        'password': 'immudb', 'web_port': 58082, 'metrics_port': 59497}
    assert verify.live_settings('xtdb')['healthz_port'] == 58083
    assert verify.live_settings('vitess')['keyspace'] == 'test_keyspace'
