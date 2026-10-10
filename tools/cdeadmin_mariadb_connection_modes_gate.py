"""Native compressed and pre-session failover MariaDB execution qualification.
"""
import argparse
import json
from pathlib import Path

from tools.cdeadmin_mariadb_driver_gate import run
from tools.cdeadmin_mariadb_execution_gate import qualify as execution


def qualify(route, evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    results = {}
    results['compressed'] = execution(
        dict(route, compress=True), evidence / 'compressed',
        reply_loss=False)['complete']
    results['failover'] = execution(
        dict(
            route,
            host=f"127.0.0.1:1,{
                route['host']}:{
                route['port']}"),
        evidence /
        'failover',
        reply_loss=False)['complete']
    proof = {'complete': all(results.values()), 'scopes': results}
    (evidence / 'summary.json').write_text(json.dumps(proof, indent=2))
    return proof


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='mariadb:12.2.2')
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.image, args.evidence, qualify, tls=True)
    raise SystemExit(0 if result['complete'] else 1)
