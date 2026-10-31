#!/usr/bin/env python3
##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""One entry point for verifying a CDEadmin working tree.

Tiers, each a superset of the one before it except live and browser, which
are chosen on their own:

  quick    preflight, DDN refresh, descriptor gate, lint and style of the
           files changed against the upstream branch, the family render
           suite
  unit     quick + ``make check-gates``, the full Python contracts and the
           full Jest suite
  live     engine round trips on the reference demos (``--engines``), one
           demo at a time; a demo this run did not start is never stopped
  browser  the sandboxed launcher and native-browser check of
           tools/development/native_verify.py

Every stage records what it proves and what it does not. Failures are
compared with tools/cdeadmin_verify_known_failures.json: a new failure fails
the run; a listed one that now passes is reported so the list can shrink.
The list is edited by hand only; the report proposes entries, it never adds
them. Open known failures are always shown: no regressions is not passed.

Reports go to .devstate/verify/<UTC time>/ (gitignored): report.md,
report.json and one log per stage.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ElementTree
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web'
KNOWN = ROOT / 'tools/cdeadmin_verify_known_failures.json'
PROFILES = (ROOT / 'tools/reference_engine_demos' /
            'connection_profiles.template.json')
# Yarn through corepack, as native_verify.py runs it.
YARN = ['corepack', 'yarn']
DEV = ['bash', str(ROOT / 'tools/development/dev.sh')]
TIERS = ('quick', 'unit', 'live', 'browser')
MIN_TMP_FREE = 4 * 1024 ** 3
# Engines whose round trip leaves objects the engine can never remove.
PERMANENT = {
    'immudb': 'immudb keeps every user; each run leaves one deactivated '
              'rt_user_*',
    'xtdb': 'XTDB keeps every user and table; the test reuses fixed names',
}


class Stage:
    """One check: what ran, its outcome and what it does and does not prove."""

    def __init__(self, name, proves, limits):
        self.name, self.proves, self.limits = name, proves, limits
        self.status, self.detail, self.seconds = 'not run', '', 0.0
        self.new_failures, self.fixed, self.known_open = [], [], []
        self.flaky, self.log = [], None

    def record(self):
        return {key: getattr(self, key) for key in (
            'name', 'status', 'detail', 'seconds', 'proves', 'limits',
            'new_failures', 'fixed', 'known_open', 'flaky', 'log')}


class Run:
    def __init__(self, args):
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            '%Y%m%dT%H%M%SZ')
        self.args = args
        self.out = Path(args.output or ROOT / '.devstate/verify' / stamp)
        self.out.mkdir(parents=True, exist_ok=False)
        self.stages = []
        self.known = json.loads(KNOWN.read_text()) if KNOWN.exists() else {}
        self.env = dict(os.environ)
        venv = ROOT / '.venv/bin'
        if venv.is_dir():
            # The gates call python3 from PATH, as dev.sh does.
            self.env['PATH'] = f'{venv}{os.pathsep}{self.env.get("PATH", "")}'
            self.env['VIRTUAL_ENV'] = str(venv.parent)

    def command(self, stage, args, cwd=ROOT, timeout=3600, env=None):
        """Run one command, its output in the stage's log; return the code."""
        stage.log = str(self.out / f'{stage.name}.log')
        with open(stage.log, 'a', encoding='utf-8') as log:
            log.write(f'$ (cd {cwd}) {" ".join(map(str, args))}\n')
            log.flush()
            try:
                return subprocess.run(
                    [str(item) for item in args], cwd=cwd, stdout=log,
                    stderr=subprocess.STDOUT, timeout=timeout,
                    env=env or self.env).returncode
            except subprocess.TimeoutExpired:
                log.write(f'\nTIMEOUT after {timeout}s\n')
                return 124

    def stage(self, name, proves, limits, body):
        stage = Stage(name, proves, limits)
        self.stages.append(stage)
        print(f'[verify] {name} ...', flush=True)
        started = time.monotonic()
        try:
            body(stage)
        except Exception as error:  # a stage error is a result, not a crash
            stage.status = 'error'
            stage.detail = f'{type(error).__name__}: {error}'
        stage.seconds = round(time.monotonic() - started, 1)
        print(f'[verify] {name}: {stage.status} {stage.detail}'.rstrip(),
              flush=True)
        return stage

    def compare(self, stage, suite, failing):
        """Split failures into new, known-open and known-now-passing."""
        listed = {item['id']: item for item in self.known.get(suite, [])}
        failing = sorted(set(failing))
        stage.new_failures = [item for item in failing if item not in listed]
        stage.known_open = [item for item in failing if item in listed]
        stage.fixed = sorted(set(listed) - set(failing))
        if stage.new_failures:
            stage.status = 'failed'
        elif stage.known_open:
            stage.status = 'known failures only'
        else:
            stage.status = 'passed'
        stage.detail = (f'{len(stage.new_failures)} new, '
                        f'{len(stage.known_open)} known open, '
                        f'{len(stage.fixed)} known now passing')


