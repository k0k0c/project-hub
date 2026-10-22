"""Small command-line client for a local Project Hub connection."""
import argparse
import json
import sys
from pathlib import Path

from agent_sdk import Client, SDKError, generic_mcp_config, load_connection, save_connection, _absolute_path, mcp_server_name, mcp_http_endpoint


def _parser():
    parser = argparse.ArgumentParser(prog='hub-cli')
    sub = parser.add_subparsers(dest='command', required=True)
    connect = sub.add_parser('connect')
    connect.add_argument('link')
    connect.add_argument('--client', required=True)
    connect.add_argument('--external-id', required=True)
    connect.add_argument('--model', help='Actual client-reported model, when known')
    connect.add_argument('--session', help='Actual client-reported current session, when known')
    connect.add_argument('--chat', help='Actual client-reported chat label or identifier, when known')
    connect.add_argument('--name')
    connect.add_argument('--workspace')
    connect.add_argument('--root', action='append', default=[])
    connect.add_argument('--output', required=True)
    call = sub.add_parser('call')
    call.add_argument('--connection', required=True)
    call.add_argument('--session', required=True)
    call.add_argument('--project', help='Registered project for this request')
    call.add_argument('--workspace', help='Registered server code folder for this request')
    call.add_argument('tool')
    call.add_argument('--arguments', required=True)
    config = sub.add_parser('config')
    config.add_argument('--connection', required=True)
    sub.add_parser('onboarding', help='Preview HTTP MCP configuration and persistent instructions; use onboarding --help')
    sub.add_parser('project-rule', help='Preview or repair/remove a scoped native project rule')
    diagnostics=sub.add_parser('diagnostics',help='Read local runtime diagnostics even while the server is stopped')
    diagnostics.add_argument('--config',type=Path,help='Installation configuration; defaults to the main Hub configuration')
    return parser


def _print(value):
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == 'onboarding':
        from native_onboarding import main as onboarding
        return onboarding(arguments[1:])
    if arguments and arguments[0] == 'project-rule':
        from native_project_rule import main as project_rule
        return project_rule(arguments[1:])
    args = _parser().parse_args(arguments)
    if args.command=='diagnostics':
        from hub_launcher import default_base, external_path
        from runtime_diagnostics import report
        config=external_path(args.config or default_base() / 'installation.json')
        _print(report(config.parent / 'diagnostics',include_tail=True))
        return 0
    if args.command == 'connect':
        output = _absolute_path(args.output)
        if output.exists():
            previous = load_connection(output)
            if previous.get('client') != args.client or previous.get('externalId') != args.external_id:
                raise ValueError('output belongs to a different enrolled connection; select a separate private file')
        link = args.link
        marker = '/connect/'
        if marker not in link:
            raise ValueError('connect link must contain /connect/{invitation}')
        base, invitation = link.split(marker, 1)
        client = Client(base)
        bootstrap = client.connect(invitation)
        kwargs = {'workspace': args.workspace, 'name': args.name, 'roots': args.root or None,
                  'model':args.model,'session':args.session,'chat':args.chat}
        if bootstrap.get('scope') != 'global' and bootstrap.get('project') is None and not args.name:
            raise ValueError('new-project invitation requires --name')
        connection = client.enroll(bootstrap['invitation'], args.client, args.external_id, **kwargs)
        file_data = dict(baseUrl=client.baseUrl, token=connection['token'], binding=connection.get('binding'),
                         project=connection.get('project'), client=args.client, externalId=args.external_id,
                         scope=connection.get('scope','project'),metadata=connection.get('metadata',{}),
                         workspace=connection.get('workspace'), workflow=bootstrap.get('workflow') if not bootstrap.get('instructionBundle') else None,
                         instructionBundle=bootstrap.get('instructionBundle'))
        save_connection(args.output, file_data)
        _print({'binding': connection.get('binding'), 'project': connection.get('project'), 'connectionFile': str(Path(args.output))})
        return 0
    if args.command == 'call':
        data = load_connection(args.connection)
        arguments = json.loads(args.arguments)
        client = Client(data['baseUrl'], data['token'], session=args.session,project=args.project,workspace=args.workspace)
        _print(client.call(args.tool, arguments))
        return 0
    data = load_connection(args.connection)
    name = mcp_server_name(data)
    variable = 'PROJECT_HUB_TOKEN_' + name.removeprefix('project_hub_').upper()
    _print(dict(transport='streamable-http',credentialEnvironment=variable,
                mcpServers={name:dict(url=mcp_http_endpoint(data['baseUrl']),headers={'Authorization':'Bearer ${env:'+variable+'}'})},
                instruction='Provision the referenced environment variable privately in the host process; preserve unrelated native configuration.'))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except SDKError as error:
        print(json.dumps(dict(error=error.code,message=str(error),outcomeUnknown=error.outcomeUnknown)),file=sys.stderr)
        raise SystemExit(2)
    except Exception as error:
        print(f'hub-cli: {error}', file=sys.stderr)
        raise SystemExit(2)
