"""Reject stale release evidence and retain independent host failures."""

import json
import shutil
import subprocess

import pytest

from tools import firebird_release_candidate as candidate
from tools.tests.test_firebird_release_evidence import (
    SOURCE,
    digest,
    platform_proof,
    write,
)


def snapshot():
    return {
        "revision": "c" * 40,
        "status": "",
        "sha256": digest(SOURCE),
        "files": SOURCE,
        "ddn_revision": "d" * 40,
        "ddn_artifacts": {"ddn.js": "a" * 64},
    }


def run():
    return {
        "id": 123,
        "head_sha": "c" * 40,
        "path": candidate.WORKFLOW,
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
        "run_attempt": 2,
        "repository": {"full_name": candidate.REPOSITORY, "id": 456},
        "head_repository": {"full_name": candidate.REPOSITORY},
    }


def bind(path, host, remote=False):
    value = json.loads(path.read_text())
    value["source"] = snapshot()
    if remote:
        value["github"] = {
            "GITHUB_REPOSITORY": candidate.REPOSITORY,
            "GITHUB_SHA": "c" * 40,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "2",
        }
    write(path, value)
    return path


@pytest.fixture
def collection(tmp_path, monkeypatch):
    captured = snapshot()
    selected_run = run()
    artifacts, archive_paths = [], {}
    for number, (host, runner) in enumerate(candidate.RUNNERS.items()):
        name = f"native-{runner}-{captured['revision']}-2"
        path = platform_proof(
            tmp_path / "archives" / host / "firebird-platform", host
        )
        bind(path, host, remote=True)
        artifacts.append(
            {
                "id": number + 10,
                "name": name,
                "expired": False,
                "workflow_run": {
                    "id": 123,
                    "head_sha": captured["revision"],
                    "repository_id": 456,
                    "head_repository_id": 456,
                },
            }
        )
        archive_paths[name] = path.parent.parent
    local = bind(platform_proof(tmp_path / "local", "linux-x64"), "linux-x64")
    calls = []

    def fake_api(endpoint):
        calls.append(endpoint)
        return (
            {"artifacts": artifacts}
            if "/artifacts?" in endpoint
            else selected_run
        )

    def download(args, **kwargs):
        name, target = (
            args[args.index("--name") + 1],
            args[args.index("--dir") + 1],
        )
        shutil.copytree(archive_paths[name], target, dirs_exist_ok=True)
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(candidate, "source_snapshot", lambda: captured)
    monkeypatch.setattr(candidate, "host_id", lambda: "linux-x64")
    monkeypatch.setattr(candidate, "api", fake_api)
    monkeypatch.setattr(candidate.subprocess, "run", download)
    return {
        "snapshot": captured,
        "run": selected_run,
        "artifacts": artifacts,
        "archives": archive_paths,
        "local": local,
        "calls": calls,
    }


def test_collects_exact_candidate_and_preserves_product_boundaries(
    tmp_path, collection
):
    evidence = tmp_path / "release"
    result = candidate.qualify(
        123, evidence, linux_receipt=collection["local"]
    )
    assert result["complete"] and result["backend_platform_qualified"]
    assert not result["product_release_approved"]
    assert len(result["receipt_sha256"]) == 4
    assert all(not item["errors"] for item in result["platforms"].values())
    assert json.loads((evidence / "release.json").read_text()) == result
    assert "human form validation" in (evidence / "summary.md").read_text()
    assert not list(evidence.rglob("*.fdb"))


@pytest.mark.parametrize(
    "change",
    [
        {"head_sha": "e" * 40},
        {"path": ".github/workflows/other.yml"},
        {"id": 999},
        {"event": "pull_request"},
        {"repository": {"full_name": "someone/fork", "id": 456}},
        {"head_repository": {"full_name": "someone/fork"}},
    ],
)
def test_foreign_or_stale_run_is_refused_without_download(
    tmp_path, collection, change
):
    collection["run"].update(change)
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert not any("/artifacts?" in item for item in collection["calls"])
    assert result["platforms"]["linux-x64"]["errors"] == []


@pytest.mark.parametrize(
    "change",
    [
        {"expired": True},
        {"name": "native-windows-2025-" + "c" * 40 + "-1"},
        {"workflow_run": {"id": 999}},
        {"workflow_run": {"id": 123, "head_sha": "e" * 40}},
    ],
)
def test_expired_or_wrong_attempt_artifact_cannot_fill_host(
    tmp_path, collection, change
):
    collection["artifacts"][0].update(change)
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert "windows-x64" not in result["platforms"]
    assert result["platforms"]["macos-x64"]["errors"] == []


def test_duplicate_artifact_is_ambiguous(tmp_path, collection):
    collection["artifacts"].append(collection["artifacts"][0].copy())
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert any("duplicate" in item["reason"] for item in result["failures"])


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("source", "revision", "e" * 40),
        ("source", "status", " M provider.py"),
        ("source", "ddn_revision", "e" * 40),
        ("source", "ddn_artifacts", {}),
        ("github", "GITHUB_RUN_ID", "999"),
        ("github", "GITHUB_RUN_ATTEMPT", "1"),
        ("github", "GITHUB_REPOSITORY", "someone/fork"),
    ],
)
def test_rehashed_receipt_still_needs_run_and_dependency_binding(
    tmp_path, collection, section, key, value
):
    archive = next(iter(collection["archives"].values()))
    path = archive / "firebird-platform/platform.json"
    data = json.loads(path.read_text())
    data[section][key] = value
    write(path, data)
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert any(
        item.get("host") == "windows-x64" for item in result["failures"]
    )


