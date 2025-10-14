# GitHub Repository Settings

## Disable Forking (Important!)

To fully enforce the no-forking policy, you need to disable forking in GitHub settings:

### Steps:

1. **Go to your repository:** https://github.com/karanhudia/borg-ui

2. **Click "Settings"** (top right, requires admin access)

3. **Scroll down to "Features" section**

4. **UNCHECK "Forks"**
   - This will prevent users from forking your repository
   - Users will see "Fork" button grayed out with tooltip explaining why

5. **Click "Save"**

### Alternative: Keep Forks Enabled (Less Restrictive)

If you want to allow forks but rely on the license to prevent misuse:

- Keep "Forks" enabled
- The LICENSE file clearly states forking is not permitted
- Users who fork anyway are violating the license terms
- You can send DMCA takedown notices to GitHub for unauthorized forks

### Recommended: Disable Forks

**Pros:**
- Technically prevents forking
- Clear message to users
- No need for DMCA takedowns

**Cons:**
- Users familiar with forking workflow may be confused
- Still possible to clone (which is allowed for PRs)

## Other Important Settings

### General

- **Repository name:** borg-ui
- **Description:** Web UI for Borgmatic - Self-hosted backup management
- **Website:** https://hub.docker.com/r/ainullcode/borgmatic-ui
- **Topics:** backup, borgmatic, borg, docker, raspberry-pi, web-ui

### Features

- ✅ **Issues** - Keep enabled for bug reports
- ✅ **Pull requests** - Keep enabled for contributions
- ✅ **Discussions** - Enable for community Q&A
- ❌ **Forks** - DISABLE to prevent forking
- ✅ **Projects** - Optional, for roadmap
- ✅ **Wiki** - Optional, for extended docs

### Pull Requests

- ✅ **Allow merge commits** - Keep enabled
- ✅ **Allow squash merging** - Recommended for clean history
- ✅ **Allow rebase merging** - Optional
- ✅ **Always suggest updating pull request branches** - Recommended
- ✅ **Automatically delete head branches** - Recommended

### Branches

**Branch protection rules for `main`:**

1. Go to Settings → Branches
2. Click "Add rule"
3. Branch name pattern: `main`
4. Enable:
   - ✅ Require a pull request before merging
   - ✅ Require approvals (1)
   - ✅ Require status checks to pass before merging
   - ✅ Require branches to be up to date before merging
   - ✅ Include administrators (so even you follow the process)
   - ✅ Restrict who can push to matching branches (only you)

### GitHub Pages (Optional)

If you want to host documentation:

- Source: Deploy from branch `gh-pages` or `docs` folder
- Custom domain: Optional

### Actions

- ✅ **Allow all actions and reusable workflows** - For Docker build workflow
- Set workflow permissions:
  - ✅ Read and write permissions
  - ✅ Allow GitHub Actions to create and approve pull requests

### Secrets

Already configured:
- ✅ DOCKERHUB_USERNAME
- ✅ DOCKERHUB_TOKEN

### Security

- ✅ **Private vulnerability reporting** - Enable
- ✅ **Dependency graph** - Enable
- ✅ **Dependabot alerts** - Enable
- ✅ **Dependabot security updates** - Enable
- ❌ **Dependabot version updates** - Optional

### Moderation

- Set up code of conduct: Use "Contributor Covenant"
- Add issue templates
- Add discussion categories

## Visibility

**Current:** Public (for Docker Hub publishing)

**Options:**
- Keep public if you want community engagement
- Make private if this is proprietary and you want to restrict access further
  - Note: Private repos limit GitHub Actions minutes (2000/month free)
  - Docker Hub images can still be public even with private repo

## Collaborators

Add trusted contributors:
- Settings → Collaborators and teams
- Add with "Write" access (can push branches, cannot merge to main without PR)

## Webhooks (Optional)

Set up webhooks for:
- Discord/Slack notifications on new issues/PRs
- Deployment automation
- Status monitoring

## Templates

Already added:
- ✅ PULL_REQUEST_TEMPLATE.md
- ✅ CONTRIBUTING.md

Consider adding:
- Issue templates for bug reports
- Issue templates for feature requests
- Discussion templates

## Labels

Default labels are fine, but consider adding:
- `license-violation` - For reporting forks/copies
- `good-first-issue` - For newcomers
- `needs-discussion` - For features requiring approval

## Monitoring

**Watch for:**
- Unauthorized forks (if you kept forks enabled)
- License violations (people using code elsewhere)
- DMCA takedown needs

**Tools:**
- GitHub API to check for forks: `https://api.github.com/repos/karanhudia/borg-ui/forks`
- Google search: `"your-unique-code-snippet" -site:github.com/karanhudia`

---

## Quick Checklist

- [ ] Disable forking in Settings → Features
- [ ] Set up branch protection for `main`
- [ ] Enable discussions for community Q&A
- [ ] Add issue templates
- [ ] Configure Dependabot
- [ ] Enable private vulnerability reporting
- [ ] Add repository topics/tags
- [ ] Add repository description and website
- [ ] Review and configure GitHub Actions permissions

---

**After disabling forks:** Users who try to fork will see a message that forking is disabled by the repository owner.
