# Official plugin format and publication boundary

Packaging and submission requirements are described in
[OpenAI's packaging documentation](https://developers.openai.com/plugins/build/plugins)
and [submission process](https://developers.openai.com/plugins/deploy/submission).

The package has root `plugin.json`, root `mcp.json`, skills and lifecycle hooks.
OpenAI presentation and hook settings live in `extensions.com.openai`;
`.codex-plugin/plugin.json` and `.mcp.json` are retained for compatibility. Prepare
and install keep both manifest versions and transports synchronized. Relative
manifest paths stay inside the plugin. Receiver-specific executable paths and
loopback configuration are generated at installation.

A dedicated local marketplace uses a relative plugin source and explicit
AVAILABLE / ON_INSTALL policies. Standard CLI registration is used; hook trust
is reviewed separately. This local archive is not a public-directory submission.

For public submission, OpenAI currently requires a public HTTPS MCP endpoint or
an agreed local-MCP support route. This runtime supports loopback HTTP only;
remote deployment/authentication is separate work. Submission also requires
publisher verification, validation/security checks and review material. Prepare
the applicable positive/negative test cases, walkthrough, release notes and
test-access details before that review. No publisher verification, remote
deployment, submission or public publication was performed here.

Local acceptance covers archive integrity, a receiving profile with no creator
helper, normal Codex CLI registration, a disposable server, prepared MCP/hook
transport and existing runtime contracts. It does not claim that OpenAI reviewed
or approved this package, or that every client/platform was exercised.

## Native instruction boundary

The current ZIP includes logically separate runtime/server/UI and plugin
components. Plain `codex plugin add` does not install or start the portal.
The Python installer initializes an owned native companion skill at
`~/.agents/skills/project-hub-user/SKILL.md`; bundled workflow, code and default
assets remain separate. Reinstallation preserves its body, and the portal edits
only that owned body with revision checks. Its GET never initializes files.
Location/history live in Hub's own data, not project instructions or the cache.
Hub API/MCP responses do not deliver policy or hot-reload a running chat.

A new `--skip-codex-registration` install without `--user-skill-root` places the
companion in private data outside native discovery; the UI reports this.
The catalog lists all packaged tools/scripts/hooks and provides recovery JSON
with current machine paths. Declaration is not observed execution or trust;
import and trust remain native user actions. Skills, user hooks and a companion
MCP are extension points, not arbitrary server-command execution.

Verification covers an isolated same-machine receiver, a Codex 0.160 MCP
handshake and native REPO `skills/list` discovery without a model call. USER
location is documented, but another computer and a new desktop task launch
have not been verified. Notification delivery or desktop resumption is not
claimed. See [instruction behavior](hub-instructions.md) and
[installation](local-installation.md).

Vendor notices and pinned upstream links are bundled. The repository has no
declared project-wide source license; no license grant is invented in plugin
metadata. Public licensing, publisher identity/contact and public policy URLs
remain publisher decisions. The authorized local handoff preserves all existing
source and third-party notices.