def test_download_failure_does_not_discard_other_hosts(
    tmp_path, collection, monkeypatch
):
    original = candidate.subprocess.run

    def fail_one(args, **kwargs):
        if "windows-2025" in args[args.index("--name") + 1]:
            raise subprocess.TimeoutExpired("gh", 600)
        return original(args, **kwargs)

    monkeypatch.setattr(candidate.subprocess, "run", fail_one)
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert result["platforms"]["macos-x64"]["errors"] == []
    assert result["platforms"]["macos-arm64"]["errors"] == []


def test_tampered_linux_receipt_does_not_skip_native_inventory(
    tmp_path, collection
):
    (collection["local"].parent / "network/driver/summary.json").write_text(
        "{}"
    )
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert set(result["platforms"]) == set(candidate.RUNNERS)


def test_failed_run_preserves_successful_native_receipts(tmp_path, collection):
    collection["run"]["conclusion"] = "failure"
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert len(result["platforms"]) == 4
    assert any(
        "did not complete" in item["reason"] for item in result["failures"]
    )


def test_run_rerun_during_download_is_refused(
    tmp_path, collection, monkeypatch
):
    original = candidate.api
    queries = []

    def rerun(endpoint):
        value = original(endpoint)
        if endpoint == "actions/runs/123":
            queries.append(endpoint)
            if len(queries) == 2:
                return dict(value, run_attempt=3)
        return value

    monkeypatch.setattr(candidate, "api", rerun)
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert any(
        "changed during artifact capture" in item["reason"]
        for item in result["failures"]
    )


def test_dirty_source_is_refused_before_writing_or_network_access(
    tmp_path, collection
):
    collection["snapshot"]["status"] = " M example.jsx"
    with pytest.raises(ValueError, match="clean committed"):
        candidate.qualify(
            123, tmp_path / "release", linux_receipt=collection["local"]
        )
    assert not collection["calls"] and not (tmp_path / "release").exists()


def test_changed_candidate_cannot_qualify(tmp_path, collection, monkeypatch):
    calls = []

    def changing_source():
        calls.append(True)
        return (
            collection["snapshot"]
            if len(calls) == 1
            else dict(collection["snapshot"], revision="e" * 40)
        )

    monkeypatch.setattr(candidate, "source_snapshot", changing_source)
    result = candidate.qualify(
        123, tmp_path / "release", linux_receipt=collection["local"]
    )
    assert not result["complete"]
    assert any(
        "candidate changed" in item["reason"] for item in result["failures"]
    )


def test_existing_evidence_is_never_overwritten(tmp_path, collection):
    target = tmp_path / "release"
    target.mkdir()
    (target / "marker").write_text("retained")
    with pytest.raises(FileExistsError):
        candidate.qualify(123, target, linux_receipt=collection["local"])
    assert (target / "marker").read_text() == "retained"


def test_failed_final_api_check_preserves_downloaded_receipts(
        tmp_path, collection, monkeypatch):
    original = candidate.api
    queries = []

    def disconnect(endpoint):
        if endpoint == 'actions/runs/123':
            queries.append(endpoint)
            if len(queries) == 2:
                raise subprocess.TimeoutExpired('gh', 120)
        return original(endpoint)

    monkeypatch.setattr(candidate, 'api', disconnect)
    result = candidate.qualify(
        123, tmp_path / 'release', linux_receipt=collection['local'])
    assert not result['complete']
    assert len(result['platforms']) == 4
    assert any('could not be rechecked' in item['reason']
               for item in result['failures'])


@pytest.mark.parametrize('rerun', [False, True])
def test_wait_for_completion_keeps_original_attempt(
        tmp_path, collection, monkeypatch, rerun):
    original = candidate.api
    queries = []

    def progress(endpoint):
        value = original(endpoint)
        if endpoint == 'actions/runs/123':
            queries.append(endpoint)
            if len(queries) == 1:
                return dict(value, status='in_progress', conclusion=None)
            if rerun:
                return dict(value, run_attempt=3)
        return value

    monkeypatch.setattr(candidate, 'api', progress)
    monkeypatch.setattr(candidate.time, 'sleep', lambda _: None)
    result = candidate.qualify(
        123, tmp_path / 'release', linux_receipt=collection['local'],
        wait_seconds=60)
    assert result['complete'] is not rerun
    if rerun:
        assert not any(
            '/artifacts?' in item for item in collection['calls'])


def test_github_transport_uses_exact_endpoint_without_a_shell(monkeypatch):
    calls = []

    def execute(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, stdout='{"id":123}')

    monkeypatch.setattr(candidate.subprocess, 'run', execute)
    assert candidate.api('actions/runs/123') == {'id': 123}
    assert calls[0][0] == [
        'gh', 'api',
        'repos/scratchbird-software-inc/CDEadmin/actions/runs/123']
    assert 'shell' not in calls[0][1]
