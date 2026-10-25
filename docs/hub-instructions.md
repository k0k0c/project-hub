# Agent connections and permanent instructions

Open **Settings → Agents and connections** to invite a client, inspect its
reported capabilities, read the complete Hub workflow and edit your additions.
Connections belong to the Hub installation. Projects, their tasks and files do
not depend on which client or model accesses them.

## What the invitation does

Press **Invite agent**, copy the generated link and give it to the intended
agent in its application. The invitation is private, expires after one day and
enrolls one connection. It does not create a project or purchase model access.
The agent reads setup instructions, registers its client and receives a private
Hub credential and HTTP MCP parameters. Application, model and current chat
details can be omitted when the client cannot determine them reliably.

The client configures native HTTP MCP if its application and permissions permit
it. Otherwise it must show the exact manual configuration and required actions.
Hub cannot modify arbitrary applications merely by sending a link. A loopback
Hub address is reachable only from the local machine; a cloud client needs a
separately configured reachable connection. Hub does not create a tunnel.

## Permanent instructions and updates

Setup provides a versioned portable workflow and your separate editable
additions. Those rules cover identity, task selection,
visible stages, beginning work, progress reports, evidence and task completion.
The invitation and `hub_instructions` provide the same bundle. MCP resources
also expose the manifest, workflow, additions, short bootstrap and complete
operation reference separately. The reference is generated from the published
tool schemas and saved as `api-reference.md` with the local snapshot. It lists
the actions, parameters and required fields without requiring source inspection.

The authorized setup installs a short application-wide rule and separate local
instruction files. Native permissions remain in force; the agent requests
additional approval only when the host requires it. Project rules contain only
the scoped Hub project binding. The agent preserves
unrelated instructions and records the Hub address, native MCP connection name
and a private credential reference. Credentials never belong in rule text.

When automatic saving is unavailable, the agent supplies the full rule text and
exact manual steps. A native instruction size limit must be explained; rules
must not be silently truncated. Open a new conversation and check that it knows
the Hub address and work rules. A client's report that it saved rules is shown
as a report, not proof that every future conversation loads them.

Successful setup requires native MCP discovery and a real Hub request through
that connection. A saved configuration, an authenticated SDK request and rules
on disk are separate checks. Supported local onboarding uses the reserved
`localhost` name for HTTP MCP, so the endpoint can use the client's normal local
proxy bypass without changing system settings. If initialization fails, setup
must report that failure rather than claim the connection is ready or raise
global proxy exceptions. A cloud client still needs a reachable endpoint.

Your additions are stored in Hub with revision checks and edit history. Existing
user rules are retained when moving to this editor. Saving here changes the
Hub-owned copy; it does not overwrite a native client file or reload running
chats. A configured agent compares the manifest at startup and refreshes changed
or missing local files through the same native permissions. Ordinary context
responses also announce the current version.
Conflicting saves preserve the draft so you can reload and reconcile it.

See [MCP project connections](mcp-project-connections.md) for project discovery,
binding repair, relocation and the typed Hub-to-agent launch contract.

## Capabilities and test results

A client can describe optional native chat links and documented HTTP or MCP
control actions. Its description does not authorize Hub to contact that
endpoint. Confirm the endpoint and its separate API credential in settings.
Configuration then starts a bounded test if the client supplied a matching
profile. You can rerun it with **Test capabilities**. The test may create a
separate disposable conversation and send a diagnostic message.

Hub distinguishes an observed MCP request, an accepted API operation, a usable
source link and a correlated reply from the new conversation. A successful
reply does not prove that a native window opened. Missing or timed-out replies
leave the capability unconfirmed. Unknown clients can still record tasks and
use Hub without native chat control. There is no shell or stdin fallback.

## Chats, disconnecting and reconnecting

Clients can optionally attach their current native chat identifier and source
URL when creating or updating a task, stage or work report. Hub retains those
resources in task chat history. Known historical Codex records retain their
documented source links. A generated Hub session identifier does not become a
native chat link merely because it resembles a UUID.

Disconnecting revokes Hub access without deleting projects, tasks or saved chat
links. Reconnecting creates a new private credential for the same connection
identity and preserves its history. Client, model and provider are separate:
one client can use several models; a provider key normally accesses the
provider's API account or project, with the model selected per request.

### Continue a task in another application

Any connection with access to the project can read, edit, continue and complete
its tasks. The creating application or an earlier connection does not own the
task. Each worker records its own contribution separately so simultaneous work
and its source boundaries remain visible.

If a stage still has historical work awaiting acceptance, ask your agent to
reconcile the specific accepted records in that project. It reads their current
revisions, records the acceptance reason and closes them under its own identity.
The original worker, identifiers, previous results, evidence, claims history and
Git boundaries remain in the audit. Repeating the same request does not duplicate
the result. Other unfinished work continues to keep the stage open.
Existing evidence remains in the original work, its audit and earlier stage
reports. The new reconciliation report publishes only newly supplied evidence,
so an archived source cannot prevent recording acceptance.

Open the task's **Chats** tab and select **Reconcile work records** to inspect
open records, choose the accepted or cancelled outcome and explain your decision.
Coordinate with an active worker before closing its contribution. Interrupting
active work requires the additional confirmation in this dialog; a last-seen timestamp does
not establish whether it is still executing. A concurrent update requires a new
read and agreement. Reconciliation does not establish a missing Git checkpoint:
that outcome remains separately visible and may need its own verification.

For agents, the standard path is `hub_context(work=...)`, then `hub_report` with
the returned revision, terminal status and `reconcile={owner,status,reason}`.
MCP reconciliation accepts only another actor's waiting work. Active work
requires the local user dialog; an owner uses an ordinary report. Begin new
owned work to continue implementation.

Ordinary task execution and continuation stay in the external client. Hub sends
typed project requests through a configured native HTTP/MCP control interface
when the client supports project routing. Their acknowledgement and results use
the same Hub MCP connection. Without that interface, native launch is unavailable.
Hub also sends
bounded architecture and documentation requests through the separate model API
configuration. Those requests carry their own context, result schema and
publication rules; they do not inherit a native chat's history automatically.
See [agents and API research](agent-analysis.md).
