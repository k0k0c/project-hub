# Agents and API research

Project Hub keeps project knowledge and the history of work performed by your
agents. It can also send a specific architecture or documentation question to
an API model and save a verified result in the selected project.

## Connect an external agent

Create an invitation in **Settings → Agents and connections** and give its link to the intended
agent. The connection belongs to this Hub installation and can be created before
you add projects. The agent selects a registered project and, when needed, its
code folder in each request. Existing connections limited to one project retain
their original scope.

Agents can use MCP over HTTP, the HTTP API, SDK or CLI. Their application's own
permissions determine whether they can configure the connection automatically.
Registration and recent requests show interactions with Hub; they do not prove
that an agent is currently running. Application, model and chat details are
reported by the client and may be unknown.

The invitation also supplies the complete Hub workflow and your additions.
Saving those rules in the client's project or application requires your explicit
consent to the displayed text, destination and scope. A manual setup provides
the same full text. See [permanent instructions](hub-instructions.md).

An **application/client** is the environment in which you work, such as a native
coding application. A **model** is the selected inference model. A **provider**
is the API service used for a Hub-originated request. One client or provider can
offer several models. Provider keys usually authorize a service account or
project; the request selects a model. A client subscription or MCP token does
not automatically issue a provider API key or share native chat history.

The invitation and Hub access credential are separate from model API keys. An
external agent does not need a model provider key to record its work through Hub.

Connect each application once. Its later requests reuse that application's
saved Hub access; a new chat or research request does not require another
application registration. A separately connected application has its own access,
project bindings and optional control settings.

Open an application to view **Hub access**, **Control from Hub**, **Projects**
and **Diagnostics**. Hub access allows the application to call Hub tools.
Control from Hub requires an interface supplied by the application and separate
configuration; connecting MCP does not enable reverse control automatically.
The detail page distinguishes a reported capability, saved settings and a
verified check. A recent authenticated request confirms access at that time,
not that a chat is currently running. Configure shared instructions and your
additions in **Work rules**; the application page shows its setup receipt.

Direct model research runs inside Hub using the connection selected in
**Model requests**. It records each run in the research history and does not
register a new external application. Earlier internal service registrations
remain in stored history but are excluded from the applications list when Hub
can identify their originating research receipts.

Research, descriptions, scenarios, subsystem proposals, project overviews and
documentation requests launched from Hub are internal operations. They do not
create tasks, plan stages or agent work records. Their progress, errors, sources
and results remain in the research journal and project knowledge. The same rule
is included in the connection instructions and in requests delivered to a native
agent. Explicit user implementation work and a **Run task** request still use
the normal task workflow.

## Choose an authorization method

**Settings → Agents and connections → Model requests** separates two ways to
authorize Hub requests. **Service sign-in** currently supports ChatGPT and uses
the model access granted through that account's plan. **API key connection**
uses a key issued by your chosen provider and its API quota. Each section has
its own add action and the same controls for saved connections: edit, probe,
delete and select for Hub requests.

Hub sends these requests directly to the model service. Codex does not need to
be open; its MCP connection and chat-control adapter are separate. Keep the Hub
server running and open its interface in a regular browser to check this after
exiting Codex. Start a new explicit model probe and check its new timestamp and
receipt; reopening an old successful receipt sends no request. For a complete
analysis check, start document research and verify its publication in Hub.
Neither operation creates a Codex chat. Access-token expiry alone does not require
another sign-in: Hub renews the saved ChatGPT session when preparing a request
that needs fresh credentials. This also works after exiting Codex, provided the
Hub server stays running.

When Hub receives a sign-in or refresh response, it retains the credentials in
protected storage before verifying the account. No model can use them until
signature, issuer, audience, expiry and account identity checks succeed. If the
verification cannot finish, **ChatGPT authorization needs verification** means
that the next new model check will resume verification of that same response.
It does not repeat the token exchange. This recovery also works after restarting
Hub. **Refresh result** only reads the old check receipt.

`chatgpt_identity_invalid` means that an authorization response failed account
verification before a model request. New verification diagnostics report a fixed
reason such as expiry, audience or signature; they never expose claims or token
contents. A received response remains protected and untrusted while verification
is pending. Hub never skips the rejected check to restore access.

**Refresh status is unknown** means the token exchange has no usable saved
response. Repeating an already spent refresh token could damage the renewable
session, so Hub does not replay it automatically. Earlier versions could also
enter this state after receiving a response but losing it during verification.
Such a lost response cannot be reconstructed: open **Edit** and sign in once to
restore that connection. Revoked or expired renewable sessions also need sign-in.
Reconnecting MCP or the Codex chat adapter does not repair model authorization.

