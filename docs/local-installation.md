# Install Project Hub on Windows

Project Hub is a local portal for project tasks, history, documentation and architecture. It connects to agent applications through MCP or its API. The Windows installer includes a private Python runtime, web server, API client SDK and command-line tools.

## Install and open

Run the Project Hub Windows installer, choose Russian or English, and select the program folder. The installer language becomes the initial Hub interface language. Change it later in **Settings → Project Hub language**; project content stays in its original language. [Updating, reinstalling and uninstalling](windows-installer.md) preserve external settings and project data.

Open **Project Hub** from the Start menu. Its launcher starts one local server and opens the portal. A new installation has no projects. All sections remain visible and explain how to connect a project.

The default program folder is `%LOCALAPPDATA%/Programs/ProjectHub`. Configuration, writable data and private credentials are separate, under `%LOCALAPPDATA%/ProjectHub`. Opening the application does not write project information into installed program files. Uninstalling keeps your data.

## Create a project and connect agents

Open **Projects** to create and name a project. A code folder is optional. Rename, archive, delete and restore projects while retaining their identifiers and history. See [projects and code workspaces](project-spaces.md).

Open **Settings → Agents and connections** to create a universal invitation, copy its link and give it to an agent. No project or client choice is needed. Agents and model API connections are global: configure them before creating a project, or use several agents with any project. Projects manage project data and optional code folders.

The link supplies enrollment instructions and the complete agent workflow. The agent obtains a private Hub credential and registers Streamable HTTP MCP when its client supports it. Hub records the model and client metadata the agent reports; missing details remain unknown. API and MCP are the integration transports. If the client cannot configure its native connection or permanent instructions itself, the invitation provides the manual steps. Client permissions and trust prompts remain under the application's control.

Verify enrollment with `hub_projects`, then select a project explicitly with `hub_context`. Keep Hub workflow instructions in the client's permanent rules so new conversations record tasks and visible stages. Enrollment and recent MCP requests are shown separately; enrollment alone does not prove that an agent is currently working.

The installer includes `project-hub.cmd`; run it with `--help` for connection, API call and onboarding commands. The Python SDK is `app/scripts/agent_sdk.py`. The server exposes Streamable HTTP MCP at `/mcp` and project-scoped API tools. Credentials belong in private storage outside project source and public instructions.

## Configure architecture and documentation research

In **Settings → Agents and connections**, add a model API connection. Generic API formats can be configured; a compatible format does not prove that every vendor or native client has been tested. Choose an available API connection when requesting architecture analysis or documentation. A Hub connection credential is distinct from a provider API key; MCP enrollment cannot issue a paid provider key automatically.

Each research request receives its own analysis or documentation instructions, project rules and read access to permitted source roots and saved knowledge. The selected file or subsystem is the starting point; related code can be read across registered roots. Hub validates the structured result, evidence and captured revisions before saving it. API research saves results in Hub rather than assuming a provider's native conversation context. Opening a page or refreshing status never starts a model request.

Ordinary tasks are managed through your external agent conversations and MCP.
Task activity indicators are informational. Hub does not launch or continue
task chats or generate task plans through a model API. Existing chat references
and results remain available in task history.

API keys stay in the installation's private credential vault. Windows protects it with the current user's DPAPI. Keys are excluded from portable data backups; enter them again when moving to another installation. Tasks and analysis receipts remain readable without a key.

## Connect code and build the architecture

A registered, available local code folder enables source scans, previews and local Git operations. A language server also needs access to that folder and its language tools configured by the administrator. Data-only and cloud projects still support tasks, documents and authored architecture. Hub never guesses code locations from its installation or data path.

In **Architecture and code → Manage subsystems**, start with a project overview or first-level subsystems, then refine individual subsystems. Rename a subsystem, adjust its parent and source boundaries, or request another description. Its identifier and history are preserved. Reconcile saved references before removing a subsystem that is still used.

For an API project's first source analysis, Hub can prepare the initial inventory before the model starts. The model receives read tools; the host validates proposed titles and source boundaries before adding subsystems. Existing subsystems are preserved. Invalid or conflicting proposals retain their result for review. Scan explicitly after changing boundaries to update code ownership.

## Preserve and transfer data

Use **Projects → Backups** to download a versioned archive of the whole data home, including all projects and shared records. Editing pauses during the full operation while browsing and progress reporting continue. The shared top banner follows the operation across sections and reloads. See [backups](backups.md) and [the archive format](backup-format.md).

Choose an existing Hub data folder or upload a compatible archive. Compare its projects, choose addition or full replacement, and confirm the summary. Supported older schemas are converted on the prepared copy. Both methods publish into the current active data folder, preserving the source and current installation credentials. The supervisor drains database handles, verifies the new server and can restore the previous data after failure. Change the active and backup folders separately in **Settings → General**; source work mode and the installed application share that configuration.

## Server diagnostics

Open **Settings → General → Project Hub server** to see the diagnostic folder and
last recorded incident. The report includes process exits, error tracebacks and
operation stages. A recorded incident can belong to an earlier session; losing
contact with the server does not by itself establish why it stopped.

Logs are stored in a `diagnostics` folder beside the installation configuration,
separately from project data and portable backups. Normal logs rotate at 1 MiB;
up to 40 older process groups per component are retained. Fatal Python failures
have a separate file. Closing Hub normally is distinguished from an unexpected
process exit. Request bodies, authentication headers and credentials are not
added to structured events. Tracebacks and raw process output may contain local
paths or error details; review the report before sharing it.

If the server has stopped, run `project-hub.cmd diagnostics` to read the saved
report. For a custom configuration, add `--config <configuration-file>`. This
command reads existing diagnostics and does not start the server.

## Optional tools and previous installations

The EXE requires no global Python installation. Git, local Codex, Java and external language servers are optional tools for their respective features. Their absence is reported as an unavailable capability. They are not silently installed or substituted.

Existing Codex plugin installations remain compatible. See [previous Python/plugin installation](legacy-plugin-installation.md) and [the check wrapper](check-wrapper.md) for their previous setup and verification workflow. The independent connection requires no plugin skills or lifecycle hooks. Keep the previous setup until the new connection passes its new-conversation check.

The server binds to loopback. This release does not provide remote multi-user service. Payload checksums are recorded in the installer manifest; vendor assets and licenses are included.
