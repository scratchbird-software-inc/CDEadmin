"""Install the pinned source-available MySQL online-copy script and license.

Native Perl with DBI and DBD::mysql must be installed on the execution host.
This installer does not change system packages or select an arbitrary tool.
"""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

REVISION='6fd7a1e7876a64e2ca164f02e170619bf5df3236'
FILES={'bin/pt-online-schema-change':'d24341d04ca7650e4d11c8b413e89f032d06e700db452b0c2edbfa61c2883896',
    'COPYING':'8177f97513213526df2cf6184d8ff986c675afb514d4e68a404010521b880643'}


def install(destination):
    destination=Path(destination).resolve();destination.mkdir(parents=True,exist_ok=True)
    manifest={'source':'https://github.com/percona/percona-toolkit','revision':REVISION,'version':'3.7.2','files':{}}
    for name,expected in FILES.items():
        with urllib.request.urlopen('https://raw.githubusercontent.com/percona/percona-toolkit/'+REVISION+'/'+name,timeout=30) as response:
            data=response.read(1024*1024+1)
        actual=hashlib.sha256(data).hexdigest()
        if len(data)>1024*1024 or actual!=expected:raise ValueError('The pinned native utility artifact changed')
        path=destination/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
        manifest['files'][name]=actual
    (destination/'provenance.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--destination',required=True);args=parser.parse_args()
    print(json.dumps(install(args.destination),indent=2))
