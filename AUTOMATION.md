# Automated Dependency & Security Management

This document explains how automated dependency updates and security scanning work in this project.

## Table of Contents
- [Overview](#overview)
- [Dependabot](#dependabot)
- [Security Scanning](#security-scanning)
- [Auto-Merge](#auto-merge)
- [Alternative Tools](#alternative-tools)
- [Configuration](#configuration)
- [Best Practices](#best-practices)

## Overview

This project uses a **multi-layered approach** to automated dependency management:

1. **Dependabot** - Automated dependency updates (GitHub native)
2. **GitHub Actions** - Automated security scanning (npm audit, pip-audit, Trivy)
3. **Auto-merge** - Automatic merging of safe updates
4. **Manual scanning** - On-demand security checks

```
┌─────────────────────────────────────────────────────────┐
│                    Weekly Schedule                       │
│  Monday 9 AM: Dependabot checks for updates             │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              Dependabot Creates PRs                      │
│  • Frontend dependencies (npm)                           │
│  • Backend dependencies (pip)                            │
│  • Docker base images                                    │
│  • GitHub Actions                                        │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│           Automated Security Scans Run                   │
│  ✓ npm audit (frontend)                                 │
│  ✓ pip-audit (backend)                                  │
│  ✓ Trivy (filesystem & Docker)                          │
│  ✓ Unit & Integration tests                             │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────┐
│              All Checks Pass?                            │
└─────────────────────────────────────────────────────────┘
              │                           │
              │ YES                       │ NO
              ▼                           ▼
    ┌──────────────────┐      ┌──────────────────────┐
    │  Auto-merge      │      │  Manual Review       │
    │  (minor/patch)   │      │  Required            │
    └──────────────────┘      └──────────────────────┘
```

## Dependabot

### What is Dependabot?

Dependabot is GitHub's built-in tool for automated dependency updates. It:
- ✅ Scans dependencies for updates and vulnerabilities
- ✅ Creates pull requests automatically
- ✅ Provides security advisories
- ✅ Groups related updates
- ✅ Respects semantic versioning
- ✅ 100% free for GitHub users

### Configuration

Located at: `.github/dependabot.yml`

**What it monitors:**
- **Frontend (npm)**: `frontend/package.json`
- **Backend (pip)**: `requirements.txt`
- **Docker**: `Dockerfile`
- **GitHub Actions**: `.github/workflows/*.yml`

**Schedule:**
- Runs every **Monday at 9 AM**
- Creates up to 10 PRs at a time
- Groups minor/patch updates together

### Dependabot Commands

You can control Dependabot via PR comments:

```bash
# Rebase the PR
@dependabot rebase

# Recreate the PR
@dependabot recreate

# Merge the PR (if you have permissions)
@dependabot merge

# Cancel auto-merge
@dependabot cancel merge

# Ignore this dependency
@dependabot ignore this dependency

# Ignore this major version
@dependabot ignore this major version
```

### Example Dependabot PR

When Dependabot finds an update, it creates a PR like:

```
Title: chore(deps): bump react-router-dom from 7.9.6 to 7.13.0 in /frontend

Body:
Bumps react-router-dom from 7.9.6 to 7.13.0.

Release notes:
- Added feature X
- Fixed bug Y
- Security fix for CVE-XXXX

Changelog:
https://github.com/remix-run/react-router/releases/tag/v7.13.0

Commits:
- abc1234 chore: bump version
- def5678 fix: security issue

---
Dependabot compatibility score: 98%
```

## Security Scanning

### Automated Scans (GitHub Actions)

Located at: `.github/workflows/security.yml`

**When it runs:**
- ✅ Every push to `main` or `develop`
- ✅ Every pull request
- ✅ Weekly on Monday at 9 AM UTC
- ✅ Manually via "Run workflow" button

**What it scans:**

#### 1. Frontend (npm audit)
```bash
npm audit --audit-level=moderate
```
- Checks for known vulnerabilities in npm packages
- Fails build on moderate or higher severity
- Generates JSON and text reports

#### 2. Backend (pip-audit)
```bash
pip-audit -r requirements.txt --strict
```
- Checks for known vulnerabilities in Python packages
- Uses PyPI vulnerability database
- Generates JSON and text reports

#### 3. Filesystem (Trivy)
```bash
trivy fs --severity CRITICAL,HIGH .
```
- Scans all dependencies (npm, pip, Docker)
- Checks for misconfigurations
- Uploads results to GitHub Security tab

#### 4. Docker Image (Trivy)
```bash
trivy image --severity CRITICAL,HIGH borg-ui:latest
```
- Scans built Docker image for vulnerabilities
- Checks base image and all layers
- Runs only on push/schedule (not PRs)

### Viewing Scan Results

**In GitHub UI:**
1. Go to repository **Security** tab
2. Click **Vulnerability alerts**
3. Click **Code scanning alerts**

**In Pull Requests:**
- Security scan results are posted as comments
- Artifacts contain detailed reports
- Failing checks block merge

**Download Reports:**
1. Go to workflow run
2. Scroll to **Artifacts** section
3. Download:
   - `npm-audit-report` (JSON + text)
   - `pip-audit-report` (JSON + text)
   - `trivy-filesystem-report` (text)
   - `trivy-docker-report` (text)

### Manual Scanning

Use the provided script:

```bash
# Scan everything
./scripts/security-scan.sh all

# Scan specific components
./scripts/security-scan.sh frontend
./scripts/security-scan.sh backend
./scripts/security-scan.sh trivy

# Scan Docker image
./scripts/security-scan.sh docker borg-ui:latest
```

Reports saved to: `security-reports/`

## Auto-Merge

### How It Works

Located at: `.github/workflows/dependabot-auto-merge.yml`

**Automatic merge for:**
- ✅ Patch updates (1.2.3 → 1.2.4)
- ✅ Minor updates (1.2.3 → 1.3.0)
- ✅ Only if all tests pass
- ✅ Only if security scans pass

**Manual review required for:**
- ⚠️ Major updates (1.2.3 → 2.0.0)
- ⚠️ Breaking changes
- ⚠️ Failed security scans
- ⚠️ Failed tests

### Disabling Auto-Merge

**For a specific PR:**
```bash
# Comment on the PR:
@dependabot cancel merge
```

**Globally:**
Delete or comment out `.github/workflows/dependabot-auto-merge.yml`

### Security Considerations

Auto-merge is **safe** because:
1. Only runs for patch/minor updates
2. Requires all tests to pass
3. Requires security scans to pass
4. Major updates always need manual review
5. You can cancel anytime

## Alternative Tools

### Renovate (Alternative to Dependabot)

**Pros:**
- More flexible configuration
- Better monorepo support
- Customizable PR grouping
- Supports more package managers

**Cons:**
- Requires separate installation
- More complex configuration
- Not GitHub-native

**Setup:**
```bash
# Install Renovate GitHub App
https://github.com/apps/renovate
```

Configuration example (`.github/renovate.json`):
```json
{
  "extends": ["config:base"],
  "schedule": ["every monday"],
  "vulnerabilityAlerts": {
    "enabled": true
  },
  "packageRules": [
    {
      "matchUpdateTypes": ["minor", "patch"],
      "automerge": true
    }
  ]
}
```

### Snyk

**Pros:**
- Deep security analysis
- Vulnerability database
- Fix suggestions
- License scanning

**Cons:**
- Paid for private repos (free tier available)
- Requires external service

**Setup:**
```bash
# Install Snyk GitHub App
https://github.com/apps/snyk-io

# Or use CLI
npm install -g snyk
snyk auth
snyk test
snyk monitor
```

### GitHub Security Features (Built-in)

**Dependabot Security Alerts:**
- Enabled by default
- Notifies about vulnerabilities
- Creates security PRs automatically

**Enable:**
1. Repository Settings
2. Security & analysis
3. Enable "Dependabot alerts"
4. Enable "Dependabot security updates"

**Code Scanning:**
- Scans code for security issues
- Uses CodeQL (GitHub's engine)

**Enable:**
1. Repository Security tab
2. Enable code scanning
3. Set up CodeQL workflow

## Configuration

### Customizing Dependabot

Edit `.github/dependabot.yml`:

```yaml
# Change schedule
schedule:
  interval: "daily"  # or "weekly", "monthly"
  day: "friday"      # for weekly
  time: "15:00"      # 24-hour format

# Change PR limit
open-pull-requests-limit: 5

# Ignore specific dependencies
ignore:
  - dependency-name: "react"
    versions: ["18.x"]

# Custom labels
labels:
  - "dependencies"
  - "automerge"

# Custom commit message
commit-message:
  prefix: "deps"
  prefix-development: "deps-dev"
  include: "scope"
```

### Customizing Security Scans

Edit `.github/workflows/security.yml`:

```yaml
# Change severity threshold
npm audit --audit-level=high  # or "low", "moderate", "critical"

# Change Trivy severity
severity: 'CRITICAL'  # or 'HIGH,CRITICAL' or 'CRITICAL,HIGH,MEDIUM'

# Change schedule
schedule:
  - cron: '0 0 * * *'  # Daily at midnight UTC

# Add notifications
- name: Notify on failure
  if: failure()
  uses: 8398a7/action-slack@v3
  with:
    status: ${{ job.status }}
    webhook_url: ${{ secrets.SLACK_WEBHOOK }}
```

### Customizing Auto-Merge

Edit `.github/workflows/dependabot-auto-merge.yml`:

```yaml
# Only auto-merge patch updates
if: steps.metadata.outputs.update-type == 'version-update:semver-patch'

# Auto-merge all non-major updates
if: |
  (steps.metadata.outputs.update-type != 'version-update:semver-major')

# Auto-merge specific packages only
if: |
  (steps.metadata.outputs.dependency-names == 'react-router-dom' ||
   steps.metadata.outputs.dependency-names == 'axios')
```

## Best Practices

### 1. Monitor Dependabot PRs

Check your PRs regularly:
```bash
# View open Dependabot PRs
https://github.com/YOUR_USERNAME/borg-ui/pulls?q=is%3Apr+is%3Aopen+author%3Aapp%2Fdependabot
```

### 2. Review Security Alerts

**Weekly routine:**
1. Check GitHub Security tab
2. Review Dependabot PRs
3. Check workflow runs
4. Download and review security reports

### 3. Test Before Merging

Even with auto-merge:
1. Download artifacts from workflow
2. Review changelogs for major updates
3. Test locally if unsure
4. Check for breaking changes

### 4. Keep Dependabot Config Updated

```bash
# Review quarterly
- Are PR limits appropriate?
- Are ignored packages still needed?
- Is the schedule optimal?
- Are labels helpful?
```

### 5. Balance Automation vs Control

**High automation** (recommended for most teams):
- Auto-merge patch updates: ✅
- Auto-merge minor updates: ✅
- Auto-merge major updates: ❌

**Medium automation** (for critical systems):
- Auto-merge patch updates: ✅
- Auto-merge minor updates: ❌
- Auto-merge major updates: ❌

**Low automation** (for highly regulated):
- Auto-merge patch updates: ❌
- Auto-merge minor updates: ❌
- Auto-merge major updates: ❌

### 6. Response Times

**Critical vulnerabilities** (CVSS 9.0+):
- Review within: 24 hours
- Merge within: 48 hours

**High vulnerabilities** (CVSS 7.0-8.9):
- Review within: 1 week
- Merge within: 2 weeks

**Medium vulnerabilities** (CVSS 4.0-6.9):
- Review within: 1 month
- Merge within: Next release

### 7. Documentation

Keep this updated:
- `SECURITY-UPDATE-SUMMARY.md` - After each security update
- `CHANGELOG.md` - For all dependency changes
- `README.md` - If automation changes workflow

## Troubleshooting

### Dependabot Not Creating PRs

**Check:**
1. Is `.github/dependabot.yml` valid?
   - Use GitHub's config validator
   - Check YAML syntax
2. Are PR limits reached?
   - Close old Dependabot PRs
   - Increase `open-pull-requests-limit`
3. Are dependencies ignored?
   - Check `ignore:` section
4. Is repository archived or disabled?

### Security Scans Failing

**Common issues:**

1. **npm audit fails:**
   ```bash
   # Locally reproduce
   cd frontend
   npm audit

   # Check specific vulnerability
   npm audit --json | jq
   ```

2. **pip-audit fails:**
   ```bash
   # Locally reproduce
   pip-audit -r requirements.txt

   # Check with verbose output
   pip-audit -r requirements.txt -v
   ```

3. **Trivy fails:**
   ```bash
   # Locally reproduce
   trivy fs --severity CRITICAL,HIGH .

   # Skip specific vulnerabilities
   trivy fs --severity CRITICAL,HIGH --ignore-unfixed .
   ```

### Auto-Merge Not Working

**Check:**
1. Are tests passing?
2. Are security scans passing?
3. Is it a patch/minor update?
4. Does the workflow have permissions?
   - Repository Settings → Actions → General
   - Enable "Allow GitHub Actions to create and approve pull requests"

## Resources

- [Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [GitHub Actions Security](https://docs.github.com/en/actions/security-guides)
- [Trivy Documentation](https://aquasecurity.github.io/trivy/)
- [npm audit Documentation](https://docs.npmjs.com/cli/v8/commands/npm-audit)
- [pip-audit Documentation](https://github.com/pypa/pip-audit)

## Getting Help

**For this project:**
- GitHub Issues: Report problems
- GitHub Discussions: Ask questions

**General:**
- GitHub Support: https://support.github.com
- Stack Overflow: Tag with `dependabot`, `github-actions`
