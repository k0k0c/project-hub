"""Standalone local Knowledge API client. Input/output are explicit files or JSON."""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.parse import urlencode, urlparse


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--project',required=True)
    parser.add_argument('--action',required=True)
    parser.add_argument('--args-file',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--public',action='store_true')
    options=parser.parse_args()
    endpoint=urlparse(options.url)
    if endpoint.scheme!='http' or endpoint.hostname not in ('localhost','127.0.0.1') or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment:
        parser.error('Use a local Hub HTTP URL')
    if options.action in ('download','backup'):
        path='/api/v1/knowledge/download?'+urlencode(dict(project=options.project,action='backup' if options.action=='backup' else 'export',public=str(options.public).lower()))
        request=Request(options.url.rstrip('/')+path)
        if not options.output: parser.error('Downloads require --output')
    else:
        arguments=json.loads(options.args_file.read_text(encoding='utf-8-sig')) if options.args_file else {}
        request=Request(options.url.rstrip('/')+'/api/v1/knowledge?'+urlencode(dict(project=options.project)),
                        data=json.dumps(dict(action=options.action,args=arguments),ensure_ascii=False).encode(),headers={'Content-Type':'application/json'})
    with urlopen(request,timeout=30) as response: data=response.read(64_000_001)
    if len(data)>64_000_000: raise ValueError('Response exceeds local client limit')
    if options.output: options.output.write_bytes(data)
    else: print(json.dumps(json.loads(data),ensure_ascii=False,indent=2))


if __name__=='__main__': main()