def changed_files(run):
    """Files changed against the upstream branch, plus uncommitted ones."""
    base = subprocess.run(
        ['git', 'merge-base', 'HEAD', '@{upstream}'], cwd=ROOT,
        capture_output=True, text=True).stdout.strip() or 'HEAD'
    names = set(subprocess.run(
        ['git', 'diff', '--name-only', base], cwd=ROOT, capture_output=True,
        text=True).stdout.split())
    names |= set(subprocess.run(
        ['git', 'ls-files', '--others', '--exclude-standard'], cwd=ROOT,
        capture_output=True, text=True).stdout.split())
    return sorted(name for name in names if (ROOT / name).is_file())


# --------------------------------------------------------------- stages

def preflight(run):
    def body(stage):
        problems = []
        python = ROOT / '.venv/bin/python'
        version = subprocess.run(
            [python, '-c', 'import sys; print(sys.version.split()[0])'],
            capture_output=True, text=True).stdout.strip() \
            if python.exists() else ''
        if not version.startswith('3.14'):
            problems.append(f'.venv Python is {version or "missing"}, '
                            'not 3.14 (README minimum)')
        free = shutil.disk_usage('/tmp').free
        if free < MIN_TMP_FREE:
            problems.append(f'/tmp has {free // 1024 ** 2} MiB free; a '
                            'full /tmp turns passes into failures')
        head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                              capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(['git', 'status', '--short'], cwd=ROOT,
                               capture_output=True, text=True).stdout
        stage.detail = (f'HEAD {head[:12]}, Python {version}, /tmp free '
                        f'{free // 1024 ** 3} GiB, '
                        f'{len(dirty.splitlines())} uncommitted paths')
        Path(run.out / 'git-status.txt').write_text(dirty)
        stage.status = 'failed' if problems else 'passed'
        if problems:
            stage.detail += '; ' + '; '.join(problems)
    return run.stage(
        'preflight', 'the interpreter, /tmp space and tree state are known',
        'nothing about the code', body)


def ddn(run):
    def body(stage):
        before = vendored_status()
        code = run.command(stage, DEV + ['ddn'], timeout=1800)
        if code == 0:
            code = run.command(stage, [ROOT / '.venv/bin/python',
                                       ROOT / 'tools/refresh_ddn.py',
                                       '--verify-vendored'])
        changed = sorted(set(vendored_status()) - set(before))
        stage.status = 'passed' if code == 0 else 'failed'
        note = ' (commit them separately)' if changed else ''
        stage.detail = (f'refresh and verification exit {code}; '
                        f'{len(changed)} vendored paths changed by the '
                        f'refresh{note}')
    return run.stage(
        'ddn', 'the consumed DDN copy is the current one and verifies '
        '(AGENTS.md: refresh before any test run that validates a commit)',
        'that DDN itself is correct', body)


def vendored_status():
    return subprocess.run(
        ['git', 'status', '--short', 'web/pgadmin/static/vendor/ddn'],
        cwd=ROOT, capture_output=True, text=True).stdout.splitlines()


def descriptors(run):
    def body(stage):
        code = run.command(stage, [
            'python3', 'tools/validate_ui_descriptors.py', '--counts',
            '--enforce-counts', 'tools/ui_lint_maximums.json'])
        stage.status = 'passed' if code == 0 else 'failed'
        stage.detail = f'exit {code}'
    return run.stage(
        'descriptors', 'every descriptor folder matches its schema, and the '
        'UI lint counts are at or below their maximums',
        'that a form works against a server', body)


def lint(run, everything):
    def body(stage):
        files = changed_files(run)
        js = [name for name in files if name.startswith('web/') and
              name.endswith(('.js', '.jsx', '.ts', '.tsx')) and
              '/generated/' not in name and '/vendor/' not in name]
        py = [name for name in files if name.endswith('.py')]
        codes = []
        if everything:
            codes.append(run.command(stage, [*YARN, 'run', 'linter'],
                                     cwd=WEB, timeout=3600))
            codes.append(run.command(stage, ['make', 'check-pep8']))
        else:
            if js:
                codes.append(run.command(stage, [
                    *YARN, 'run', 'eslint', '-c', '.eslintrc.js',
                    *[str(ROOT / name) for name in js]], cwd=WEB))
            if py:
                codes.append(run.command(stage, [
                    'python3', '-m', 'pycodestyle', '--config=.pycodestyle',
                    *py]))
        bad = [code for code in codes if code != 0]
        stage.status = 'failed' if bad else 'passed'
        stage.detail = ('whole tree' if everything else
                        f'{len(js)} JS and {len(py)} Python changed files')
    return run.stage(
        'lint', 'ESLint (flat config, -c .eslintrc.js) and pycodestyle '
        'accept the checked files',
        'behaviour; the quick tier checks changed files only', body)


