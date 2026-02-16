# Security Vulnerability Scanning Guide

This guide explains how to check for security vulnerabilities in the borg-ui project.

## Quick Start

Use the provided security scan script:

```bash
# Scan everything
./scripts/security-scan.sh all

# Scan specific components
./scripts/security-scan.sh frontend
./scripts/security-scan.sh backend
./scripts/security-scan.sh trivy
./scripts/security-scan.sh docker
```

Reports are saved in `security-reports/` directory.

## Manual Scanning

### Frontend (JavaScript/npm)

#### npm audit (Built-in)
```bash
cd frontend
npm audit                     # Show vulnerabilities
npm audit --audit-level=high  # Only show high/critical
npm audit fix                 # Auto-fix (minor/patch updates)
npm audit fix --force         # Force major version updates (use with caution)
```

#### Check for outdated packages
```bash
cd frontend
npm outdated                  # Show all outdated packages
```

### Backend (Python)

#### pip-audit (Recommended)
```bash
# Install
pip3 install pip-audit

# Scan
pip-audit -r requirements.txt              # Scan requirements file
pip-audit -r requirements.txt --fix        # Auto-fix vulnerabilities
pip-audit -r requirements.txt --format json > report.json
```

#### Safety
```bash
# Install
pip3 install safety

# Scan
safety check -r requirements.txt
safety check -r requirements.txt --json > safety-report.json
```

#### Check for outdated packages
```bash
pip3 list --outdated
```

### Full Project Scanning

#### Trivy (Comprehensive)
```bash
# Install
brew install aquasecurity/trivy/trivy

# Scan entire project
trivy fs .

# Scan only high/critical
trivy fs --severity HIGH,CRITICAL .

# Scan specific files
trivy fs --scanners vuln frontend/package-lock.json
trivy fs --scanners vuln requirements.txt

# Scan Docker image
trivy image borg-ui:latest

# JSON output
trivy fs --format json --output report.json .
```

#### Snyk
```bash
# Install
npm install -g snyk

# Authenticate (one-time)
snyk auth

# Scan
snyk test                     # Test current project
snyk test --all-projects      # Test all projects
snyk monitor                  # Monitor continuously
```

## Installing Security Tools

### macOS
```bash
# Trivy
brew install aquasecurity/trivy/trivy

# pip-audit
pip3 install pip-audit

# Safety
pip3 install safety

# Snyk
npm install -g snyk

# Grype (alternative to Trivy)
brew install grype
```

### Linux (Ubuntu/Debian)
```bash
# Trivy
sudo apt-get install wget apt-transport-https gnupg lsb-release
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | sudo apt-key add -
echo "deb https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" | sudo tee -a /etc/apt/sources.list.d/trivy.list
sudo apt-get update
sudo apt-get install trivy

# Python tools
pip3 install pip-audit safety

# Snyk
npm install -g snyk
```

### Docker
```bash
# Run Trivy in Docker (no installation needed)
docker run --rm -v $(pwd):/workspace aquasec/trivy fs /workspace

# Scan Docker image
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock aquasec/trivy image borg-ui:latest
```

## CI/CD Integration

### GitHub Actions

Create `.github/workflows/security.yml`:

```yaml
name: Security Scan

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday

jobs:
  npm-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '20'
      - name: Install dependencies
        run: cd frontend && npm ci
      - name: Run npm audit
        run: cd frontend && npm audit --audit-level=moderate

  pip-audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install pip-audit
        run: pip install pip-audit
      - name: Run pip-audit
        run: pip-audit -r requirements.txt

  trivy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          scan-type: 'fs'
          scan-ref: '.'
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'

      - name: Upload Trivy results to GitHub Security tab
        uses: github/codeql-action/upload-sarif@v2
        if: always()
        with:
          sarif_file: 'trivy-results.sarif'
```

## Vulnerability Response Workflow

1. **Identify vulnerabilities**
   ```bash
   ./scripts/security-scan.sh all
   ```

2. **Review the reports** in `security-reports/`
   - Check severity levels (CRITICAL > HIGH > MEDIUM > LOW)
   - Verify if vulnerability is actually exploitable in your context
   - Check if fixed version is available

3. **Update dependencies**

   Frontend:
   ```bash
   cd frontend
   # Update specific package
   npm update react-router-dom
   # Or edit package.json and run
   npm install
   ```

   Backend:
   ```bash
   # Edit requirements.txt with new versions
   # Or use pip-audit --fix (with caution)
   pip-audit -r requirements.txt --fix
   ```

4. **Test after updates**
   ```bash
   # Backend tests
   pytest tests/

   # Frontend tests
   cd frontend && npm test
   ```

5. **Verify fixes**
   ```bash
   ./scripts/security-scan.sh all
   ```

6. **Commit and deploy**
   ```bash
   git add package.json package-lock.json requirements.txt
   git commit -m "security: update vulnerable dependencies"
   ```

## Best Practices

1. **Regular scanning**: Run scans weekly or before each release
2. **Automated CI/CD**: Add security scans to your CI/CD pipeline
3. **Dependency updates**: Keep dependencies reasonably up-to-date
4. **Review before updating**: Always review changes before updating to new major versions
5. **Test after updates**: Run full test suite after dependency updates
6. **Monitor advisories**: Subscribe to security advisories for critical packages
7. **Docker image scanning**: Scan Docker images before deployment

## Understanding Severity Levels

- **CRITICAL**: Immediate action required. Actively exploited or easily exploitable
- **HIGH**: Should be fixed soon. Significant security impact
- **MEDIUM**: Fix in next update cycle. Moderate security impact
- **LOW**: Nice to fix. Minimal security impact

## Common False Positives

Some vulnerabilities may not apply to your use case:
- Development dependencies not used in production
- Vulnerabilities in unused code paths
- Issues that require specific configurations not used in your app

Always verify if a vulnerability actually affects your deployment before panicking.

## Resources

- [npm audit documentation](https://docs.npmjs.com/cli/v8/commands/npm-audit)
- [pip-audit documentation](https://github.com/pypa/pip-audit)
- [Trivy documentation](https://aquasecurity.github.io/trivy/)
- [Snyk documentation](https://docs.snyk.io/)
- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CVE Database](https://cve.mitre.org/)
- [GitHub Security Advisories](https://github.com/advisories)

## Getting Help

If you find a security vulnerability:
1. Check if it's already been reported in the issue tracker
2. For critical security issues, report privately (don't create public issues)
3. Provide details: affected versions, steps to reproduce, potential impact
