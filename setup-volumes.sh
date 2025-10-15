#!/bin/bash
# Setup script for Borg UI data volumes
# Creates directory structure with proper permissions

set -e

echo "Creating Borg UI volume directories..."

# Create main data directory structure
mkdir -p ./data/{config,logs,ssh_keys}
mkdir -p ./backups

echo "Setting permissions..."

# Main directories
chmod 755 ./data
chmod 755 ./backups

# Subdirectories
chmod 755 ./data/config
chmod 755 ./data/logs
chmod 700 ./data/ssh_keys  # SSH keys need restricted permissions

# Create .gitkeep files to preserve directory structure in git
touch ./data/.gitkeep
touch ./backups/.gitkeep

echo "✓ Volume directories created successfully!"
echo ""
echo "Directory structure:"
echo "  ./data/"
echo "    ├── config/      (Borgmatic configurations)"
echo "    ├── logs/        (Backup job logs)"
echo "    ├── ssh_keys/    (SSH keys - restricted permissions)"
echo "    └── borgmatic.db (SQLite database - created by app)"
echo "  ./backups/         (Borg backup repositories)"
echo ""
echo "You can now run: docker-compose up -d"
