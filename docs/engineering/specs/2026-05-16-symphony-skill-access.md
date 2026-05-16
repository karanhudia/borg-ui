# Symphony Skill Access Verification

Date: 2026-05-16
Issue: BOR-19
Workspace: `/home/karanhudia/code/borg-ui-symphony-workspaces/BOR-19`
HEAD: `e1a16fa`

## Summary

This Symphony/Codex session has access to 39 skill files across repo-local skills,
global/system skills, user-installed skills, and enabled plugin skills.

The requested focus areas are available:

- `ui-ux-pro-max` is installed and its search script runs successfully with
  Python 3.11.2.
- The Superpowers plugin is installed with 14 readable skills, including
  planning, TDD, debugging, verification, review, and branch-completion
  workflows.

No Borg UI runtime files or behavior were changed as part of this verification.

## Verification Evidence

Commands were run from the repository root.

```bash
rg --hidden --files -g SKILL.md .codex/skills /home/karanhudia/.codex/skills /home/karanhudia/.codex/plugins/cache/openai-curated | wc -l
```

Result: `39`

```bash
python3 --version
```

Result: `Python 3.11.2`

```bash
python3 /home/karanhudia/.codex/skills/ui-ux-pro-max/scripts/search.py "saas dashboard professional" --design-system -p "BOR-19 Skill Verification"
```

Result: command exited successfully and returned a design-system recommendation
for `BOR-19 Skill Verification`, proving the `ui-ux-pro-max` skill file,
Python runtime, and backing search data are usable in this session.

## Available Skills

### Repo-local Skills

These skills are available from this repository's `.codex/skills` directory:

- `commit`
- `land`
- `linear`
- `pull`
- `push`

### Global and User Skills

These skills are available from the Codex home skill directories:

- `imagegen`
- `openai-docs`
- `plugin-creator`
- `skill-creator`
- `skill-installer`
- `ui-ux-pro-max`

### Cloudflare Plugin Skills

The enabled Cloudflare plugin contributes 9 skills:

- `cloudflare:agents-sdk`
- `cloudflare:building-ai-agent-on-cloudflare`
- `cloudflare:building-mcp-server-on-cloudflare`
- `cloudflare:cloudflare`
- `cloudflare:durable-objects`
- `cloudflare:sandbox-sdk`
- `cloudflare:web-perf`
- `cloudflare:workers-best-practices`
- `cloudflare:wrangler`

### GitHub Plugin Skills

The enabled GitHub plugin contributes 4 skills:

- `github:gh-address-comments`
- `github:gh-fix-ci`
- `github:github`
- `github:yeet`

### Linear Plugin Skills

The enabled Linear plugin contributes 1 skill:

- `linear:linear`

Note: there is also a repo-local `linear` skill. The plugin-prefixed name
distinguishes the plugin skill from the repository skill.

### Superpowers Plugin Skills

The enabled Superpowers plugin contributes 14 skills:

- `superpowers:brainstorming`
- `superpowers:dispatching-parallel-agents`
- `superpowers:executing-plans`
- `superpowers:finishing-a-development-branch`
- `superpowers:receiving-code-review`
- `superpowers:requesting-code-review`
- `superpowers:subagent-driven-development`
- `superpowers:systematic-debugging`
- `superpowers:test-driven-development`
- `superpowers:using-git-worktrees`
- `superpowers:using-superpowers`
- `superpowers:verification-before-completion`
- `superpowers:writing-plans`
- `superpowers:writing-skills`

## Focus Area Details

### ui-ux-pro-max

Verified path:

```text
/home/karanhudia/.codex/skills/ui-ux-pro-max/SKILL.md
```

The skill is readable and describes a searchable UI/UX design database with
style, color, typography, UX, chart, stack, and design-system workflows. Its
script path is also usable:

```text
/home/karanhudia/.codex/skills/ui-ux-pro-max/scripts/search.py
```

The live script check returned a complete design-system recommendation, so this
session can use `ui-ux-pro-max` for UI/UX design decisions and implementations.

### Superpowers

Verified root:

```text
/home/karanhudia/.codex/plugins/cache/openai-curated/superpowers/dc902811/skills
```

The Superpowers plugin exposes workflow skills for:

- creative/product shaping (`brainstorming`)
- implementation planning (`writing-plans`, `executing-plans`)
- feature and bug-fix discipline (`test-driven-development`,
  `systematic-debugging`)
- verification and reviews (`verification-before-completion`,
  `requesting-code-review`, `receiving-code-review`)
- agent coordination (`dispatching-parallel-agents`,
  `subagent-driven-development`)
- branch lifecycle (`using-git-worktrees`, `finishing-a-development-branch`)
- skill maintenance (`using-superpowers`, `writing-skills`)

## Notes

- This verification reflects the skills visible to the current
  Symphony/Codex session on 2026-05-16.
- Skill availability can vary by workspace, enabled plugins, and installed
  local skill directories.
