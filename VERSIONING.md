# Versioning Guide

Borg UI uses [Semantic Versioning](https://semver.org/) (SemVer) for release management.

## Current Version

The current version is stored in the [`VERSION`](./VERSION) file: **v1.0.0**

## How It Works

### Automatic Patch Bumps (Default)

Every push to the `main` branch automatically:
- Increments the **patch** version (e.g., `1.0.0` → `1.0.1`)
- Builds and pushes a Docker image with the new version
- Tags the image as: `1.0.1+abc1234`, `latest`

**Example**: Push to main with VERSION file containing `1.0.0`
```
Docker tags created: 1.0.1+abc1234, latest
```

### Manual Minor/Major Bumps

For minor or major version bumps, use the provided script:

```bash
# Bump patch version (1.0.0 -> 1.0.1)
./scripts/bump-version.sh patch

# Bump minor version (1.0.0 -> 1.1.0)
./scripts/bump-version.sh minor

# Bump major version (1.0.0 -> 2.0.0)
./scripts/bump-version.sh major
```

The script will:
1. Update the `VERSION` file
2. Commit the change
3. Create a git tag (e.g., `v1.1.0`)
4. Provide instructions to push

Then push both the commit and tag:
```bash
git push origin main
git push origin v1.1.0
```

This triggers a release build with semantic version tags:
```
Docker tags: 1.1.0, 1.1, 1, latest
```

## Version Format

### Development Builds (main branch)
Format: `MAJOR.MINOR.PATCH+SHORT_SHA`
- Example: `1.0.1+abc1234`
- Contains commit SHA for traceability

### Release Builds (version tags)
Format: `MAJOR.MINOR.PATCH`
- Example: `1.1.0`
- Clean semantic version

## Docker Tags

### On Main Branch Push
- `latest` - Always points to the latest main build
- `1.0.1+abc1234` - Specific version with commit SHA

### On Version Tag Push (e.g., v1.2.3)
- `latest` - Updated to this release
- `1.2.3` - Full version
- `1.2` - Major.Minor
- `1` - Major only (for v1.x.x and above)

## When to Bump What

Follow Semantic Versioning guidelines:

### PATCH (1.0.0 → 1.0.1)
- Bug fixes
- Documentation updates
- Performance improvements
- No breaking changes
- **This happens automatically on every push to main**

### MINOR (1.0.0 → 1.1.0)
- New features
- New functionality
- Backwards-compatible changes
- **Manual bump using script**

### MAJOR (1.0.0 → 2.0.0)
- Breaking changes
- Major redesigns
- API changes that break compatibility
- **Manual bump using script**

## Example Workflow

### Regular Development (Automatic)
```bash
# Make changes
git add .
git commit -m "feat: add new feature"
git push origin main

# GitHub Actions automatically:
# - Bumps patch: 1.0.0 -> 1.0.1
# - Builds Docker image
# - Tags: 1.0.1+abc1234, latest
```

### Release Minor Version (Manual)
```bash
# Bump to 1.1.0
./scripts/bump-version.sh minor

# Push commit and tag
git push origin main
git push origin v1.1.0

# GitHub Actions automatically:
# - Builds Docker image with v1.1.0 tag
# - Tags: 1.1.0, 1.1, 1, latest
```

### Release Major Version (Manual)
```bash
# Bump to 2.0.0
./scripts/bump-version.sh major

# Push commit and tag
git push origin main
git push origin v2.0.0

# GitHub Actions automatically:
# - Builds Docker image with v2.0.0 tag
# - Tags: 2.0.0, 2.0, 2, latest
```

## Checking Version

### In Docker Container
```bash
docker run --rm karanhudia/borg-ui:latest cat /app/VERSION
```

### In Running Container
```bash
docker exec borg-web-ui cat /app/VERSION
```

### In GitHub Actions
The version is available in the build logs and image labels.

## Docker Hub

Published images: [karanhudia/borg-ui](https://hub.docker.com/r/karanhudia/borg-ui)

All pushes to main and version tags are automatically published to Docker Hub.
