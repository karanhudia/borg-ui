# BOR-38: borgbackupserver Agent Investigation

Date: 2026-05-19

## Source Snapshot

- Upstream repository: `marcpope/borgbackupserver`
- Upstream commit inspected: `b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253` (`v2.53.2`, 2026-05-17)
- Borg UI commit inspected: `3aa4ee9`
- Upstream references use immutable GitHub commit links where practical.

## Executive Summary

`borgbackupserver` uses a mature remote-agent architecture with a narrow HTTPS control plane and an SSH Borg data plane. The agent polls the server, receives server-built task payloads, runs Borg and pre/post plugins locally on the client, reports progress and completion over HTTPS, and uses a server-provisioned SSH key to push repository data to the BBS server through a forced-command SSH gate.

Borg UI's current managed agent is intentionally smaller. It already has the same core direction: one-time enrollment, token-authenticated heartbeat, job polling, claim/start/report transitions, log upload, cancellation, and local `borg create` execution for Borg 1 and Borg 2. It does not yet include BBS's broader environment integration: SSH data-plane provisioning, restore jobs, plugin/database backup and restore, file-catalog streaming, self-update, Borg binary management, watchdog/stall recovery, cross-platform zero-dependency installers, or server-side repository maintenance integration.

The most important product distinction is that BBS is opinionated about where repository data lives: backups are pushed over SSH into the BBS server's managed storage, with server-side pruning and repository management. Borg UI's agent currently runs Borg against a repository path supplied in the job payload. That makes Borg UI more flexible and simpler, but it means we currently lack the BBS-style integrated provisioning, append-only SSH gate, and central file-catalog model.

## Upstream Architecture

### Control Plane

