"""PostgreSQL native psycopg_pool connection-pool adapter & generation retirement (PG-AUDIT-POOL-01).

Implements optional `psycopg_pool.ConnectionPool` management for the PostgreSQL
provider and endpoint adapter so every declared `pooling` capability (`min_size`,
`max_size`, `acquisition_timeout`, `queue_limit`, `lifetime`, `idle_timeout`,
`checkout_validation`, `background_reconnect_window`, and `generation_based_pool_retirement`)
is backed by actual PostgreSQL adapter implementation and native verification.
"""
from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import threading
import time

from psycopg.conninfo import make_conninfo
from psycopg_pool import ConnectionPool, PoolTimeout


class PostgreSQLPoolError(RuntimeError):
    """Raised when PostgreSQL pool configuration, acquisition, or validation fails."""


POOL_DEFAULTS = {
    'enabled': False,
    'min_size': 1,
    'max_size': 4,
    'acquisition_timeout': 10.0,
    'queue_limit': 16,
    'lifetime': 3600.0,
    'idle_timeout': 600.0,
    'checkout_validation': True,
    'background_reconnect_window': 30.0,
}


def normalize_pool_policy(raw: dict | None) -> dict:
    if raw is None:
        return deepcopy(POOL_DEFAULTS)
    if not isinstance(raw, dict) or set(raw) - set(POOL_DEFAULTS):
        raise PostgreSQLPoolError('Unsupported PostgreSQL pool policy fields')
    merged = {**POOL_DEFAULTS, **raw}
    if type(merged['enabled']) is not bool or type(merged['checkout_validation']) is not bool:
        raise PostgreSQLPoolError('Pool enabled and checkout_validation flags must be booleans')
    for key in ('min_size', 'max_size', 'queue_limit'):
        if type(merged[key]) is not int or merged[key] < 0:
            raise PostgreSQLPoolError(f'Pool {key} must be a non-negative integer')
    if merged['max_size'] < 1 or merged['min_size'] > merged['max_size']:
        raise PostgreSQLPoolError('Pool requires 0 <= min_size <= max_size and max_size >= 1')
    if merged['queue_limit'] < 1:
        raise PostgreSQLPoolError('Pool queue_limit must be >= 1')
    for key in ('acquisition_timeout', 'lifetime', 'idle_timeout', 'background_reconnect_window'):
        val = merged[key]
        if isinstance(val, bool) or not isinstance(val, (int, float)) or float(val) <= 0:
            raise PostgreSQLPoolError(f'Pool {key} must be a positive number of seconds')
        merged[key] = float(val)
    return merged


class PostgreSQLConnectionPoolRegistry:
    """Thread-safe generation-keyed `psycopg_pool.ConnectionPool` registry."""

    def __init__(self):
        self._lock = threading.RLock()
        self._pools: dict[tuple[str, str], dict] = {}
        self._retired: list[dict] = []

    def configure_or_get(
        self,
        endpoint_id: str,
        generation: str,
        conn_params: dict,
        policy: dict | None = None,
    ) -> ConnectionPool:
        normalized = normalize_pool_policy(policy if policy is not None else {'enabled': True})
        if not normalized['enabled']:
            raise PostgreSQLPoolError('Optional psycopg_pool is disabled on this policy')
        key = (str(endpoint_id), str(generation))
        with self._lock:
            # Retire any older generation pools for this endpoint immediately!
            stale_keys = [k for k in self._pools if k[0] == str(endpoint_id) and k[1] != str(generation)]
            for sk in stale_keys:
                self._retire_locked(sk, reason='generation_superseded')
            existing = self._pools.get(key)
            if existing is not None:
                return existing['pool']

            safe_kwargs = {k: v for k, v in conn_params.items() if v is not None}
            conninfo = make_conninfo(**safe_kwargs)
            pool = ConnectionPool(
                conninfo=conninfo,
                min_size=normalized['min_size'],
                max_size=normalized['max_size'],
                timeout=normalized['acquisition_timeout'],
                max_waiting=normalized['queue_limit'],
                max_lifetime=normalized['lifetime'],
                max_idle=normalized['idle_timeout'],
                reconnect_timeout=normalized['background_reconnect_window'],
                check=ConnectionPool.check_connection if normalized['checkout_validation'] else None,
                kwargs={'autocommit': True},
                open=True,
            )
            if normalized['min_size'] > 0:
                pool.wait(timeout=normalized['acquisition_timeout'])
            self._pools[key] = {
                'endpoint_id': str(endpoint_id),
                'generation': str(generation),
                'policy': normalized,
                'pool': pool,
                'created_at': time.time(),
            }
            return pool

    @contextmanager
    def connection(
        self,
        endpoint_id: str,
        generation: str,
        conn_params: dict,
        policy: dict | None = None,
        *,
        timeout: float | None = None,
    ):
        pool = self.configure_or_get(endpoint_id, generation, conn_params, policy)
        try:
            with pool.connection(timeout=timeout) as conn:
                yield conn
        except PoolTimeout as err:
            raise PostgreSQLPoolError(f'PostgreSQL pool acquisition timed out or exceeded queue limit: {err}') from None

    def _retire_locked(self, key: tuple[str, str], *, reason: str) -> dict | None:
        entry = self._pools.pop(key, None)
        if entry is None:
            return None
        pool: ConnectionPool = entry['pool']
        pool.close()
        receipt = {
            'endpoint_id': entry['endpoint_id'],
            'generation': entry['generation'],
            'reason': reason,
            'retired_at': time.time(),
            'closed': pool.closed,
        }
        self._retired.append(receipt)
        del self._retired[:-50]
        return receipt

    def retire_endpoint(self, endpoint_id: str, *, reason: str = 'explicit_retirement') -> list[dict]:
        with self._lock:
            keys = [k for k in self._pools if k[0] == str(endpoint_id)]
            return [r for k in keys if (r := self._retire_locked(k, reason=reason)) is not None]

    def stats(self, endpoint_id: str, generation: str | None = None) -> dict:
        with self._lock:
            active = []
            for (ep, gen), entry in self._pools.items():
                if ep == str(endpoint_id) and (generation is None or gen == str(generation)):
                    pool: ConnectionPool = entry['pool']
                    active.append({
                        'endpoint_id': ep,
                        'generation': gen,
                        'policy': deepcopy(entry['policy']),
                        'closed': pool.closed,
                        'stats': dict(pool.get_stats()),
                    })
            retired = [deepcopy(r) for r in self._retired if r['endpoint_id'] == str(endpoint_id)]
            return {'active_pools': active, 'retired_generations': retired}

    def close_all(self) -> None:
        with self._lock:
            for key in list(self._pools):
                self._retire_locked(key, reason='provider_shutdown')
