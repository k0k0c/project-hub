"""Register an existing language server. No download, build or shell execution."""
import argparse
import json
from pathlib import Path
import platform


def jdtls_config(home, java='java', *, maven_import=False):
    """Build a declarative JDT LS provider configuration.

    Maven import is deliberately opt-in: enabling it lets JDT LS associate
    source files with an existing ``pom.xml`` project, but this helper never
    runs Maven or otherwise builds the project.
    """
    home=Path(home).resolve()
    launchers=sorted((home/'plugins').glob('org.eclipse.equinox.launcher_*.jar'))
    configuration=home/({'Windows':'config_win','Darwin':'config_mac'}.get(platform.system(),'config_linux'))
    if len(launchers)!=1 or not configuration.is_dir():
        raise ValueError('Expected an extracted Eclipse JDT LS installation with one launcher and platform configuration')
    settings={'java':{'import':{'gradle':{'enabled':False},'maven':{'enabled':bool(maven_import)}},'autobuild':{'enabled':False},'configuration':{'updateBuildConfiguration':'disabled'}}}
    return dict(id='jdtls',languages=['java'],timeout=60,command=[java,
                '-Declipse.application=org.eclipse.jdt.ls.core.id1','-Dosgi.bundles.defaultStartLevel=4',
                '-Declipse.product=org.eclipse.jdt.ls.core.product','-Xmx1G','--add-modules=ALL-SYSTEM',
                '--add-opens','java.base/java.util=ALL-UNNAMED','--add-opens','java.base/java.lang=ALL-UNNAMED',
                '-jar',str(launchers[0]),'-configuration',str(configuration),'-data','{workspace}'],
                settings=settings,initializationOptions={'settings':settings})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jdtls-home',required=True,type=Path)
    parser.add_argument('--java',default='java')
    parser.add_argument('--maven-import', action='store_true',
                        help='opt in to JDT LS Maven project import (does not run Maven)')
    parser.add_argument('--output',type=Path,help='Explicit language-servers.json destination; default prints configuration')
    args=parser.parse_args()
    provider=jdtls_config(args.jdtls_home,args.java,maven_import=args.maven_import)
    config={'providers':[]}
    if args.output and args.output.exists():config=json.loads(args.output.read_text(encoding='utf-8'))
    config['providers']=[p for p in config['providers'] if p.get('id')!=provider['id']]+[provider]
    text=json.dumps(config,ensure_ascii=False,indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(text,encoding='utf-8')
        print(json.dumps({'configured':provider['id'],'path':str(args.output.resolve())}))
    else:print(text)


if __name__=='__main__':main()