BBS exposes dedicated agent API routes for registration, task polling, progress, status, heartbeat, inventory, catalog upload, SSH key download, and agent file download in `src/Core/App.php` ([lines 252-263](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Core/App.php#L252-L263)).

The agent uses a Bearer API key from `config.ini` and sends JSON requests with a `BBS-Agent/<version>` user agent. The core request wrapper lives in `agent/bbs-agent.py` ([lines 274-331](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L274-L331)).

Registration sends hostname, OS, platform, architecture, glibc version, Borg install metadata, Borg version, and primary IP. The server records this and returns polling interval plus SSH connection details ([agent lines 367-505](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L367-L505), [server lines 108-157](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Controllers/Api/AgentApiController.php#L108-L157)).

The poll loop registers once, starts a heartbeat thread, polls `/api/agent/tasks`, processes stall checks, dispatches `update_borg`, `update_agent`, or Borg task execution, and sleeps for the server-provided interval ([agent lines 3735-3838](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L3735-L3838)).

### Data Plane

BBS separates control traffic from backup traffic. The agent gets a private SSH key from `/api/agent/ssh-key` and stores it locally. The server returns SSH username, server host, and SSH port ([agent lines 509-625](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L509-L625), [server lines 1035-1068](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Controllers/Api/AgentApiController.php#L1035-L1068)).

The server builds `BORG_RSH` for SSH repositories. For local BBS-hosted storage, it points to `/etc/bbs-agent/ssh_key`; for remote SSH storage, the server sends a temporary private key in the task payload and the agent writes it to `/tmp/bbs-remote-ssh-key` while the job runs ([BorgCommandBuilder lines 180-217](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Services/BorgCommandBuilder.php#L180-L217), [agent lines 3190-3210](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L3190-L3210)).

Server-side SSH access is constrained by `bbs-ssh-gate`, installed as the forced command in `authorized_keys`. It allows `borg serve --append-only` with path restrictions, `catalog-write <job_id>`, and `ping`; everything else is rejected ([bbs-ssh-gate lines 24-102](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/bin/bbs-ssh-gate#L24-L102)). This is the core security boundary for push-based backups.

### Task Surface

BBS sends server-built payloads from `QueueManager`. Agent-side task types include:

| Task type | Runs on agent? | What the agent does | Source evidence |
| --- | --- | --- | --- |
| `backup` | Yes | Runs pre-backup plugins, counts files, executes `borg create`, parses Borg JSON progress, streams file catalog over SSH, reports final stats. | [agent task dispatch](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L2999-L3078), [backup execution](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L3079-L3653) |
| `restore` | Yes | Runs `borg extract`, reports byte and file progress, supports restore destination `cwd`. | [QueueManager restore payload](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Services/QueueManager.php#L498-L571), [agent generic restore path](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L3281-L3360) |
| `restore_mysql`, `restore_pg`, `restore_mongo` | Yes | Extracts database dump files from Borg archive, optionally creates safety backups, imports into target DBs, supports rename or replace. | [agent DB restore handlers](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L2330-L2898) |
| `plugin_test` | Yes | Runs plugin-specific connectivity/script tests and returns output or failure. | [agent lines 3029-3050](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L3029-L3050) |
| `update_borg` | Yes | Installs or updates Borg using server-selected binary, package manager, pip fallback, or Windows installer path. | [agent lines 731-812](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L731-L812), [QueueManager lines 919-967](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Services/QueueManager.php#L919-L967) |
| `update_agent` | Yes | Downloads replacement `bbs-agent.py`, validates syntax, keeps backup, refreshes wrapper, reports status, restarts itself. | [agent lines 1168-1292](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L1168-L1292) |
| `prune`, `compact`, `s3_sync`, `s3_restore`, `repo_check`, `repo_repair`, `break_lock`, `catalog_sync`, `catalog_rebuild`, `archive_delete` | No | Marked server-side; scheduler/server handles them instead of sending executable payload to the endpoint agent. | [QueueManager lines 114-115](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Services/QueueManager.php#L114-L115), [lines 265-279](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Services/QueueManager.php#L265-L279) |

### Plugin Handling

The upstream agent embeds built-in plugins for MySQL dumps, PostgreSQL dumps, MongoDB dumps, InterWorx backups, and shell hooks. BBS server sends plugin configuration in the backup payload; the agent executes pre-backup actions before Borg and cleanup/post hooks after Borg ([agent lines 1307-1467](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L1307-L1467)). The wiki describes the model as server-selected plugin instructions attached to backup plans, executed by the agent around the Borg archive operation ([Plugins wiki](https://raw.githubusercontent.com/wiki/marcpope/borgbackupserver/Plugins.md)).

The shell hook is more mature than a simple pre/post command. It receives `BBS_*` context variables and can opt into `BORG_PASSCOMMAND` plus `BORG_REPO` for advanced script-driven Borg use, with a temporary passphrase file to avoid putting `BORG_PASSPHRASE` directly into every hook subprocess environment ([agent lines 2114-2175](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L2114-L2175), [wiki lines 7-18](https://raw.githubusercontent.com/wiki/marcpope/borgbackupserver/Plugins.md)).

### Progress, Cancellation, and Watchdog

BBS parses Borg `--log-json` stderr events for backup stats, restore bytes, file counts, current file, warnings, and catalog entries. It posts progress every few seconds and treats server cancellation responses as kill signals ([agent lines 3224-3310](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L3224-L3310)).

The heartbeat thread only sends heartbeats while a task is running. It also handles server-reported stalled jobs and cancellation, killing the current Borg process tree when appropriate ([agent lines 3692-3732](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L3692-L3732), [server lines 959-1003](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/src/Controllers/Api/AgentApiController.php#L959-L1003)).

Final status reporting is retried with exponential backoff because a lost completion report would leave server jobs stuck ([agent lines 323-340](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent.py#L323-L340)).

### Installation and Runtime Integration

BBS has a server-served Linux/macOS/FreeBSD installer, Windows installer, service templates/wrappers, Docker agent image, and uninstallers.

- Linux/macOS/FreeBSD installer: detects OS, installs Borg and Python, downloads agent files from the BBS server, writes `/etc/bbs-agent/config.ini`, downloads SSH key, and installs launchd, rc.d, systemd, or init.d service ([install.sh lines 1-111](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/install.sh#L1-L111), [lines 175-423](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/install.sh#L175-L423), [lines 497-650](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/install.sh#L497-L650)).
- Startup wrapper: syntax-checks `bbs-agent.py`, downloads a fresh copy from the server if broken, falls back to `.bak`, then execs Python ([bbs-agent-start.sh lines 20-126](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/bbs-agent-start.sh#L20-L126)).
- Windows installer: requires Windows 10 1607/Server 2016 or newer, installs Borg, bundles or locates SSH/Python, downloads `bbs-agent.exe` and script, writes config, downloads SSH key, and installs an auto-restarting Windows service ([install-windows.ps1 lines 1-130](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/install-windows.ps1#L1-L130), [lines 167-430](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/agent/install-windows.ps1#L167-L430)).
- Docker agent image: includes Borg, SSH, DB client tools, Mongo tools, writes config from `BBS_SERVER` and `BBS_API_KEY`, and runs the Python agent as PID 1 ([Dockerfile and entrypoint](https://github.com/marcpope/borgbackupserver/blob/b8d3cceb2f22c0c4e47da0ae1edadafd0b1fa253/docker/agent/Dockerfile#L1-L46)).

The BBS server installation itself is designed to own MySQL/MariaDB, ClickHouse, Apache, SSH daemon, system users, and cron jobs; the agent is installed on the machines being backed up and pushes data to the BBS server ([Installation wiki](https://raw.githubusercontent.com/wiki/marcpope/borgbackupserver/Installation.md)).

## Borg UI Managed Agent Today

Borg UI has a Python package named `borg-ui-agent` at version `0.1.0`, requiring Python 3.11 and `requests` ([pyproject.toml lines 6-17](../../../pyproject.toml)). The CLI supports `register`, `status`, `once`, `run`, and `unregister` ([agent/borg_ui_agent/cli.py](../../../agent/borg_ui_agent/cli.py)).

The current agent capabilities are explicit and narrow: `jobs.poll`, `jobs.claim`, `jobs.report`, `logs.stream`, `backup.create`, and `backup.cancel` ([runtime.py lines 14-21](../../../agent/borg_ui_agent/runtime.py)).

Runtime behavior:

- On each loop, the agent sends a heartbeat, polls one queued job, claims it, starts it, dispatches only `backup.create`, and reports unsupported job kinds as failures ([runtime.py lines 40-81](../../../agent/borg_ui_agent/runtime.py)).
- Cancellation is checked by heartbeat every five seconds while a job is running; the server returns `cancel_job_ids` ([runtime.py lines 94-105](../../../agent/borg_ui_agent/runtime.py), [agents API lines 333-370](../../../app/api/agents.py)).
- `backup.create` builds Borg 1 or Borg 2 commands from a payload, supports repository path, archive name, source paths, compression, excludes, custom flags, remote path, optional Borg binary, and `BORG_PASSPHRASE` extraction from payload secrets. It streams Borg output as logs, parses JSON progress, and completes/fails/cancels through API calls ([backup.py lines 14-124](../../../agent/borg_ui_agent/backup.py), [lines 165-312](../../../agent/borg_ui_agent/backup.py)).
- Borg binary detection reports `borg` and `borg2` versions and paths ([borg.py lines 21-66](../../../agent/borg_ui_agent/borg.py)).
- Config is stored in TOML under platform-specific default paths, with `0600` permissions on POSIX ([config.py lines 77-142](../../../agent/borg_ui_agent/config.py)).

Server-side Borg UI integration:

- Agent API routes cover registration, heartbeat, unregister, job poll, claim, start, progress, logs, complete, fail, and cancel ([app/api/agents.py lines 278-602](../../../app/api/agents.py)).
- Admin-managed routes cover enrollment token creation/list/revoke, agent listing/revoke, manual agent-job creation, agent-job listing, logs, and cancel requests ([app/api/managed_machines.py lines 229-411](../../../app/api/managed_machines.py)).
- Manual backup requests for repositories with `execution_target == "agent"` create linked `BackupJob` plus `AgentJob`, and the agent's final state is synchronized back into the normal backup job fields ([app/api/backup.py lines 97-194](../../../app/api/backup.py), [lines 308-365](../../../app/api/backup.py), [app/api/agents.py lines 244-276](../../../app/api/agents.py)).
- Persistence is in `agent_machines`, `agent_enrollment_tokens`, `agent_jobs`, and `agent_job_logs`; repositories have `execution_target` and `agent_machine_id` fields ([models.py lines 78-166](../../../app/database/models.py), [models.py lines 250-255](../../../app/database/models.py)).
- Existing service templates are present for systemd and launchd, but they are examples that assume a preinstalled virtualenv and config path, not full installers ([systemd template](../../../agent/install/systemd/borg-ui-agent.service), [launchd template](../../../agent/install/launchd/com.borg-ui.agent.plist), [agent README lines 273-306](../../../agent/README.md)).

## One-to-One Comparison

| Dimension | BBS upstream | Borg UI today | Assessment |
| --- | --- | --- | --- |
| Primary architecture | Pull-based HTTPS control plane, SSH `borg serve` data plane. | Pull-based HTTPS control plane, Borg command runs against payload-specified repo path. | Same high-level remote-agent control model. Different repository/data-plane model. |
| Agent auth | Bearer API key against hashed server records, with legacy plaintext upgrade. | Enrollment token creates an agent token; agent authenticates with `X-Borg-Agent-Authorization: Bearer <token>`. | Borg UI has cleaner one-time enrollment/token separation. BBS has more production migration hardening. |
| Enrollment/provisioning | Agent is created/provisioned from BBS UI; installer gets API key and SSH key. | Admin creates enrollment token; CLI registers and stores returned agent token. | Borg UI enrollment is solid, but lacks server-served installers and SSH/storage provisioning. |
| Runtime installation | Full Linux/macOS/FreeBSD installer, Windows installer, Docker image, uninstallers, services. | Python package install plus sample systemd/launchd templates. | BBS is far ahead for unattended endpoint rollout. |
| Job lifecycle | Server queue promotes jobs to `sent`; agent polls tasks; progress/status endpoints update `backup_jobs`. | Agent polls `queued`, then explicit `claim`, `start`, `progress`, `logs`, `complete/fail/cancel`. | Borg UI has a more explicit transport state machine; BBS has more mature operational recovery. |
| Supported agent jobs | Backup, file restore, DB restore, plugin test, Borg update, agent update. | `backup.create` only. | BBS covers more lifecycle. Borg UI is a narrow MVP. |
| Server-side jobs | Prune, compact, S3 sync/restore, repo check/repair, lock break, catalog rebuild, archive delete. | Existing Borg UI has local/server backup services, but managed-agent transport does not yet schedule agent-adjacent maintenance. | Borg UI should decide which operations remain server-side vs agent-side for agent repositories. |
| Borg command construction | Server constructs Borg argv and env, including `BORG_RSH`, repo passphrase, remote path, lock wait, JSON/list/progress flags. | Server constructs structured `backup.create` payload; agent constructs Borg argv. | Borg UI gives the agent more command-building responsibility. BBS centralizes command policy on server. |
| Borg 2 support | BBS appears Borg 1-oriented in command shapes, with agent binary/version management. | Borg UI supports Borg 1 and Borg 2 command shapes in the agent. | Borg UI is ahead on explicit Borg 2 support in the managed agent. |
| Backup progress | Parses Borg JSON logs for archive progress, file status, restore bytes, warning handling, and catalog data. | Parses `archive_progress`, `progress_percent`, and `file_status` into progress percent/current file/stats. | Borg UI covers basic progress. BBS has more nuanced warning classification and restore/file count handling. |
| Logs | Sends progress/log messages through `/api/agent/progress` and server logs. | Dedicated per-job log upload with sequence de-duplication. | Borg UI's log transport is cleaner and more replay-safe. |
| Cancellation | Checks cancel in progress responses and heartbeat; kills process tree. | Checks heartbeat every five seconds; terminates then kills process. | Similar intent. BBS is more robust because it kills process groups/trees for Borg SSH children. |
| Stall recovery | Server detects stalled jobs; heartbeat/poll asks agent to confirm or kill; agent reports abandoned jobs. | No equivalent stale-running reconciliation beyond cancellation. | BBS has a production pattern Borg UI should adopt. |
| Completion durability | Final status retries with exponential backoff. | Single API call through `requests`; failure bubbles as runtime error. | BBS is stronger. Borg UI should add retry/backoff for terminal reports. |
| File catalog | Agent streams file status entries through SSH `catalog-write`; server imports into ClickHouse. | No managed-agent file catalog upload yet. | BBS has a full browse/search/restore support path. Borg UI needs a deliberate catalog strategy if remote browsing is in scope. |
| Database plugins | MySQL, PostgreSQL, MongoDB backup/restore; InterWorx; shell hook. | No plugin execution in managed agent. | Upstream-only. Borg UI has repository pre/post script fields generally, but not managed-agent plugin contracts. |
| Shell hooks | Context-rich `BBS_*` env and optional `BORG_PASSCOMMAND` credential exposure. | Not present in managed agent runtime. | Useful pattern if Borg UI wants endpoint-side hooks. |
| SSH key management | Server provisions Unix users, SSH keys, forced-command gate, append-only Borg serve, path restrictions. | Existing app has SSH repository concepts, but managed agent does not provision a central SSH data plane. | This is the biggest architectural gap if Borg UI wants BBS-style central storage. |
| Repository security | Append-only Borg serve prevents agents from pruning/deleting via SSH; management runs server-side. | Depends on repository path/credentials supplied to job. | Borg UI is flexible but less opinionated about damage containment. |
| Agent self-update | Agent downloads and validates replacement script, updates wrapper, restarts. | Not present. | Upstream-only and important for fleet operations. |
| Borg binary management | Agent can install/update Borg; reports source, path, glibc/platform/arch. | Detects `borg`/`borg2` only; no install/update. | Upstream-only, though Borg UI already reports multiple Borg binaries. |
| Windows support | Installer, service launcher exe, bundled Python, bundled SSH workaround, Borg installer. | Config path supports Windows; no Windows installer/service wrapper. | BBS is far ahead on Windows endpoint operability. |
| macOS support | Launchd, app bundle for Full Disk Access, compiled wrapper. | Launchd template only. | BBS is far ahead for real macOS backups. |
| Dockerized agent | First-class Docker image with DB tools. | No managed-agent Docker image. | Upstream-only. |
| API surface clarity | Few broad endpoints with task-specific payloads and status/progress. | More explicit endpoints for each transport transition. | Borg UI's API is easier to test and reason about. |
| Test posture in repo | No obvious Python unit suite for the agent in the inspected snapshot. | Unit tests cover API, runtime, payload parsing, Borg command building, and cancellation. | Borg UI appears stronger on local automated test coverage. |

## What Borg UI Is Already Doing Well

- The enrollment flow is cleaner than BBS's installer API-key model because enrollment tokens are one-time and produce a separate durable agent token.
- The job transport has explicit `poll -> claim -> start -> progress/logs -> complete/fail/cancel` states, which is easier to audit than overloading progress/status endpoints.
- Dedicated log upload with `(agent_job_id, sequence)` uniqueness is a good design for idempotent log streaming.
- Borg 2 command support is already part of the agent contract.
- The managed-agent code is compact and covered by targeted unit tests.

## Gaps Borg UI Should Consider

These are not implementation requests for BOR-38; they are the main roadmap implications from the comparison.

1. Add terminal report retry/backoff and stale-running reconciliation.
   BBS treats final status delivery and stalled tasks as critical operational failure modes. Borg UI should add durable completion retries, heartbeat-based stale job checks, and process-tree kill behavior for cancellations.

2. Decide the managed-agent data-plane model.
   If Borg UI wants BBS-style central storage, it needs server-provisioned SSH keys, append-only forced-command Borg serve, and path restrictions. If Borg UI stays payload-path based, document that the agent is responsible for access to the repository and accept that pruning/deletion containment is repository-specific.

3. Expand job types deliberately.
   Next natural Borg UI agent job kinds are `restore.extract`, repository check, prune/compact policy, and maybe pre/post hook execution. BBS shows that DB restore and catalog workflows become large quickly, so these should be separate contracts rather than ad hoc `custom_flags`.

4. Add an endpoint installation story.
   BBS's biggest practical advantage is installability: server-served installers, service setup, Windows support, macOS Full Disk Access guidance, uninstallers, and Docker images. Borg UI has templates, not an install product.

5. Add self-update only after signing/validation policy is clear.
   BBS self-updates by downloading Python from the server and syntax-checking it. Borg UI should not copy this blindly without a release trust model, version pinning, rollback behavior, and tests.

6. Define file-catalog strategy for remote agent backups.
   BBS streams file entries during backup and imports to ClickHouse for browse/search/restore. Borg UI currently completes an agent backup with archive name and stats only. If UI browse/restore for agent-backed archives matters, catalog upload must become part of the agent contract.

## Things BBS Does That Borg UI May Not Need

- BBS's DB plugin stack is tightly coupled to a hosting-control-panel backup manager product. Borg UI may not need MySQL/PostgreSQL/Mongo/InterWorx in the agent unless the product commits to application-aware backups.
- BBS's server owns Apache, MySQL, ClickHouse, SSH daemon, users, and cron. Borg UI should avoid inheriting this operational assumption unless it intentionally becomes an appliance-like server.
- BBS's agent supports very old Python compatibility and many distribution package paths. Borg UI currently requires Python 3.11; that is simpler and probably appropriate until endpoint install coverage becomes a priority.

## Recommended Follow-Up Shape

The investigation points to one high-value follow-up before implementation: create a managed-agent hardening and roadmap ticket that chooses the data-plane model, ranks job-type expansion, and specifies durability requirements. Without that decision, copying individual BBS features risks mixing two different architectures.

Concrete acceptance criteria for that follow-up should include:

- A decision on payload-path repositories versus server-provisioned append-only SSH repositories.
- A durability spec for terminal status retries, cancellation process-tree cleanup, and stale job recovery.
- A prioritized list of additional job kinds with explicit out-of-scope items.
- Installer/package targets for Linux, macOS, Windows, and Docker.
- Security requirements for any future self-update mechanism.
