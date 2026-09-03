---
name: continue-spec
description: Continue a multi-phase engineering spec from its progress table. Use when the user says /continue-spec, "continue the spec", "continue the operations feature", or asks what the next phase is. Runs the next step (plan, implement, review) in this session on the model the spec names, stopping at the spec's gates. Never uses subagents.
allowed-tools: Read, Bash, Edit, Write, AskUserQuestion, Skill
---

# Continue a spec

You do the next step yourself, in this session. Do not dispatch subagents;
the owner has ruled them out on cost. The spec tells you which model each
step wants; you check the model you are running on and ask before
proceeding if it differs.

## Resolve the spec

1. If an argument is given, it is the spec path.
2. Otherwise, use the newest file under `docs/engineering/specs/` that
   contains a heading matching `## <n>. Working this spec`.
3. If none exists, tell the user and stop.

Current default: `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`.

## Follow the spec's own protocol

Read the spec in full. Its "Working this spec" section defines the progress
table, the continuation protocol, the review focus per phase, and the
gates. Follow it exactly. In short:

1. Find the first phase not `done` in the progress table.
2. Work out the step from its status and the model that step wants from
   the phases table.
3. Gate G0: compare with the model this session runs on. If different, ask
   the user to switch with `/model` and rerun, or to continue anyway. Wait
   for the answer.
4. Do the step in this session:
   - plan: `superpowers:writing-plans`, then gate G1;
   - implement: branch, `superpowers:executing-plans` with
     `superpowers:test-driven-development`, then
     `superpowers:verification-before-completion`, then gate G2;
   - review: `/code-review high` against the listed spec sections, findings
     only, then gate G3.
5. Update the progress table immediately after every state change.

## Rules

- Never commit, push, or merge without the gate answer. See
  `.claude/instructions.md`.
- Never re-open a decision recorded in the spec's Appendix B. Escalate to
  gate G5 instead.
- The spec wins when the plan and the code disagree.
- Report back in plain language: which phase, which step, what was done,
  what the user needs to decide now.
