# Versioning & Release Process

Borg UI uses [Semantic Versioning](https://semver.org/) (SemVer) for release management.

## Current Version

The current version is stored in the [`VERSION`](./VERSION) file: **v1.0.0**

## Release Process

Docker images are built **only on version tags**, not on every push to main. This ensures controlled releases.

### Creating a Release

Use the provided script to bump the version and create a release:

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
3. Create a git tag (e.g., `v1.0.1`)
4. Provide instructions to push

Then push both the commit and tag:
```bash
git push origin main
git push origin v1.0.1
```

This triggers GitHub Actions to:
- Build Docker image for both `amd64` and `arm64` platforms
- Push to Docker Hub with semantic version tags
- Update the `latest` tag

## Version Format

All releases use clean semantic versioning: `MAJOR.MINOR.PATCH`
- Example: `1.0.1`
- No commit SHAs or build metadata in version tags

## Docker Tags

### On Version Tag Push (e.g., v1.2.3)
- `latest` - Updated to this release
- `1.2.3` - Full version
- `1.2` - Major.Minor
- `1` - Major only (for v1.x.x and above)

### Example
Pushing tag `v1.2.3` creates Docker tags:
```
karanhudia/borg-ui:latest
karanhudia/borg-ui:1.2.3
karanhudia/borg-ui:1.2
karanhudia/borg-ui:1
```

## When to Bump What

Follow Semantic Versioning guidelines:

### PATCH (1.0.0 → 1.0.1)
- Bug fixes
- Documentation updates
- Performance improvements
- Security patches
- No breaking changes
- No new features

### MINOR (1.0.0 → 1.1.0)
- New features
- New functionality
- Backwards-compatible changes
- Deprecations (with warnings)

### MAJOR (1.0.0 → 2.0.0)
- Breaking changes
- Major redesigns
- API changes that break compatibility
- Removal of deprecated features

## Release Workflow Example

### Bug Fix Release
```bash
# Fix a bug in the code
git add .
git commit -m "fix: resolve archive browsing issue"
git push origin main

# Create patch release
./scripts/bump-version.sh patch
# This updates VERSION to 1.0.1 and creates tag v1.0.1

# Push release
git push origin main
git push origin v1.0.1

# GitHub Actions automatically:
# - Builds Docker image for amd64 and arm64
# - Pushes tags: 1.0.1, 1.0, 1, latest to Docker Hub
```

### Feature Release
```bash
# Add a new feature
git add .
git commit -m "feat: add SSH repository support"
git push origin main

# Create minor release
./scripts/bump-version.sh minor
# This updates VERSION to 1.1.0 and creates tag v1.1.0

# Push release
git push origin main
git push origin v1.1.0

# GitHub Actions automatically builds and publishes
```

### Breaking Change Release
```bash
# Make breaking changes
git add .
git commit -m "feat!: redesign API endpoints (BREAKING CHANGE)"
git push origin main

# Create major release
./scripts/bump-version.sh major
# This updates VERSION to 2.0.0 and creates tag v2.0.0

# Push release
git push origin main
git push origin v2.0.0

# GitHub Actions automatically builds and publishes
```

## Manual Builds

You can trigger a build manually from the GitHub Actions UI:
1. Go to Actions tab
2. Select "Build and Publish Docker Images"
3. Click "Run workflow"
4. Select the tag to build

## Checking Version

### In Docker Container
```bash
docker run --rm karanhudia/borg-ui:latest cat /app/VERSION
```

### In Running Container
```bash
docker exec borg-web-ui cat /app/VERSION
```

### In Web UI
The version is displayed in the UI footer (or Settings page, if implemented).

## Docker Hub

Published images: [karanhudia/borg-ui](https://hub.docker.com/r/karanhudia/borg-ui)

All version tags are automatically published to Docker Hub with multi-platform support (amd64/arm64).

## Development Workflow

For day-to-day development:

```bash
# Make changes
git add .
git commit -m "feat: add new feature"
git push origin main
# No Docker build happens yet

# Continue working
git commit -m "fix: small bug"
git push origin main
# Still no build

# When ready to release
./scripts/bump-version.sh patch  # or minor/major
git push origin main
git push origin v1.0.1
# Now Docker build triggers
```

This approach ensures:
- No unnecessary builds on every push
- Clean version history
- Controlled releases
- Better CI/CD resource usage
