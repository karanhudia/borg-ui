---
description: Run a local CodeRabbit review of the branch, fix what is real, then open the PR
allowed-tools: Bash, Read, Edit, Grep, Glob
---

Gate this branch through a local CodeRabbit review before any PR is opened.

1. Confirm the working tree is committed and the branch is pushed. If not, stop and say what is outstanding.
2. Run the review against the base branch (default `main`, or `$ARGUMENTS` if a base is given):

   `coderabbit review --base main --agent -c .claude/instructions.md`

   This can take several minutes. Run it in the background and wait for it once. Do not poll with sleep.
3. Triage every finding. For each one decide: real bug, valid cleanup, or false positive. Do not implement blindly. Verify the claim against the actual code before acting.
4. Fix the real ones. Leave the false positives alone and list them with a one line reason.
5. Re-run the project checks that cover what you touched. Never claim a fix works without running something.
6. Only then create the PR with `gh pr create`, and summarise in the PR body what CodeRabbit flagged and what was fixed.

Report at the end: findings count by severity, what was fixed, what was dismissed and why.