def jest(run, paths, name, proves):
    def body(stage):
        report = run.out / f'{name}.json'
        args = [*YARN, 'run', 'jest', '--maxWorkers=50%', '--json',
                '--outputFile', report, *paths]
        run.command(stage, args, cwd=WEB, timeout=7200)
        failing = jest_failures(report)
        # A suite that fails in parallel and passes alone is flaky: shown,
        # never counted as passed.
        confirmed = set()
        for suite in sorted({item.split(' › ')[0] for item in failing}):
            rerun = run.out / f'{name}-rerun.json'
            run.command(stage, [*YARN, 'run', 'jest', '--runInBand',
                                '--json', '--outputFile', rerun, suite],
                        cwd=WEB, timeout=1800)
            still = jest_failures(rerun)
            confirmed |= still
            stage.flaky += sorted(
                item for item in failing
                if item.startswith(suite) and item not in still)
        run.compare(stage, 'jest', confirmed)
        if stage.flaky and stage.status == 'passed':
            stage.status = 'passed with flaky suites'
        stage.detail = (f'{jest_total(report)} tests; ' + stage.detail +
                        f', {len(stage.flaky)} flaky (failed only in '
                        'parallel)')
    return run.stage(name, proves, 'anything a browser or server would show',
                     body)


def jest_total(report):
    try:
        return json.loads(Path(report).read_text()).get('numTotalTests', 0)
    except (OSError, ValueError):
        return 0


def jest_failures(report):
    try:
        document = json.loads(Path(report).read_text())
    except (OSError, ValueError):
        return {'<jest did not report>'}
    failing = set()
    for suite in document.get('testResults', []):
        path = os.path.relpath(suite.get('name', ''), WEB)
        if suite.get('status') == 'failed' and not suite.get(
                'assertionResults'):
            failing.add(f'{path} › <suite failed to run>')
        for test in suite.get('assertionResults', []):
            if test.get('status') == 'failed':
                failing.add(f'{path} › {test.get("fullName")}')
    return failing


def gates(run):
    def body(stage):
        code = run.command(stage, ['make', 'check-gates'], timeout=7200)
        stage.status = 'passed' if code == 0 else 'failed'
        stage.detail = f'exit {code}'
    return run.stage(
        'check-gates', 'the curated CDEadmin gates (Makefile CHECK_GATES) '
        'pass', 'the tests outside those gates', body)


def python_contracts(run):
    def body(stage):
        report = run.out / 'python.xml'
        # As native_verify.py runs them: config imported first, history
        # deferred by the owner (2026-10-16).
        run.command(stage, [
            'python3', '-c',
            'import sys; sys.path[:0] = ["web"]; import config, pytest; '
            'raise SystemExit(pytest.main(["tools/tests", "-q", "-p", '
            '"no:cacheprovider", "--continue-on-collection-errors", "-k", '
            f'"not history", "--junitxml={report}"]))'], timeout=7200)
        run.compare(stage, 'python', junit_failures(report))
        stage.detail = f'{junit_total(report)} tests; ' + stage.detail
    return run.stage(
        'python-contracts', 'every test in tools/tests (history excepted) '
        'passes or is a listed known failure',
        'live engines: round trips skip without their settings', body)


def junit_failures(report):
    try:
        tree = ElementTree.parse(report)
    except (OSError, ElementTree.ParseError):
        return {'<pytest did not report>'}
    failing = set()
    for case in tree.iter('testcase'):
        if case.find('failure') is not None or case.find('error') is not None:
            name = case.get('classname', '').replace('.', '/') + '.py'
            failing.add(f'{name}::{case.get("name")}' if case.get('name')
                        else name)
    return failing


def demos_running():
    result = subprocess.run(DEV + ['status'], cwd=ROOT, capture_output=True,
                            text=True)
    text = result.stdout
    start = min((index for index in (text.find('['), text.find('{'))
                 if index >= 0), default=-1)
    if start < 0:
        return set()
    document = json.loads(text[start:])
    items = document if isinstance(document, list) else document.get(
        'engines', list(document.values()))
    return {item.get('engine') for item in items
            if isinstance(item, dict) and item.get('runtime') == 'running'}


