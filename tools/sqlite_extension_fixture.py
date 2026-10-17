"""Build qualification-only native code outside the source checkout."""
import os
from pathlib import Path
import platform
import subprocess


def build(source, output, headers, *, definitions=()):
    output = Path(output)
    library = output.with_suffix('.dll' if os.name == 'nt' else '.so')
    env = dict(os.environ)
    if os.name == 'nt':
        from tools.development.native_assets import msvc
        env = msvc(env)
        command = ['cl.exe', '/nologo', '/LD', '/MD', '/O2', '/I' + str(headers),
                   *('/D' + value for value in definitions), str(source), '/link', '/OUT:' + str(library)]
    else:
        command = ['cc', *(['-dynamiclib'] if platform.system() == 'Darwin' else ['-shared', '-fPIC']),
                   '-I', str(headers), *('-D' + value for value in definitions), str(source), '-o', str(library)]
    with output.with_suffix('.compile.log').open('w') as log:
        subprocess.run(command, cwd=output.parent, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    return library
