"""Native option-file dependency review and independent process observations."""
from pathlib import Path
import os
import base64
import json
import sys

import pytest

from pgadmin.cdeadmin.providers.mysql_family import mysql_host_worker as worker
from test_mysql_host import host


def graph(path):
    context = {'working_directory': str(path.parent), 'home_directory': str(path.parent)}
    return worker.configuration_graph(path, context)


def test_native_include_syntax_directory_order_and_filename_bytes(tmp_path):
    root = tmp_path / 'selected.cnf'; directory = tmp_path / 'parts'; directory.mkdir()
    for name in ('z.cnf', 'a.cnf', '.cnf', 'ignored.CNF', 'ignored.ini', 'ignored.txt'):
        (directory / name).write_text('[mysqld]\n')
    (tmp_path / 'child#literal.cnf').write_text('[mysqld]\n')
    (tmp_path / 'child.cnf').write_text('[mysqld]\n')
    # Native '#' comments respect quotes, but include arguments themselves are
    # not unquoted. ';' is only a whole-line comment. Matching is case-sensitive.
    root.write_bytes(b'; !include nonexistent\n# !include absent\n!INCLUDE absent\n'
        b'!include child.cnf # end comment\n!includedir parts\n'
        b'!include "child#literal.cnf"\n!include child.cnf;literal\n')
    value = graph(root); entries = value['entries']
    listing = next(row for row in entries if row['kind'] == 'directory')
    assert listing['selected_names'] == ['.cnf', 'a.cnf', 'z.cnf']
    assert [Path(row['path']).name for row in entries if row['state'] == 'missing'] == ['"child#literal.cnf"', 'child.cnf;literal']
    assert any(row['path'] == str(tmp_path / 'child.cnf') and row['state'] == 'read' for row in entries)
    assert not value['atomic_native_file_read_snapshot']


def test_native_relative_includes_use_process_cwd_and_tilde_uses_reviewed_home(tmp_path):
    nested = tmp_path / 'nested'; nested.mkdir()
    root = tmp_path / 'selected.cnf'; root.write_text('!include nested/child.cnf\n')
    (nested / 'child.cnf').write_text('!include leaf.cnf\n!include ~/leaf.cnf\n')
    (tmp_path / 'leaf.cnf').write_text('[mysqld]\n')
    entries = graph(root)['entries']
    assert len(entries) == 4 and all(row['state'] == 'read' for row in entries)
    assert [row['path'] for row in entries[-2:]] == [str(tmp_path / 'leaf.cnf')] * 2


def test_latin1_space_and_lf_only_lines_follow_native_loader(tmp_path):
    root = tmp_path / 'selected.cnf'; child = tmp_path / 'child.cnf'; child.write_text('[mysqld]\n')
    root.write_bytes(b'\xa0!\tinclude\xa0child.cnf\xa0# comment\r\n[mysqld]\nkey=1\r!include absent\n')
    assert len(graph(root)['entries']) == 2


def test_native_file_directory_normalization_precedes_symlink_resolution(tmp_path):
    root = tmp_path / 'selected.cnf'; outside = tmp_path / 'outside'; outside.mkdir()
    (outside / 'link').symlink_to(tmp_path, target_is_directory=True)
    (tmp_path / 'leaf.cnf').write_text('[mysqld]\n')
    (outside / 'leaf.cnf').write_text('[mysqld]\nmax_connections=151\n')
    root.write_text('!include outside/link/../leaf.cnf\n!include absent/~/leaf.cnf\n')
    entries = graph(root)['entries']
    assert entries[1]['path'] == str(outside / 'leaf.cnf') and entries[1]['state'] == 'read'
    assert entries[2]['path'] == str(tmp_path / 'leaf.cnf') and entries[2]['state'] == 'read'


def test_native_includedir_does_not_expand_tilde_but_its_child_filename_does(tmp_path):
    root = tmp_path / 'selected.cnf'; literal = tmp_path / '~'; literal.mkdir()
    (literal / 'leaf.cnf').write_text('[mysqld]\nunknown_literal_path=1\n')
    (tmp_path / 'leaf.cnf').write_text('[mysqld]\n')
    root.write_text('!includedir ~\n')
    entries = graph(root)['entries']
    assert entries[1]['path'] == str(literal) and entries[1]['selected_names'] == ['leaf.cnf']
    assert entries[2]['path'] == str(tmp_path / 'leaf.cnf') and entries[2]['state'] == 'read'


def test_cycle_stops_at_native_tenth_recursion_level(tmp_path):
    root = tmp_path / 'selected.cnf'; root.write_text('!include selected.cnf\n')
    entries = graph(root)['entries']
    assert len(entries) == 11 and entries[-1]['depth'] == 10
    assert entries[-1]['directives_skipped_at_native_depth_limit'] == [1]


@pytest.mark.skipif(os.name == 'nt', reason='Native POSIX world-writable option-file rule')
def test_world_writable_file_is_not_traversed_but_mode_changes_invalidate_graph(tmp_path):
    root = tmp_path / 'selected.cnf'; root.write_text('!include absent.cnf\n'); root.chmod(0o666)
    before = graph(root); assert len(before['entries']) == 1
    assert before['entries'][0]['state'] == 'ignored_world_writable'
    root.chmod(0o600); assert graph(root) != before


