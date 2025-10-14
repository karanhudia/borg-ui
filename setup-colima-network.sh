#!/bin/bash

# This script reconfigures Colima to use bridged networking
# This allows Docker containers to access your Mac's local network

echo "⚠️  This will stop and restart Colima with bridged networking"
echo "Current Colima status:"
colima status

read -p "Do you want to continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]
then
    echo "Aborted."
    exit 1
fi

echo ""
echo "Stopping Colima..."
colima stop

echo ""
echo "Starting Colima with bridged network..."
colima start \
  --network-address \
  --cpu 2 \
  --memory 4 \
  --disk 60

echo ""
echo "✅ Colima restarted with bridged networking"
echo ""
echo "Now containers can access your Mac's network (192.168.1.x)"
echo ""
echo "Rebuild your containers:"
echo "  docker-compose down && docker-compose up -d --build"