def live_settings(engine):
    profiles = json.loads(PROFILES.read_text())['profiles']
    profile = next(item for item in profiles if item['engine'] == engine)
    settings = {'host': '127.0.0.1', 'port': profile['port'],
                'user': profile.get('user')}
    if profile.get('password'):
        settings['password'] = profile['password']
    extra = {
        'immudb': {'web_port': profile.get('http_port'),
                   'metrics_port': profile.get('metrics_port')},
        'xtdb': {'healthz_port': profile.get('http_port')},
        'vitess': {'keyspace': profile.get('database'),
                   'http_port': profile.get('http_port')},
        'firebird': {'database_root': profile.get('database_create_root')},
    }.get(engine, {})
    settings.update(extra)
    return settings


def live(run, engine):
    test = ROOT / f'tools/tests/test_ui_descriptor_roundtrip_{engine}.py'

    def body(stage):
        if not test.exists():
            stage.status, stage.detail = 'gap', 'no live round-trip test'
            return
        if engine in PERMANENT and not run.args.allow_permanent:
            stage.status = 'skipped'
            stage.detail = (f'{PERMANENT[engine]}; pass --allow-permanent '
                            'to run it')
            return
        started_here = engine not in demos_running()
        others = demos_running() - {engine}
        if started_here and others & set(run.started):
            # One demo at a time: stop the one this run started last.
            for name in sorted(others & set(run.started)):
                run.command(stage, DEV + ['stop', name], timeout=600)
        if started_here:
            if run.command(stage, DEV + ['start', engine], timeout=1800):
                stage.status, stage.detail = 'error', 'demo did not start'
                return
            run.started.append(engine)
        if run.command(stage, DEV + ['verify', engine], timeout=900):
            stage.status, stage.detail = 'error', 'demo did not verify'
            return
        env = dict(run.env)
        env[f'CDEADMIN_ROUNDTRIP_{engine.upper()}'] = json.dumps(
            live_settings(engine))
        report = run.out / f'live-{engine}.xml'
        code = run.command(stage, [
            'python3', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
            '-rs', str(test), f'--junitxml={report}'], env=env,
            timeout=7200)
        failing = junit_failures(report)
        skipped = junit_skips(report)
        run.compare(stage, 'live', failing)
        if skipped and not failing:
            stage.status = 'skipped'
        demo = ('started here' if started_here else
                'was already running, left running')
        stage.detail = (f'{junit_total(report)} tests; ' + stage.detail +
                        f'; pytest exit {code}; {len(skipped)} skipped; '
                        f'demo {demo}')
        if engine in PERMANENT:
            stage.detail += f'; leaves permanent objects: {PERMANENT[engine]}'
    return run.stage(
        f'live-{engine}', f'{engine} forms round-trip against the reference '
        'demo: plan, apply, read back', 'other versions, multi-node '
        'topologies and anything the test does not draft', body)


def junit_total(report):
    try:
        return sum(1 for _case in ElementTree.parse(report).iter('testcase'))
    except (OSError, ElementTree.ParseError):
        return 0


def junit_skips(report):
    try:
        tree = ElementTree.parse(report)
    except (OSError, ElementTree.ParseError):
        return set()
    return {case.get('name') for case in tree.iter('testcase')
            if case.find('skipped') is not None}


def browser(run):
    def body(stage):
        missing = [name for name in ('selenium',) if subprocess.run(
            ['python3', '-c', f'import {name}'], env=run.env,
            capture_output=True).returncode]
        if missing:
            stage.status = 'blocked'
            stage.detail = ('not installed: ' + ', '.join(missing) +
                            ' (web/regression/requirements.txt; '
                            'make install-python-testing)')
            return
        evidence = run.out / 'browser'
        code = run.command(stage, [
            'python3', '-c',
            'import sys; sys.path[:0] = ["tools/development", "tools"]; '
            'from pathlib import Path; import native_verify; '
            f'p = Path("{evidence}"); p.mkdir(); native_verify.http(p)'],
            timeout=1800)
        stage.status = 'passed' if code == 0 else 'failed'
        stage.detail = (f'exit {code}; screenshot and browser.json in '
                        f'{evidence}')
    return run.stage(
        'browser', 'the built workbench mounts in a headless browser from a '
        'sandboxed launcher (own data directory and port) without console '
        'errors', 'that any form works; the bundle is whatever was last '
        'built (dev.sh frontend)', body)


