# Managed Agent Behavior Support Spec Plan

> For agentic workers: this is a documentation-only plan for BOR-38 rework. Do not change runtime behavior in this task.

**Goal:** Rework the BOR-38 investigation into a general Borg UI managed-agent behavior and support-target spec, then update the BOR-39 follow-up ticket to match.

**Architecture:** Keep the artifact product-first: define the intended managed-agent role, map current Borg UI capabilities, identify reusable implementation pieces, and use the upstream reference implementation only as supporting evidence. The output should guide future implementation without changing code in this task.

**Tech Stack:** Markdown docs, Linear GraphQL for follow-up issue metadata, local Git/GitHub PR workflow.

---

### Task 1: Capture Rework Inputs

**Files:**
- Read: Linear BOR-38, PR #507 comments, BOR-39
- Read: `agent/borg_ui_agent/runtime.py`
- Read: `agent/borg_ui_agent/backup.py`
- Read: `app/api/agents.py`
- Read: `app/api/managed_machines.py`
- Read: `app/api/backup.py`
- Read: `app/services/backup_service.py`
- Read: `app/services/remote_backup_service.py`

- [x] Record the reviewer request from PR #507: general agent behavior, Borg UI support targets, reuse existing capabilities, update BOR-39, and avoid upstream-repo naming as the spec frame.
- [x] Confirm current Borg UI managed-agent scope: enrollment, heartbeat, job polling/claim/start/report/logging/cancel, and agent-side `backup.create` only.
- [x] Confirm existing non-agent backup capabilities that may be reused: repository model fields, backup plan source locations, script hooks, remote SSH source handling, remote SSH execution service, Borg 1/2 command routing, maintenance services, restore services, archive browsing, and notification/progress models.
- [x] Confirm upstream reference scope from source: polling HTTPS control plane, SSH Borg data plane, backup/restore/update/plugin/catalog handling, service installers, process-tree cancellation, terminal report retry, and stall recovery.

### Task 2: Write the Reworked Spec

**Files:**
- Create: `docs/engineering/specs/2026-05-19-managed-agent-behavior-and-support-targets.md`

- [ ] Use a title and path that are about Borg UI managed agents, not the upstream repository.
- [ ] Define the desired Borg UI agent role as server-orchestrated endpoint execution where the server sends work and the endpoint runs Borg near the data.
- [ ] Explicitly cover remote-to-remote backups: the server should orchestrate, while source-to-repository data should move directly from the agent/source environment to the target repository where possible.
- [ ] Map current Borg UI behavior, what can be reused, and what is unsupported today.
- [ ] Include a one-to-one comparison table with the upstream reference implementation as evidence.
- [ ] Include recommended support targets and out-of-scope cautions for future tickets.

### Task 3: Update Follow-Up Ticket

**Files:**
- Linear BOR-39

- [ ] Update BOR-39 title and description so it describes managed-agent orchestration support rather than a source-repo comparison.
- [ ] Include acceptance criteria for data-plane decision, backup-plan/manual support parity, reusable existing capabilities, durability, job-kind expansion, installers, and security model.
- [ ] Keep BOR-39 in Backlog.
- [ ] Add a `related` relation between BOR-38 and BOR-39 if missing.

### Task 4: Validate and Publish

**Files:**
- Validate: `docs/engineering/plans/2026-05-19-managed-agent-behavior-support-spec-plan.md`
- Validate: `docs/engineering/specs/2026-05-19-managed-agent-behavior-and-support-targets.md`

- [ ] Proofread for requested framing, source-backed claims, broken relative links, and unresolved placeholders.
- [ ] Run `git diff --check`.
- [ ] Remove temporary upstream clone before commit.
- [ ] Commit documentation changes.
- [ ] Push a fresh branch, open a PR with `.github/PULL_REQUEST_TEMPLATE.md`, attach it to BOR-38, and add `symphony`.
- [ ] Sweep PR comments, inline comments, reviews, and checks before moving BOR-38 to Human Review.