@pytest.mark.parametrize('change', ['child-bytes', 'add', 'remove', 'retarget'])
def test_dependency_change_refuses_before_native_version_or_job_creation(host, change):
    root = host.configuration; directory = root.parent / 'parts'; directory.mkdir()
    child = directory / 'child.cnf'; child.write_text('[mysqld]\nmax_connections=151\n')
    other = root.parent / 'other'; other.mkdir(); (other / 'child.cnf').write_bytes(child.read_bytes())
    link = root.parent / 'selected-parts'; link.symlink_to(directory, target_is_directory=True)
    root.write_text('!includedir selected-parts\n')
    review = worker.dispatch(host.request)
    request = {**host.run, 'reviewed': review}; count = len(host.calls)
    if change == 'child-bytes': child.write_text('[mysqld]\nmax_connections=152\n')
    elif change == 'add': (directory / 'new.cnf').write_text('[mysqld]\n')
    elif change == 'remove': child.unlink()
    else: link.unlink(); link.symlink_to(other, target_is_directory=True)
    with pytest.raises(worker.Refused, match='changed after review'):
        worker.dispatch(request)
    assert len(host.calls) == count and not Path(host.run['workspace']).exists()


@pytest.mark.parametrize('kind', ['bytes', 'entries', 'nul', 'empty', 'nonregular'])
def test_partial_or_ambiguous_scan_cannot_be_admitted(tmp_path, monkeypatch, kind):
    root = tmp_path / 'selected.cnf'; root.write_text('[mysqld]\n')
    if kind == 'bytes': monkeypatch.setattr(worker, 'MAX_CONFIGURATION_BYTES', 2)
    elif kind == 'entries': monkeypatch.setattr(worker, 'MAX_CONFIGURATION_ENTRIES', 0)
    elif kind == 'nul': root.write_bytes(b'[mysqld]\n\0!include absent\n')
    elif kind == 'empty': root.write_text('!include # no argument\n')
    else: root.write_text('!include .\n')
    with pytest.raises(worker.Refused): graph(root)


@pytest.mark.parametrize('after', ['changed', 'unreadable'])
def test_native_process_receipt_survives_later_configuration_observation_failure(host, monkeypatch, after):
    original = worker.process; native_graph = worker.configuration_graph
    def execute(*args, **kwargs):
        result = original(*args, **kwargs)
        if '--validate-config' in args[1]:
            assert kwargs['configuration_context']['working_directory'] == str(host.configuration.parent)
            if after == 'changed': host.configuration.write_text('[mysqld]\nmax_connections=152\n')
            else:
                monkeypatch.setattr(worker, 'configuration_graph', lambda *a: (_ for _ in ()).throw(PermissionError()))
        return result
    monkeypatch.setattr(worker, 'process', execute)
    result = worker.dispatch(host.run)
    assert result['state'] == 'native_process_returned' and result['result']['return_code'] == 0
    observation = result['configuration_after_process']
    assert observation['observed'] == (after == 'changed')
    if after == 'changed': assert not observation['matches_review']
    else: assert observation['error_type'] == 'PermissionError'
    assert worker.dispatch({**host.run, 'action': 'status'}) == result
    monkeypatch.setattr(worker, 'configuration_graph', native_graph)


def test_root_symlink_retarget_with_identical_bytes_changes_the_review(host):
    selected = host.configuration; other = selected.parent / 'other.cnf'; other.write_bytes(selected.read_bytes())
    link = selected.parent / 'link.cnf'; link.symlink_to(selected)
    request = {**host.request, 'configuration_file': str(link)}
    review = worker.dispatch(request)
    link.unlink(); link.symlink_to(other)
    with pytest.raises(worker.Refused, match='changed after review'):
        worker.dispatch({**host.run, **request, 'action': 'validate_config', 'reviewed': review})


def test_native_process_uses_reviewed_cwd_and_home_and_private_temp_directory(tmp_path):
    working = tmp_path / 'configuration'; working.mkdir()
    workspace = tmp_path / 'private'; workspace.mkdir()
    context = {'working_directory': str(working), 'home_directory': str(working)}
    code = 'import os,json;print(json.dumps([os.getcwd(),os.environ["HOME"],os.environ.get("TMPDIR") or os.environ.get("TEMP")]))'
    result = worker.process(Path(sys.executable), ['-c', code], workspace, 10, configuration_context=context)
    assert result['return_code'] == 0
    values = json.loads(base64.b64decode(result['outputs']['stdout']['base64']))
    assert values == [str(working), str(working), str(workspace)]


@pytest.mark.skipif(not hasattr(os, 'mkfifo'), reason='Native POSIX FIFO replacement')
def test_file_replaced_by_fifo_before_open_is_refused_without_blocking(tmp_path, monkeypatch):
    selected = tmp_path / 'selected.cnf'; selected.write_text('[mysqld]\n')
    original = os.open
    def replaced(path, flags, *args, **kwargs):
        if Path(path) == selected:
            selected.unlink(); os.mkfifo(selected)
        return original(path, flags, *args, **kwargs)
    monkeypatch.setattr(worker.os, 'open', replaced)
    with pytest.raises(worker.Refused, match='not regular'):
        worker.file_hash(selected)