The refresh and replacement rules follow the official
[ChatGPT accounts and sessions documentation](https://developers.openai.com/siwc/token-sharing-open-source/profiles-and-sessions).

## Configure an API model

Add an API provider in **Settings → Agents and connections** with its model identifier and
credential. Compatible Chat Completions services also require an endpoint.
Obtain the provider key in the provider's account and enter it in these settings;
MCP enrollment cannot issue that key automatically.
Provider credentials belong to the installation and are available to research
requests across its projects. You can choose a provider for one request without
changing the default selection.

Opening a page or refreshing a request's status does not start paid model work.
Only an explicit research request starts a background API call. Hub records the
chosen provider, model, request identifier, progress and outcome.

Choose a network policy for each saved provider. **Direct** connects to the
 provider without an HTTP proxy. **System HTTP proxy** uses the operating system
 or environment proxy settings available to the Hub process. A local Hub uses direct connections; this setting
does not change your global proxy or VPN. Existing providers use direct mode
until you choose another policy.

You can run an explicit **Probe model** check from the provider list. It sends a
small generation request and may incur provider charges, so Hub asks before it
runs. Saving a provider or opening this page never starts a probe. If the result
is uncertain, refresh the saved receipt before starting a new probe; Hub never
repeats an uncertain request automatically. The receipt can show safe transport
details such as the scheme, host, port, timing, status and upstream request ID.
Credentials, prompts and raw provider error bodies are excluded.

For an unexpected response format, new receipts also record a fixed media-type
classification, content-encoding classification, received byte count and a
structural body hint (for example, JSON-like or HTML-like). Arbitrary header
values and body text are never recorded. A format hint does not validate the
response or identify which service or network intermediary produced it.
ChatGPT inference requires a completed event stream; HTTP 200 or a JSON-looking
body alone is not success. Earlier receipts cannot recover format facts that
were not saved, and refreshing a receipt never sends another model request.
If the response omits Content-Type, Hub can still read a correctly framed event
stream and confirm its completed terminal event. HTML, a plain JSON response,
malformed or unfinished streams remain failures; a declared incompatible media
type is not ignored. The missing header stays visible in the saved diagnostics.

Model probes allow up to 60 seconds of network inactivity (or a shorter configured
analysis deadline). This wait is separate from the timeout for each analysis
turn. New transport records include the applied timeout; received HTTP headers
are saved before reading the response. A timeout before headers cannot distinguish
a connection delay from processing at the provider. A timeout after headers is
reported as a read failure. Both leave the model request's outcome unknown and
require an explicit new probe to send another request. Older receipts retain the
facts recorded at the time and are never rewritten to use the new wait limit.

New TLS failures include a fixed `tlsReason` classification; certificate
verification failures can also include a numeric `tlsVerifyCode`. Raw exception
messages, certificate bodies and proxy credentials are excluded. An abrupt TLS
EOF without HTTP headers leaves the request outcome unknown: the connection may
have closed after sending the request. If headers were already received, the
receipt identifies a read failure. Neither case is automatically retried.
Older TLS receipts without a subtype cannot identify the original cause.
The system HTTP proxy label describes a network policy. If no applicable proxy
is configured, that policy connects without an explicit HTTP proxy; it does not
establish whether a VPN or another network intermediary is present.

The provider list retains the last explicit check, its time and the source of
access. An API key uses the provider's API account; Hub does not infer a paid
account or an application subscription from that key. Account sign-in that
authorizes use of a subscription is a separate integration and is not offered by
the current API-key form.

Checks distinguish available access, rejected access, network failures, temporary
rate limits and exhausted quota when the provider supplies a recognized reason
code. HTTP 429 alone does not distinguish request rate from quota or billing
limits. Unknown reasons remain unspecified. Safe, recognized error code/type
identifiers can accompany transport details; arbitrary messages are excluded.
Changing the key, model, endpoint or network policy requires a new check.
Renaming the service does not invalidate it. A saved result describes the time
of the check and does not guarantee current access. Reopening it only reads its
receipt; another model request requires explicit confirmation.

## Sign in with ChatGPT

You can add a Responses connection with **Continue with ChatGPT** when your
account and plan allow model access. This uses the ChatGPT subscription for Hub
requests and does not replace or expose API keys. Choose the account's model
from the models supplied for that account; Hub does not assume a fixed model name.
The account list shows email addresses or names; internal identifiers are not
shown. If there are several saved sign-ins with the same label, a number distinguishes
them without merging their credentials.

Choose an existing account in the connection dialog, then choose a model and
save the connection. Successful sign-in and successful model discovery are
separate states. If the model list cannot be loaded, the dialog shows the reason
and safe transport details. Use **Refresh model list** to try again with the
saved sign-in; this does not start a generation request.

A saved account identifies a retained registration; its presence alone does not
confirm that Hub can use it. The dialog shows **Authorization status** separately.
Verified sign-in needs no new login. A received response awaiting verification
offers **Verify authorization**, which checks the saved response and loads model
choices without starting a generation request. **Sign in to ChatGPT again** is
for a signed-out or unrecoverable session. Signing out clears Hub authorization;
removing the account also removes its saved registration.

`chatgpt_crypto_unavailable` identifies a missing or incompatible Hub signature
verification component. Repair the Hub runtime and verify authorization again;
another sign-in cannot repair that component. A received response remains in
protected storage while verification is unavailable.

After saving, **Probe model** sends an explicitly confirmed request using the
ChatGPT plan's allowance. A connection stores the account and model chosen for
Hub requests. **Delete connection** removes those settings. The saved ChatGPT
sign-in remains available for another connection.

In the connection dialog, expand **Saved ChatGPT accounts** to manage sign-ins.
**Sign out** ends the local session. **Remove account from Hub** asks for
confirmation, signs out when necessary, and removes its saved sign-in data from
Hub. Delete connections using that account first. Removing a saved account does
not delete the account at OpenAI or the history of requests in Hub. The dialog and
provider list refresh after these actions; reopening the dialog fetches current
account status without reloading the page.

The dialog selects the saved active account by default. Reuse it for another
connection or for sign-in again; do not add the same account afresh. Choose
**Another account or workspace** only for a separate ChatGPT account or workspace.
OpenAI registrations can share an email address while belonging to different
client and workspace contexts, so Hub never merges credentials by email.

The dialog has one sign-in action for the selected account. It reserves a browser
tab during the click, then sends that tab to the local authorization redirect.
If the browser blocks a new tab, use the single **Open authorization page** link.
A browser connection or DNS failure is separate from Hub's network policy; it
does not mean that sign-in succeeded. Hub continues to show pending sign-in until
OpenAI returns its authorization result.

OAuth requests allow up to 60 seconds of network inactivity. Model discovery
retains its separate 30-second limit. An authorization failure before inference
means no model request was sent. If a refresh request times out, its outcome is
unknown: OpenAI may already have replaced the refresh token. Hub preserves the
registration, marks it as requiring sign-in, and never repeats that refresh.
Open **Edit** for the saved connection and continue in ChatGPT to authorize it
again. Reuse the existing registration; adding another connection is unnecessary.
New safe diagnostics identify the OAuth step without retaining the URL path,
credentials or response body.

The sign-in page opens only after you choose **Continue in ChatGPT**. You can
cancel a pending sign-in or refresh its saved status. A signed-out or expired
registration remains available for reauthentication. When plan model access is
disabled, use [ChatGPT Usage settings](https://chatgpt.com/#settings/Usage) to
manage access before signing in again. Logging out removes the account's active
Hub authorization but does not delete a saved provider connection. No model
generation runs while opening the settings page, signing in, refreshing status,
or saving the connection.

Each sign-in attempt lasts ten minutes. Start it with **Continue in ChatGPT**
when you are ready; a previously shared sign-in link may already have expired.
If Hub rejects the return link, open model settings from the error page and
start again from the saved connection. Reloading an old callback cannot renew
its attempt or reuse its one-time authorization code.

## Investigate architecture and code

Select a project, subsystem, directory, class, relationship or saved research map
and describe what you want to understand. Choose the kind of investigation and
how detailed the answer should be. A selected object is the starting point:
related files, collaborators and previous project knowledge can contribute to
the answer.

For code research, connect an accessible source folder. Hub can perform a local
source scan before the first model request. The researcher can inspect all
available registered folders with bounded tree, text-search and file-reading
tools, including neighboring files in other folders. It can discover applicable
`AGENTS.md` files and available project skills. The model's API does not mount
your filesystem; Hub performs the permitted reads and sends their results to
the chosen provider. Service directories, credential files, binary files and
symbolic links are excluded.

Research starts with the selected object's source links and reads related
sources as needed. The read budget counts each unchanged source file once,
including when it is read in several pages. Broad search has a separate ceiling
that leaves capacity for direct source reads. A partial search reports its limit
so the researcher can narrow the path; rejected reads do not consume the
remaining budget. Hub still checks for changed source content before accepting
evidence.

The API researcher receives its own architecture instructions and captured
context. It does not automatically inherit the rules, tools or history of a
native chat. Project rules are read through the supplied tools within the
research assignment. Tool access remains read-only.

After validation, Hub saves an authored description on a persistent object or
a separate research view for a project, directory or transient symbol. A
decomposition adds evidenced subsystems and its overview together. Grouping a
saved map creates a separate view with local groups, preserving global ownership.
Generated source facts and earlier history remain available.

## Draft, refresh or review documentation

Use a documentation research request to prepare a new article, refresh an
existing Markdown document, or review the documentation for evidenced gaps.
Describe the intended reader and what the document should explain. The
researcher can read earlier documents and knowledge with their revisions and
consult source files through the same restricted tools.

New articles and reviews are saved as separate internal drafts. Refresh updates
only the selected Markdown document and preserves its audience, section, status,
visibility, existing source references and links. Review does not replace the
document being reviewed. Source evidence and the research basis accompany the
saved result so you can assess its claims.

## Results, changes and cancellation

The host validates the structured response, inspected evidence, source hashes,
knowledge revision and registered folders before publishing. It saves the result
through one revision-checked changeset. A malformed answer, missing evidence or
changed context leaves knowledge unchanged. The request receipt retains the
response for diagnosis; it is not published as a fallback article.

You can cancel an active research request. Cancellation preserves its receipt
and prevents later results from being published. If the provider outcome is
uncertain or the process stops, inspect the recorded status before starting a
new request. Repeating the same request identifier does not start a second model
call. Previous task and native-chat receipts remain readable as history.

Hub research does not execute ordinary tasks or stages, generate task plans,
review all tasks, or start or resume native chats. Implementation remains work
for your external coding agent.

The same request lifecycle serves architecture, code-oriented investigation,
articles and documentation: capture context, supply action-specific rules,
perform a bounded model call, validate the structured answer and save a
revision-checked result. Native chat opening is an optional independent
capability. Its failure does not prevent these requests. Ordinary task-start
buttons remain unavailable even if a connection's diagnostic test can create
a disposable chat.

## Client integration contract (developer reference)

Call `hub_connection` with your own current `session`, `action: "describe"` and
a `profile` containing `schemaVersion: 1`. No project is required. Optional
identity fields are `clientVersion`, `clientInstance`, `host`, `model` and
`nativeChat: {client, nativeId, openUri?, title?, clientInstance?, host?, model?}`.
An optional `capabilities.openChat.uriTemplate` uses one `{nativeId}` placeholder
on a fixed HTTPS or local HTTP origin. Hub URL-encodes the ID and records the
derived source as client-reported; a template never verifies native UI opening.
For task, stage and report tools, `nativeChat` describes the current external
resource separately from the Hub actor. Unknown fields must be omitted.

`persistentInstructions` reports `scope` (`project` or `application`),
`destination`, explicit Boolean `consent`, bundle `revision` and `status`
(`saved` or `manual`). Hub labels this information client-reported. Enrollment
and a test callback cannot prove persistence or new-conversation discovery.

`control: {protocol, endpoint}` describes `mcp-http` or `http-json`. Each
`capabilities.createChat` or `capabilities.sendMessage` entry contains an
advertised MCP `tool` or HTTP `path`/`method`, JSON `arguments`, and optional
response `idField`/`uriField` dot paths. Arguments accept named placeholders
`$prompt`, `$nativeId`, `$callback`, `$probeId` and `$nonce`. They never contain
credentials, scripts or executable commands. The administrator separately
confirms the endpoint and private credential; redirects are refused.

The bounded test correlates its one-purpose nonce with the conversation ID
actually returned by the configured API. Its callback has no task or project
authority. A changed profile, endpoint, expired test or revoked connection
invalidates the reply. Recorded API acceptance and source URLs are separate
from native window verification. New services can describe this contract
without adding client names to Hub's project data model; a different transport
requires a documented extension and has no command fallback.

## Research limits

Reading and model calls have explicit limits. A truncated page, partial search,
unavailable folder or incomplete language analysis cannot prove that a
relationship is absent. Static source relationships do not establish a complete
runtime trace. Without a connected source folder, research can use stored
architecture and documents but cannot verify local code.

The runtime does not reproduce a coding client's persistent chat context,
context compaction or token-usage optimization. Results depend on the selected
model and the available evidence. Refresh source analysis when files change and
review limitations before relying on earlier findings.
