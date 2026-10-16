##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Constrained provider-owned external administration tool execution.

The common runner validates grants and reports process observations. It does
not understand a database command, infer a remote transaction outcome, or
convert local process exit into remote finality. Providers own argument
construction and any post-state verification.
"""

from __future__ import annotations

import hashlib
import ntpath
import os
import re
import shutil
import tempfile
import sys
from dataclasses import dataclass
from pathlib import Path


MAX_TOOL_OUTPUT = 2 * 1024 * 1024


class ProviderToolError(RuntimeError):
    """An external provider tool grant or invocation is unsafe."""


def tool_environment(executable, workspace, *, platform=None, inherited=None):
    """Supply native OS requirements while isolating tool settings and secrets."""
    platform = sys.platform if platform is None else platform
    inherited = os.environ if inherited is None else inherited
    workspace, executable = str(workspace), str(executable)
    environment = {'LANG': 'C' if platform == 'darwin' else 'C.UTF-8',
                   'LC_ALL': 'C' if platform == 'darwin' else 'C.UTF-8'}
    if platform == 'win32':
        root = inherited.get('SYSTEMROOT') or inherited.get('SystemRoot')
        if not isinstance(root, str) or '\x00' in root or not ntpath.isabs(root):
            raise ProviderToolError('Windows native tools require an absolute SystemRoot')
        environment.update(SYSTEMROOT=root, WINDIR=root,
            PATH=';'.join((ntpath.dirname(executable), ntpath.join(root, 'System32'), root)),
            USERPROFILE=workspace, TEMP=workspace, TMP=workspace)
    else:
        environment.update(PATH=os.pathsep.join((str(Path(executable).parent), os.defpath)),
                           HOME=workspace, TMPDIR=workspace)
    return environment


def _safe_root(value):
    if not isinstance(value, str) or not value:
        raise ProviderToolError('tool workspace must be an absolute path')
    path = Path(value)
    if not path.is_absolute():
        raise ProviderToolError('tool workspace must be an absolute path')
    path = path.resolve(strict=False)
    forbidden = {Path(path.anchor), Path.home().resolve(strict=False)}
    if path in forbidden:
        raise ProviderToolError('tool workspace grant is over-broad')
    return path


@dataclass(frozen=True)
class ProviderToolGrant:
    """Explicit executable, filesystem, network, and resource authority."""

    executable_id: str
    workspace: str
    endpoint_host: str
    endpoint_port: int
    timeout_seconds: int | None = 300
    max_output_bytes: int = MAX_TOOL_OUTPUT
    secret_environment_names: tuple[str, ...] = ()
    allow_unbounded_runtime: bool = False

    def __post_init__(self):
        if not isinstance(self.executable_id, str) or not self.executable_id:
            raise ProviderToolError('tool executable ID is required')
        object.__setattr__(self, 'workspace', str(_safe_root(self.workspace)))
        if not isinstance(self.endpoint_host, str) or not self.endpoint_host:
            raise ProviderToolError('tool endpoint host is required')
        if isinstance(self.endpoint_port, bool) or not isinstance(
            self.endpoint_port, int
        ) or not 1 <= self.endpoint_port <= 65535:
            raise ProviderToolError('tool endpoint port is invalid')
        if type(self.allow_unbounded_runtime) is not bool:
            raise ProviderToolError('tool runtime authority is invalid')
        if (self.timeout_seconds is None and not self.allow_unbounded_runtime or
                self.timeout_seconds is not None and (type(self.timeout_seconds) is not int or
                not 1 <= self.timeout_seconds <= 2147483647)):
            raise ProviderToolError('tool timeout is invalid')
        if isinstance(self.max_output_bytes, bool) or not isinstance(
            self.max_output_bytes, int
        ) or not 1024 <= self.max_output_bytes <= MAX_TOOL_OUTPUT:
            raise ProviderToolError('tool output limit is invalid')
        if not isinstance(self.secret_environment_names, tuple) or any(
            not isinstance(name, str) or not name or
            not name.replace('_', '').isalnum() or name.upper() != name
            for name in self.secret_environment_names
        ):
            raise ProviderToolError(
                'tool secret environment grant is invalid'
            )


class ProviderToolRunner:
    """Run one allowlisted executable without a shell or inherited secrets."""

    def __init__(self, executable_allowlist):
        if not isinstance(executable_allowlist, dict):
            raise ProviderToolError('tool executable allowlist is invalid')
        self._allowlist = dict(executable_allowlist)

    def available(self):
        return {
            key: self._resolve(value) is not None
            for key, value in self._allowlist.items()
        }

    @staticmethod
    def _resolve(value):
        if not isinstance(value, str) or not value:
            return None
        candidate = value if os.path.isabs(value) else shutil.which(value)
        if candidate is None:
            return None
        # Preserve launcher identity: resolving a venv's python symlink first
        # discards its environment and can make native tool dependencies vanish.
        path = Path(os.path.abspath(candidate))
        return path if path.is_file() and os.access(path, os.X_OK) else None

    def run(
        self, grant, arguments, input_bytes=b'', input_path=None,
        secret_config=None,
        secret_argument='--config={path}', secret_suffix='.yaml',
        secret_argument_position=None, redact_values=(),
        secret_environment=None,
        progress=None, cancel_signal=None,
        secret_environment_name=None,
    ):
        if not isinstance(grant, ProviderToolGrant):
            raise ProviderToolError('provider tool grant is required')
        declared = self._allowlist.get(grant.executable_id)
        executable = self._resolve(declared)
        if executable is None:
            raise ProviderToolError('provider tool executable is unavailable')
        if not isinstance(arguments, (list, tuple)) or any(
            not isinstance(item, str) or '\x00' in item for item in arguments
        ):
            raise ProviderToolError('provider tool arguments are invalid')
        if not isinstance(input_bytes, (bytes, bytearray, memoryview)):
            raise ProviderToolError('provider tool input must be bytes')
        if progress is not None and not callable(progress):
            raise ProviderToolError('provider tool progress callback is invalid')
        if cancel_signal is not None and any(not callable(getattr(cancel_signal, name, None)) for name in ('is_set','wait')):
            raise ProviderToolError('provider tool cancellation signal is invalid')
        redactions = tuple(value for value in ((redact_values,) if isinstance(redact_values,str) else redact_values)
                           if isinstance(value,str) and value)
        workspace = Path(grant.workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        environment = tool_environment(executable, workspace)
        if secret_environment is not None:
            if not isinstance(secret_environment, dict) or any(
                not isinstance(key, str) or not key or '\x00' in key or
                not isinstance(value, str) or '\x00' in value
                for key, value in secret_environment.items()
            ):
                raise ProviderToolError(
                    'provider tool secret environment is invalid'
                )
            if not set(secret_environment).issubset(
                grant.secret_environment_names
            ):
                raise ProviderToolError(
                    'provider tool secret environment key is not granted'
                )
            if set(secret_environment).intersection(environment):
                raise ProviderToolError('Secret environment cannot replace native process settings')
            environment.update(secret_environment)
        if secret_environment_name is not None and (
                not isinstance(secret_environment_name,str) or
                secret_environment_name not in grant.secret_environment_names or
                secret_environment_name in environment or secret_config is None):
            raise ProviderToolError('provider tool secret file environment is not granted')
        input_stream = None
        if input_path is not None:
            if input_bytes:
                raise ProviderToolError(
                    'provider tool input path conflicts with input bytes'
                )
            if not isinstance(input_path, (str, os.PathLike)):
                raise ProviderToolError('provider tool input path is invalid')
            try:
                candidate = Path(input_path).resolve(strict=True)
            except OSError:
                raise ProviderToolError(
                    'provider tool input path is unavailable'
                ) from None
            try:
                candidate.relative_to(workspace)
            except ValueError:
                raise ProviderToolError(
                    'provider tool input path escapes the workspace'
                ) from None
            if candidate == workspace or not candidate.is_file():
                raise ProviderToolError('provider tool input path is invalid')
            input_stream = candidate.open('rb')
        config_path = None
        command = [str(executable), *arguments]
        try:
            if secret_config is not None:
                if not isinstance(secret_config, (bytes, bytearray)):
                    raise ProviderToolError(
                        'provider tool secret config must be bytes'
                    )
                descriptor, name = tempfile.mkstemp(
                    prefix='.cdeadmin-tool-', suffix=secret_suffix,
                    dir=workspace
                )
                config_path = Path(name)
                with os.fdopen(descriptor, 'wb') as stream:
                    from ..operations.fileio import private_file
                    private_file(config_path)
                    stream.write(bytes(secret_config))
                    stream.flush()
                    os.fsync(stream.fileno())
                if secret_environment_name is not None:
                    environment[secret_environment_name] = str(config_path)
                if secret_argument is None and secret_environment_name is not None:
                    secret_arguments = []
                elif isinstance(secret_argument, str):
                    secret_arguments = [secret_argument]
                elif (
                    isinstance(secret_argument, (list, tuple)) and
                    secret_argument and all(
                        isinstance(item, str) and item
                        for item in secret_argument
                    )
                ):
                    secret_arguments = list(secret_argument)
                else:
                    raise ProviderToolError(
                        'provider tool secret argument is invalid'
                    )
                if secret_arguments and sum(
                    item.count('{path}') for item in secret_arguments
                ) != 1:
                    raise ProviderToolError(
                        'provider tool secret argument is invalid'
                    )
                secret_options = [
                    item.format(path=config_path)
                    for item in secret_arguments
                ]
                if secret_argument_position is None:
                    command.extend(secret_options)
                elif (
                    isinstance(secret_argument_position, bool) or
                    not isinstance(secret_argument_position, int) or
                    not 0 <= secret_argument_position <= len(arguments)
                ):
                    raise ProviderToolError(
                        'provider tool secret argument position is invalid'
                    )
                else:
                    offset = 1 + secret_argument_position
                    command[offset:offset] = secret_options
            from .tool_process import observe_process, ToolProcessFailure
            secret_bytes = sorted({value.encode('utf8') for value in redactions}, key=len, reverse=True)
            try:
                observed = observe_process(command, workspace=workspace, environment=environment,
                    input_bytes=bytes(input_bytes), input_stream=input_stream, timeout=grant.timeout_seconds,
                    capture_limit=grant.max_output_bytes + max(map(len,secret_bytes),default=0),
                    cancel_signal=cancel_signal, progress=progress)
            except ToolProcessFailure as failure:
                observed = failure.observation
            def output_text(raw):
                if secret_bytes:
                    pattern = re.compile(b'|'.join(re.escape(value) for value in secret_bytes))
                    masked, end = bytearray(), 0
                    for match in pattern.finditer(raw):
                        if match.start() >= grant.max_output_bytes:break
                        remaining = grant.max_output_bytes-len(masked)
                        masked.extend(raw[end:match.start()][:remaining])
                        masked.extend(b'[redacted]'[:max(0,grant.max_output_bytes-len(masked))])
                        end=match.end()
                        if len(masked)>=grant.max_output_bytes:break
                    if end<grant.max_output_bytes:masked.extend(raw[end:grant.max_output_bytes][:max(0,grant.max_output_bytes-len(masked))])
                    raw=bytes(masked)
                return raw[:grant.max_output_bytes].decode('utf8',errors='replace')
            result = {
                'executable_id': grant.executable_id,
                'executable_sha256': hashlib.sha256(
                    executable.read_bytes()
                ).hexdigest(),
                'workspace': str(workspace),
                'execution_host': {'kind': 'application-host', 'platform': sys.platform,
                                   'filesystem_scope': str(workspace)},
                'network_grant': {
                    'host': grant.endpoint_host,
                    'port': grant.endpoint_port,
                },
                'return_code': observed['return_code'],
                'stdout': output_text(observed['stdout']),
                'stderr': output_text(observed['stderr']),
                'stdout_truncated': observed['stdout_bytes'] > grant.max_output_bytes,
                'stderr_truncated': observed['stderr_bytes'] > grant.max_output_bytes,
                'process_observation': {key:value for key,value in observed.items() if key not in {'stdout','stderr'}},
                'remote_finality_inferred': False,
                'local_process_observation_only': True,
            }
            if observed.get('supervision_error_type') or observed['timed_out'] or not observed['cleanup_confirmed']:
                error = ProviderToolError('provider tool output supervision failed' if observed.get('supervision_error_type') else
                                          'provider tool timed out' if observed['timed_out'] else
                                          'provider tool process cleanup is unconfirmed')
                error.process_observation = result
                raise error
            return result
        finally:
            if input_stream is not None:
                input_stream.close()
            if config_path is not None and config_path.exists():
                try:
                    size = config_path.stat().st_size
                    with config_path.open('r+b') as stream:
                        stream.write(b'\x00' * size)
                        stream.flush()
                        os.fsync(stream.fileno())
                finally:
                    config_path.unlink(missing_ok=True)
