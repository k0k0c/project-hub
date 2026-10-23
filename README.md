# Project Hub

**[Download Project Hub 0.3.2 — Pre-alpha 1](https://github.com/k0k0c/project-hub/releases/tag/v0.3.2)**

Windows 10/11 x64. The release page includes the installer and checksums.

Project Hub is a local Windows application for organizing AI agents' tasks and
work stages, keeping history, reports, project documentation, and architecture
notes in one place. It connects your working chats, agents, and projects so
decisions and results carry over between sessions.

The project is in public pre-alpha testing. Features and compatibility are still
evolving. Keep backups before important work and review the limitations below.

## Three independent connections

**Agent → Hub: tasks and shared context.** The agent you work with in your own
application accesses Hub tools through MCP, the Model Context Protocol for
connecting external tools to AI assistants. It can read project status, create
and edit tasks, track stages, save reports, and work with documentation. The
application needs to support MCP over HTTP, authentication, and project context.
Compatibility depends on the application's capabilities. You do not need a
separate model API key in Hub for this connection: the agent uses the model
configured in its own application.

**Hub → agent application: chats and task launches.** From Hub, you can open a
linked chat, create a chat for a task, and send work to an agent. Chat control
integration is currently available for Codex. It is experimental, requires
separate setup, and needs the Codex application to be running. Compatibility may
change after Codex updates. Connecting an agent through MCP does not by itself
enable control of its chats.

**Hub → model: research and documentation.** Hub can send requests directly to a
model to explore architecture, code, and documentation. This does not require
Codex, but Hub itself must be running. You can sign in with a ChatGPT account or
provide an API key, an access key obtained from a model service. Connections are
implemented for the OpenAI, Anthropic, and Google Gemini APIs, as well as services
with a compatible Chat Completions API. Direct requests help explain a project
and prepare documentation; code changes for ordinary tasks remain the external
agent's responsibility. Account sign-in for other services is not yet
implemented. Model connections are experimental: check access to your chosen
model with your own account or key.

## Installation

Download the latest version from
[Project Hub releases](https://github.com/k0k0c/project-hub/releases) and run the
EXE file. Python is included. Windows 10 and 11 on x64 are supported. The shortcut
starts a local server and opens it in your browser. You can also check the server
status through the system tray icon.

After starting Hub, open **Projects** and add a project. You can specify a source
folder if you want to explore its code. Tasks, documents, and history can also be
managed without linking a folder.

## Connecting an agent

Use an agent application that organizes work into projects or workspace folders
and supports persistent instructions, such as Codex, Cursor, Antigravity, or
similar tools. The invitation link gives the agent instructions to connect the
application to Hub, save Hub's working rules, and link the current project.
Compatibility depends on the application's MCP and project features.

1. In Hub, open **Settings → Agents and connections → Applications**.
2. Create an invitation in Hub, then paste its link into the agent's chat in your
   open project and ask the agent to connect to Project Hub.
3. Follow the setup instructions. If the application cannot save settings
   automatically, follow the documentation to configure it manually.
4. Check that the agent can see Hub tools and identify the correct project.
5. Ask the agent to create a small task and check that it appears in Hub.

During setup, the agent may offer to save persistent instructions for working
with Hub. Review the instructions and where they will apply before saving them.

To control Codex chats, ask the agent to set up the separate integration, then
run the check on the **Application chats** tab in the connection settings.

For direct requests from Hub, open **Settings → Agents and connections → Model
requests**. Choose ChatGPT sign-in or add your own API key. Select a model, test
the connection, and choose which connection Hub should use for its requests.
This setup is optional for ordinary task tracking through MCP.

## Everyday use

Create tasks, record stages, and attach context, reports, links, and documents.
Browse project history, revisit earlier decisions, and use architecture notes
in new discussions. Sections and labels in the application may change during
pre-alpha testing.

A useful workflow is to choose a project and describe a task, ask the agent to
refine the plan, and record the outcome of each stage. When the work is complete,
review the report, links, and attachments in Hub. In your next chat, ask the
connected agent to read the project's current state in Hub and continue the task
you need. Connecting an agent gives it access to Hub operations. Access to the
source folder is controlled by the client application and operating system
settings.

For research, you can send a separate request to a model, such as comparing
architecture options or explaining a section of documentation. Research results
are saved in the selected project's knowledge section, separately from ordinary
task execution. Before sharing sensitive material, check which context is
selected and which provider will process it.

Learn more:

- [Windows installation](docs/windows-installer.md)
- [Connecting projects through MCP](docs/mcp-project-connections.md)
- [Codex chat control](docs/codex-desktop-control.md)
- [Architecture and code analysis](docs/agent-analysis.md)
- [Backups](docs/backups.md)

## Limitations and data

Hub stores data locally, but the context or code you select may be sent to an
external agent or model provider when a request runs. The relevant service's
limits, terms, and possible charges apply. Hub does not automatically collect
your entire chat history. Connected agents and model services receive the
context needed for the operations they perform.
