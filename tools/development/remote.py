"""macOS/Windows/Linux SSH launcher for an existing Linux development VM."""
import argparse
import shlex
import subprocess


def command(host, repository, arguments):
    if host.startswith('-') or not repository.startswith('/'):
        raise ValueError('Use an SSH host alias and an absolute guest path')
    remote = shlex.join(['bash', repository.rstrip('/') +
                         '/tools/development/dev.sh', *arguments])
    return ['ssh', '-t', host, remote]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('host', help='SSH alias or user@host')
    parser.add_argument('repository', help='Absolute repository path in VM')
    parser.add_argument('arguments', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    return subprocess.call(command(
        args.host, args.repository, args.arguments or ['doctor']))


if __name__ == '__main__':
    raise SystemExit(main())