# --------------------------------------------------------------- report

def report(run):
    stages = [stage.record() for stage in run.stages]
    open_known = sum(len(stage['known_open']) for stage in stages)
    new = sum(len(stage['new_failures']) for stage in stages)
    bad = [stage['name'] for stage in stages if stage['status'] in (
        'failed', 'error', 'blocked')]
    verdict = ('FAILED: ' + ', '.join(bad)) if bad else (
        f'no new failures; {open_known} known failures still open'
        if open_known else 'no failures in the stages run')
    unproven = [f'{stage["name"]} ({stage["status"]})' for stage in stages
                if stage['status'] in ('skipped', 'gap', 'not run')]
    if unproven:
        verdict += '; not proven: ' + ', '.join(unproven)
    document = {'verdict': verdict, 'tiers': run.args.tier,
                'engines': run.args.engines, 'new_failures': new,
                'known_open': open_known, 'stages': stages}
    (run.out / 'report.json').write_text(json.dumps(document, indent=2))
    lines = [f'# CDEadmin verification — {run.out.name}', '',
             f'**{verdict}**', '',
             'Not a completion claim: each stage proves only what it says.',
             '', '| Stage | Status | Detail | Time (s) |', '|---|---|---|---|']
    lines += [f'| {s["name"]} | {s["status"]} | {s["detail"]} | '
              f'{s["seconds"]} |' for s in stages]
    for stage in stages:
        lines += ['', f'## {stage["name"]}', '',
                  f'- Proves: {stage["proves"]}',
                  f'- Does not prove: {stage["limits"]}',
                  f'- Log: {stage["log"]}']
        for title, key in (('New failures', 'new_failures'),
                           ('Flaky (parallel only)', 'flaky'),
                           ('Known, still failing', 'known_open'),
                           ('Known, now passing (remove from the list)',
                            'fixed')):
            if stage[key]:
                lines += ['', f'{title} ({len(stage[key])}):', '']
                lines += [f'- `{item}`' for item in stage[key][:200]]
                if len(stage[key]) > 200:
                    lines.append(f'- … {len(stage[key]) - 200} more in '
                                 'report.json')
    proposed = [{'id': item, 'error': '', 'date': '', 'reason': ''}
                for stage in stages for item in stage['new_failures']]
    if proposed:
        (run.out / 'proposed_known_failures.json').write_text(
            json.dumps(proposed, indent=2))
        lines += ['', 'New failures are not added to the known list '
                  'automatically. proposed_known_failures.json lists them '
                  'for review; each entry needs the error, date and reason.']
    (run.out / 'report.md').write_text('\n'.join(lines) + '\n')
    print(f'\n[verify] {verdict}\n[verify] report: {run.out / "report.md"}')
    return 1 if bad else 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--tier', action='append', choices=TIERS,
                        help='repeatable; default quick')
    parser.add_argument('--engines', default='',
                        help='comma-separated engines for the live tier')
    parser.add_argument('--allow-permanent', action='store_true',
                        help='also run engines whose tests leave objects the '
                             'engine cannot remove (immudb, xtdb)')
    parser.add_argument('--skip-ddn', action='store_true',
                        help='do not refresh DDN (the run then does not '
                             'validate a commit; the report says so)')
    parser.add_argument('--output', help='report directory')
    args = parser.parse_args()
    args.tier = args.tier or ['quick']
    run = Run(args)
    run.started = []
    preflight(run)
    if args.skip_ddn:
        stage = Stage('ddn', '', 'the run does not validate a commit')
        stage.status = 'skipped'
        stage.detail = 'skipped by --skip-ddn: not valid for a commit'
        run.stages.append(stage)
    else:
        ddn(run)
    if {'quick', 'unit'} & set(args.tier):
        descriptors(run)
        lint(run, everything='unit' in args.tier)
        if 'unit' in args.tier:
            gates(run)
            python_contracts(run)
            jest(run, [], 'jest', 'the whole Jest suite passes, or fails '
                 'only in listed or flaky tests')
        else:
            jest(run, ['regression/javascript/families'], 'jest-families',
                 'every engine form renders in the shared editor and the '
                 'form-ergonomics behaviour holds')
    if 'live' in args.tier:
        for engine in [name for name in args.engines.split(',') if name]:
            live(run, engine)
        for engine in reversed(run.started):
            stage = Stage(f'stop-{engine}', 'the demo this run started is '
                          'stopped', '')
            run.command(stage, DEV + ['stop', engine], timeout=600)
    if 'browser' in args.tier:
        browser(run)
    return report(run)


if __name__ == '__main__':
    sys.exit(main())
