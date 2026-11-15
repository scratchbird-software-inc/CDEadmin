"""Inspect or clear future SQLite host startup overrides without opening SQLite.

Recovery entry point when an accepted policy prevents application startup.
Use the application OS identity and an explicit absolute policy filename.
"""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'web'))
import sqlite_startup as codec


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('inspect','clear'))
    parser.add_argument('--policy',required=True,type=Path)
    parser.add_argument('--expected-revision')
    parser.add_argument('--confirm-clear',action='store_true')
    args=parser.parse_args(argv)
    if not args.policy.is_absolute():parser.error('--policy must be absolute')
    if args.operation=='inspect':
        policy,revision=codec.read_policy(args.policy)
        print(json.dumps({'policy':policy,'revision':revision,'native_dispatched':False},indent=2));return
    if not args.confirm_clear or not args.expected_revision:
        parser.error('clear requires --confirm-clear and the inspected --expected-revision')
    # Reuse the native OS advisory lock used by the application publisher.
    fileio=codec.component.file_io()
    lock_path=args.policy.with_name('.'+args.policy.name+'.lock')
    import os
    descriptor=os.open(lock_path,os.O_RDWR|os.O_CREAT|getattr(os,'O_NOFOLLOW',0),0o600)
    with os.fdopen(descriptor,'r+b')as lock:
        fileio.private_file(lock_path)
        with fileio.exclusive_file_lock(lock.fileno()):
            _,revision=codec.read_policy(args.policy)
            if revision!=args.expected_revision:raise RuntimeError('Policy changed; inspect again before clearing')
            codec.publish_policy_file(args.policy,(json.dumps({'schema':codec.SCHEMA,'settings':{}})+'\n').encode())
    print(json.dumps({'outcome':'overrides_cleared_for_next_startup','native_dispatched':False,
                      'running_process_changed':False,'restart_performed':False}))


if __name__=='__main__':main()
