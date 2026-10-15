"""Collect and reconcile one clean Firebird candidate across four native hosts.

Run with the candidate's qualified Python environment on Linux x64. GitHub
credentials belong to gh; they are never copied into receipts or child routes.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from tools.firebird_release_evidence import (
    ROOT,
    compose,
    host_id,
    inspect_receipt,
    source_snapshot,
)

REPOSITORY = "scratchbird-software-inc/CDEadmin"
WORKFLOW = ".github/workflows/native-development.yml"
RUNNERS = {
    "windows-x64": "windows-2025",
    "macos-x64": "macos-15-intel",
    "macos-arm64": "macos-15",
}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def api(endpoint):
    result = subprocess.run(
        ["gh", "api", f"repos/{REPOSITORY}/{endpoint}"],
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return json.loads(result.stdout)


def run_errors(run, run_id, candidate):
    errors = []
    if (
        run.get("id") != run_id or
        run.get("head_sha") != candidate["revision"] or
        run.get("path") != WORKFLOW or
        run.get("event") != "workflow_dispatch" or
        run.get("repository", {}).get("full_name") != REPOSITORY or
        run.get("head_repository", {}).get("full_name") != REPOSITORY
    ):
        errors.append(
            "GitHub run is not the native workflow for this candidate "
            "and repository"
        )
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        errors.append("GitHub native run did not complete successfully")
    return errors


def select_artifacts(inventory, run, candidate):
    """Never select the newest artifact by prefix or silently reuse a rerun."""
    selected = {}
    failures = []
    for host, runner in RUNNERS.items():
        name = f"native-{runner}-{candidate['revision']}-{run['run_attempt']}"
        matches = [item for item in inventory if item.get("name") == name]
        if len(matches) != 1:
            failures.append(
                {
                    "host": host,
                    "reason": "missing or duplicate current-attempt "
                    "native artifact",
                }
            )
            continue
        item = matches[0]
        binding = item.get("workflow_run", {})
        if (
            item.get("expired") is not False or
            not item.get("id") or
            binding.get("id") != run["id"] or
            binding.get("head_sha") != candidate["revision"] or
            binding.get("repository_id") != run["repository"]["id"] or
            binding.get("head_repository_id") != run["repository"]["id"]
        ):
            failures.append(
                {
                    "host": host,
                    "reason": "native artifact provenance or "
                    "retention differs",
                }
            )
            continue
        selected[host] = item
    return selected, failures


def platform_binding(value, host, candidate, run=None):
    errors = []
    source = value.get("source", {})
    if (
        value.get("host") != host or
        source.get("revision") != candidate["revision"] or
        source.get("status") != "" or
        source.get("sha256") != candidate["sha256"] or
        source.get("ddn_revision") != candidate["ddn_revision"] or
        source.get("ddn_artifacts") != candidate["ddn_artifacts"]
    ):
        errors.append(
            "native host, clean source or DDN binding differs "
            "from this candidate"
        )
    if run is not None:
        observed = value.get("github", {})
        expected = {
            "GITHUB_REPOSITORY": REPOSITORY,
            "GITHUB_SHA": candidate["revision"],
            "GITHUB_RUN_ID": str(run["id"]),
            "GITHUB_RUN_ATTEMPT": str(run["run_attempt"]),
        }
        if any(observed.get(key) != item for key, item in expected.items()):
            errors.append(
                "native receipt belongs to a different GitHub run or attempt"
            )
    return errors


def copy_linux_receipt(path, target, candidate):
    """Copy verified public artifacts without owned runtimes or keys."""
    value, errors = inspect_receipt(path, candidate["sha256"])
    errors += platform_binding(value, "linux-x64", candidate)
    if errors:
        raise ValueError("; ".join(errors))
    target.mkdir()
    shutil.copyfile(path, target / "platform.json")
    for relative in value["artifacts"]:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path.parent / relative, destination)
    return target / "platform.json"


def collect_native(run_id, candidate, evidence, *, wait_seconds):
    failures, paths = [], []
    run = api(f"actions/runs/{run_id}")
    attempt = run['run_attempt']
    write(evidence / "github-run-initial.json", run)
    write(evidence / "github-run.json", run)
    # A mismatched run must not spend hours waiting or download foreign
    # evidence.
    identity_errors = run_errors(
        dict(run, status="completed", conclusion="success"), run_id, candidate
    )
    if identity_errors:
        return [], [
            {"scope": "github", "reason": error} for error in identity_errors
        ]
    deadline = time.monotonic() + wait_seconds
    while run.get("status") != "completed" and time.monotonic() < deadline:
        time.sleep(min(30, max(0, deadline - time.monotonic())))
        run = api(f"actions/runs/{run_id}")
        write(evidence / "github-run.json", run)
        if run.get('run_attempt') != attempt or run_errors(
            dict(run, status="completed", conclusion="success"),
            run_id,
            candidate,
        ):
            return [], [
                {
                    "scope": "github",
                    "reason": "GitHub run identity changed while waiting",
                }
            ]
    failures.extend(
        {"scope": "github", "reason": error}
        for error in run_errors(run, run_id, candidate)
    )
    inventory = api(f"actions/runs/{run_id}/artifacts?per_page=100")
    write(evidence / "github-artifacts.json", inventory)
    selected, errors = select_artifacts(
        inventory.get("artifacts", []), run, candidate
    )
    failures.extend(errors)
    for host, item in selected.items():
        target = evidence / host
        target.mkdir()
        try:
            with (evidence / (host + "-download.log")).open(
                "w", encoding="utf-8"
            ) as log:
                subprocess.run(
                    [
                        "gh",
                        "run",
                        "download",
                        str(run_id),
                        "--repo",
                        REPOSITORY,
                        "--name",
                        item["name"],
                        "--dir",
                        str(target),
                    ],
                    check=True,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    timeout=600,
                )
            path = target / "firebird-platform/platform.json"
            value = json.loads(path.read_text(encoding="utf-8"))
            failures.extend(
                {"host": host, "reason": error}
                for error in platform_binding(value, host, candidate, run)
            )
            paths.append(path)
        except (
            OSError,
            ValueError,
            TypeError,
            AttributeError,
            subprocess.SubprocessError,
        ) as error:
            failures.append(
                {
                    "host": host,
                    "reason": "native artifact download or receipt failed",
                    "error_type": type(error).__name__,
                }
            )
    try:
        after = api(f"actions/runs/{run_id}")
        write(evidence / "github-run-after.json", after)
        if after.get("run_attempt") != attempt or run_errors(
            after, run_id, candidate
        ):
            failures.append(
                {
                    "scope": "github",
                    "reason": "GitHub run changed during artifact capture",
                }
            )
    except (OSError, ValueError, TypeError, AttributeError,
            subprocess.SubprocessError) as error:
        failures.append(
            {
                "scope": "github",
                "reason": "GitHub run could not be rechecked after capture",
                "error_type": type(error).__name__,
            }
        )
    return paths, failures


def qualify(
    run_id, evidence, *, runtime=None, linux_receipt=None, wait_seconds=0
):
    evidence = Path(evidence).resolve()
    if host_id() != "linux-x64":
        raise ValueError(
            "Run candidate collection on the actual Linux x64 host"
        )
    if evidence.is_relative_to(ROOT):
        raise ValueError("Keep release evidence outside the repository")
    if (runtime is None) == (linux_receipt is None):
        raise ValueError(
            "Select a native runtime or an existing exact-candidate "
            "Linux receipt"
        )
    candidate = source_snapshot()
    if candidate["status"]:
        raise ValueError(
            "Release candidates require a clean committed source snapshot"
        )
    evidence.mkdir(parents=True, exist_ok=False)
    write(evidence / "candidate.json", candidate)
    failures, paths = [], []
    if linux_receipt is not None:
        try:
            paths.append(
                copy_linux_receipt(
                    Path(linux_receipt).resolve(),
                    evidence / "linux-x64",
                    candidate,
                )
            )
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
        ) as error:
            failures.append(
                {
                    "host": "linux-x64",
                    "reason": "existing Linux qualification refused",
                    "error_type": type(error).__name__,
                }
            )
    else:
        try:
            from tools.development.native import command
            command(
                [
                    sys.executable,
                    "-m",
                    "tools.development.firebird_platform",
                    "--runtime-root",
                    str(Path(runtime).resolve()),
                    "--evidence",
                    str(evidence / "linux-x64"),
                ],
                cwd=ROOT,
                env=dict(os.environ, PYTHONFAULTHANDLER="1"),
                log=evidence / "linux-qualification.log",
                timeout=14400,
            )
        except (OSError, subprocess.SubprocessError) as error:
            failures.append(
                {
                    "host": "linux-x64",
                    "reason": "Linux native qualification failed",
                    "error_type": type(error).__name__,
                }
            )
            try:
                sys.path.insert(0, str(ROOT / 'tools/development'))
                from tools.development.native_fixtures import (
                    cleanup_crashed_fixture)
                cleanup_crashed_fixture(evidence / 'linux-x64/server')
            except Exception as cleanup_error:
                failures.append({
                    'host': 'linux-x64',
                    'reason': 'owned server cleanup failed',
                    'error_type': type(cleanup_error).__name__})
        path = evidence / "linux-x64/platform.json"
        if path.is_file():
            paths.append(path)
    # Preserve all hosts even when Linux or a GitHub job fails.
    try:
        remote_paths, remote_failures = collect_native(
            run_id, candidate, evidence, wait_seconds=wait_seconds
        )
        paths.extend(remote_paths)
        failures.extend(remote_failures)
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        subprocess.SubprocessError,
    ) as error:
        failures.append(
            {
                "scope": "github",
                "reason": "GitHub evidence collection failed",
                "error_type": type(error).__name__,
            }
        )
    after = source_snapshot()
    write(evidence / "candidate-after.json", after)
    if any(
        after[key] != candidate[key]
        for key in ("sha256", "revision", "status")
    ):
        failures.append(
            {
                "scope": "source",
                "reason": "candidate changed during qualification",
            }
        )
    result = compose(paths, candidate["sha256"])
    result["failures"].extend(failures)
    result["complete"] = result["backend_platform_qualified"] = not result[
        "failures"
    ]
    result["candidate_revision"] = candidate["revision"]
    result["github_run_id"] = run_id
    result["receipt_sha256"] = {
        str(path.relative_to(evidence)): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in paths
    }
    write(evidence / "release.json", result)
    lines = [
        "# Firebird release candidate",
        "",
        f"Candidate: `{candidate['revision']}`",
        "",
        "Backend platform qualified: " + str(
            result['backend_platform_qualified']),
        "",
        "| Host | Native evidence |",
        "| --- | --- |",
    ]
    for host in ("linux-x64", *RUNNERS):
        errors = result["platforms"].get(host, {}).get("errors")
        host_failures = [
            item for item in result["failures"] if item.get("host") == host
        ]
        state = (
            "passed"
            if errors == [] and not host_failures
            else "incomplete/failed"
        )
        lines.append(f"| {host} | {state} |")
    lines += [
        "",
        "Product release approved: false",
        "",
        "Separate acceptance:",
        "",
    ]
    lines += ["- " + item for item in result["separate_acceptance"]]
    lines += ["", "Failures:", ""] + [
        "- " + item["reason"] for item in result["failures"]
    ]
    (evidence / "summary.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-run", type=int, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    local = parser.add_mutually_exclusive_group(required=True)
    local.add_argument("--runtime-root", type=Path)
    local.add_argument("--linux-receipt", type=Path)
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=0,
        help="Wait up to this many seconds for the selected GitHub run",
    )
    args = parser.parse_args()
    if args.native_run <= 0 or not 0 <= args.wait_seconds <= 21600:
        parser.error(
            "Use a positive run ID and a wait budget between "
            "0 and 21600 seconds"
        )
    result = qualify(
        args.native_run,
        args.evidence,
        runtime=args.runtime_root,
        linux_receipt=args.linux_receipt,
        wait_seconds=args.wait_seconds,
    )
    print(
        json.dumps(
            {
                "complete": result["complete"],
                "failures": result["failures"],
                "evidence": str(args.evidence),
            },
            indent=2,
        )
    )
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
