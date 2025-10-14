# Docker Hub Publishing Setup

This guide shows you how to publish your Borgmatic UI image to Docker Hub so users can pull it instantly instead of waiting 20-40 minutes to build.

## Why Publish to Docker Hub?

**Without Docker Hub (Building Locally):**
- ❌ Users wait 20-40 minutes on Raspberry Pi
- ❌ Users need build tools (gcc, node, etc.)
- ❌ High memory usage during build
- ❌ Can fail on low-resource devices

**With Docker Hub (Pre-built Images):**
- ✅ **Users wait 30-60 seconds** (just pulling the image)
- ✅ No build tools needed
- ✅ Low memory usage
- ✅ Works on all devices
- ✅ Multi-arch support (amd64, arm64, armv7)

## Step 1: Create Docker Hub Account

1. Go to https://hub.docker.com/
2. Sign up (it's free for public images)
3. Verify your email

## Step 2: Create Access Token

1. Login to Docker Hub
2. Click your profile → **Account Settings**
3. Click **Security** → **New Access Token**
4. Name it: `github-actions`
5. Permissions: **Read, Write, Delete**
6. Click **Generate**
7. **Copy the token** (you won't see it again!)

## Step 3: Add Secrets to GitHub

1. Go to your GitHub repository
2. Click **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add these secrets:

   **Secret 1:**
   - Name: `DOCKERHUB_USERNAME`
   - Value: Your Docker Hub username (e.g., `karanhudia`)

   **Secret 2:**
   - Name: `DOCKERHUB_TOKEN`
   - Value: The access token you copied

## Step 4: Update docker-compose.yml

Edit `docker-compose.yml` and replace `yourusername` with your Docker Hub username:

```yaml
services:
  borgmatic-ui:
    image: ${DOCKER_IMAGE:-karanhudia/borgmatic-ui:latest}
```

Or set it in `.env`:
```bash
DOCKER_IMAGE=karanhudia/borgmatic-ui:latest
```

## Step 5: Push to GitHub

Commit your changes and push to GitHub:

```bash
git add .
git commit -m "Add Docker Hub publishing workflow"
git push origin main
```

## Step 6: Watch the Build

1. Go to your GitHub repository
2. Click **Actions** tab
3. You'll see "Build and Publish Docker Images" workflow running
4. Click on it to watch the build progress

**This takes 30-60 minutes** but only needs to happen once (and on each update).

## Step 7: Verify Images

Once the build completes:

1. Go to https://hub.docker.com/r/yourusername/borgmatic-ui
2. You should see:
   - Tag: `latest`
   - Architectures: `amd64`, `arm64`, `armv7`
   - Size: ~500MB-800MB

## Step 8: Test the Published Image

### On Linux (including Raspberry Pi):

```bash
# Pull the image (should take 30-60 seconds)
docker pull yourusername/borgmatic-ui:latest

# Run it
docker-compose up -d

# Check it started
docker-compose ps
```

### On macOS:

```bash
docker pull yourusername/borgmatic-ui:latest
docker-compose up -d
```

## Automatic Builds

The GitHub Action will automatically build and publish:
- ✅ On every push to `main` branch → `latest` tag
- ✅ On every git tag (e.g., `v1.0.0`) → versioned tag (e.g., `1.0.0`)
- ✅ Multi-arch images (amd64 + arm64 + armv7)

## Versioning

To release a new version:

```bash
# Tag your release
git tag v1.0.0
git push origin v1.0.0
```

This will create:
- `yourusername/borgmatic-ui:1.0.0`
- `yourusername/borgmatic-ui:latest` (updated)

## Manual Build (Alternative)

If you prefer to build and push manually:

```bash
# Login to Docker Hub
docker login

# Build for multiple architectures
docker buildx create --use
docker buildx build \
  --platform linux/amd64,linux/arm64,linux/arm/v7 \
  --tag yourusername/borgmatic-ui:latest \
  --push \
  .
```

## Update Documentation

Once your image is published, update your README:

```markdown
## Quick Start

```bash
# Pull the pre-built image (30 seconds)
docker pull yourusername/borgmatic-ui:latest

# Start the service
docker-compose up -d

# Access at http://localhost:8000
```

**No building required!** ✨
```

## For Users

Users can now install in **under 2 minutes**:

```bash
# Clone repo
git clone https://github.com/yourusername/borgmatic-ui
cd borgmatic-ui

# Start (pulls pre-built image)
docker-compose up -d
```

**That's it!** No 40-minute build, no compilation, no waiting.

## Troubleshooting

### GitHub Action Fails

**Check secrets:**
```bash
# Make sure these are set in GitHub Settings → Secrets
DOCKERHUB_USERNAME
DOCKERHUB_TOKEN
```

**Check Dockerfile:**
```bash
# Make sure Dockerfile builds successfully locally
docker build -t test .
```

### Image Too Large

Current image size: ~500-800MB (normal for this stack)

To reduce:
- Use Alpine instead of Debian (but may break some packages)
- Use multi-stage builds (already doing this)
- Exclude docs and unnecessary files

### Multi-arch Build Fails

GitHub Actions uses QEMU for cross-compilation. If it fails:
- Check the logs in Actions tab
- May need to split into separate workflows for each arch
- Some packages may not support armv7 (can drop it)

## Cost

**GitHub Actions:** Free for public repositories (2000 minutes/month)
**Docker Hub:** Free for public images (unlimited pulls)
**Total cost:** $0/month

For private repositories:
- GitHub Actions: First 2000 minutes free, then $0.008/minute
- Docker Hub: $5/month for private repos

## Next Steps

1. ✅ Set up Docker Hub account
2. ✅ Add GitHub secrets
3. ✅ Push to trigger build
4. ✅ Update documentation with your image name
5. ✅ Test on Raspberry Pi (should be < 2 minutes now!)

---

**Result:** Your app goes from **40-minute install** to **1-minute install** 🚀
