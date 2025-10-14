# Installing Borgmatic UI on Raspberry Pi

This guide will help you install Borgmatic UI on your Raspberry Pi.

---

## Prerequisites

- Raspberry Pi (any model with Docker support)
- Raspberry Pi OS (formerly Raspbian) or Ubuntu Server
- Internet connection
- SSH access to your Pi

---

## Step 1: Install Docker

### Option A: Using the official Docker script (Recommended)

```bash
# SSH into your Raspberry Pi
ssh pi@raspberrypi.local

# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker using official script
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Add your user to docker group (so you don't need sudo)
sudo usermod -aG docker $USER

# Log out and back in for group changes to take effect
exit
# SSH back in
ssh pi@raspberrypi.local

# Verify Docker is working
docker --version
docker run hello-world
```

### Option B: Using apt (Alternative)

```bash
sudo apt update
sudo apt install -y docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker $USER
```

---

## Step 2: Install Docker Compose

```bash
# Install docker-compose
sudo apt install -y docker-compose

# Or install the latest version manually:
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Verify
docker-compose --version
```

---

## Step 3: Clone and Configure Borgmatic UI

```bash
# Create directory for the app
cd /opt
sudo mkdir borgmatic-ui
sudo chown $USER:$USER borgmatic-ui
cd borgmatic-ui

# Clone the repository
git clone <repo-url> .

# Or download manually if no git:
wget https://github.com/your-repo/archive/main.zip
unzip main.zip
cd borgmatic-ui-main
```

---

## Step 4: Configure for Raspberry Pi (Linux)

Since Raspberry Pi runs Linux, we can use host networking for full network access:

```bash
# Edit docker-compose.yml
nano docker-compose.yml

# Make sure this line is UNCOMMENTED:
network_mode: "host"

# And these lines are COMMENTED:
# networks:
#   - borgmatic-network
# extra_hosts:
#   - "host.docker.internal:host-gateway"
```

Or create a Raspberry Pi specific override:

```bash
# Create docker-compose.raspberry-pi.yml
cat > docker-compose.raspberry-pi.yml << 'EOF'
version: '3.8'

services:
  borgmatic-ui:
    # Use host network on Linux/Raspberry Pi
    network_mode: "host"

    # Remove conflicting settings
    ports: []
    networks: []
    extra_hosts: []
EOF
```

---

## Step 5: Configure Docker Image

**IMPORTANT:** Choose between pre-built image (fast) or local build (slow):

### Option A: Pre-built Image (RECOMMENDED - 30-60 seconds)

```bash
# Create .env file
cp .env.example .env

# Edit .env and set your Docker Hub image
nano .env

# Change this line to use the official pre-built image:
DOCKER_IMAGE=yourusername/borgmatic-ui:latest
```

**Result:** Installation completes in under 2 minutes! ✨

### Option B: Build Locally (20-40 minutes)

Only use this if you're developing or can't access Docker Hub:

```bash
# Edit docker-compose.yml
nano docker-compose.yml

# Comment out the 'image' line and uncomment 'build':
# image: ${DOCKER_IMAGE:-yourusername/borgmatic-ui:latest}
build: .
```

**Note:** First build on Raspberry Pi takes **20-40 minutes**:
- Pi 3: ~40 minutes
- Pi 4: ~25 minutes
- Pi 5: ~15 minutes

This is because Docker must compile Python packages for ARM architecture.

### Monitor Build Progress

```bash
# Watch the build (you'll see progress bars)
docker-compose up --build

# Or build in background and monitor logs
docker-compose up -d --build
docker-compose logs -f
```

### Using standard docker-compose:

```bash
# First time (will take 20-40 minutes)
docker-compose up -d --build

# Check logs
docker-compose logs -f
```

### Or using the Raspberry Pi override:

```bash
docker-compose -f docker-compose.yml -f docker-compose.raspberry-pi.yml up -d --build
```

### 🚀 Optional: Use Optimized Dockerfile (Faster Build)

For faster builds, use the Pi-optimized Dockerfile:

```bash
# Edit docker-compose.yml
nano docker-compose.yml

# Change this line:
#   build: .
# To:
#   build:
#     context: .
#     dockerfile: Dockerfile.pi-optimized

# Then build
docker-compose up -d --build
```

The optimized version uses system packages instead of compiling from source, reducing build time by ~50%.

---

## Step 6: Access the UI

With host networking, the app runs directly on port 8000:

```bash
# From the Raspberry Pi itself:
http://localhost:8000

# From another computer on your network:
http://raspberrypi.local:8000
# Or use the IP address:
http://192.168.1.XXX:8000
```

**Find your Pi's IP:**
```bash
hostname -I
```

**Default login:**
- Username: `admin`
- Password: `admin123`

**⚠️ Change the default password immediately!**

---

## Step 7: Test SSH Access

Since the Pi uses host networking, it can SSH to any device on your network:

```bash
# Test from inside the container
docker exec borgmatic-web-ui ssh -o ConnectTimeout=5 user@192.168.1.150 echo "SSH works!"

# Or enter the container
docker exec -it borgmatic-web-ui bash
ssh user@192.168.1.150
```

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs

# Check if port 8000 is already in use
sudo netstat -tlnp | grep 8000

# If port is in use, kill the process or change the port
```

### Can't access from other devices

```bash
# Check firewall
sudo ufw status

# Allow port 8000 if firewall is enabled
sudo ufw allow 8000

# Check if service is listening
sudo netstat -tlnp | grep 8000
```

### SSH from container doesn't work

```bash
# Test network connectivity
docker exec borgmatic-web-ui ping -c 3 192.168.1.150

# Test SSH port
docker exec borgmatic-web-ui nc -zv 192.168.1.150 22

# Check if sshpass is installed
docker exec borgmatic-web-ui which sshpass
```

### Out of memory / Performance issues

Raspberry Pi has limited RAM. You can:

```bash
# Reduce Docker worker count (edit Dockerfile)
# Change from: --workers 1
# Or add memory limits to docker-compose.yml:

services:
  borgmatic-ui:
    mem_limit: 512m
    memswap_limit: 1g
```

---

## Automatic Startup

Docker Compose services start automatically with the `restart: unless-stopped` policy.

To ensure it starts on boot:

```bash
# Enable Docker service
sudo systemctl enable docker

# Your container will start automatically
```

---

## Updating

```bash
cd /opt/borgmatic-ui

# Pull latest changes
git pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build

# Or with override:
docker-compose -f docker-compose.yml -f docker-compose.raspberry-pi.yml down
docker-compose -f docker-compose.yml -f docker-compose.raspberry-pi.yml up -d --build
```

---

## Performance Tips for Raspberry Pi

1. **Use SSD instead of SD card** - Much faster and more reliable
2. **Enable swap** - Helps with memory-intensive operations
3. **Use external storage** - For backup destinations
4. **Schedule backups during off-hours** - Reduce load during peak usage

```bash
# Check current swap
free -h

# Add swap if needed (1GB example)
sudo fallocate -l 1G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# Make permanent
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Uninstall

```bash
cd /opt/borgmatic-ui

# Stop and remove containers
docker-compose down -v

# Remove images
docker rmi borgmatic-web-ui

# Remove files
cd ..
sudo rm -rf borgmatic-ui
```

---

## Next Steps

1. **Change default password** - Settings → Profile
2. **Generate SSH key** - SSH Keys → Generate New Key
3. **Add backup destinations** - Repositories → Add New
4. **Configure backup job** - Backups → Create New Job
5. **Test backup** - Run a manual backup first

---

## Security Recommendations

1. **Change default password immediately**
2. **Use strong SSH key passphrases**
3. **Enable firewall** (ufw)
4. **Keep system updated** (`sudo apt update && sudo apt upgrade`)
5. **Use HTTPS** if exposing to internet (use reverse proxy like Nginx/Caddy)
6. **Restrict SSH access** to trusted IPs only

---

## Support

- **Issues:** https://github.com/your-repo/issues
- **Docs:** https://github.com/your-repo/docs
- **Raspberry Pi Forum:** https://forums.raspberrypi.com/
