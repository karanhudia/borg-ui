# Borgmatic UI Optimization Tasks

## Backend Changes

### 1. Change Default Port from 8000 to 8081
- **Why:** Port 8000 conflicts with Portainer, 8081 is more suitable default
- **Files to modify:**
  - `Dockerfile` - Change EXPOSE and gunicorn bind port
  - `docker-compose.yml` - Update port mapping
  - Documentation files
- **Status:** Pending

### 2. Create .env.example for Portainer
- **Why:** Users need a template for environment variables in Portainer
- **Requirements:**
  - All environment variables documented
  - Sensible defaults provided
  - Clear comments explaining each variable
  - Portainer-friendly format
- **Variables to include:**
  - `SECRET_KEY` (with generation instructions)
  - `PORT` (default: 8081)
  - `DATABASE_URL` (default: sqlite:////data/borgmatic.db)
  - `CONFIG_DIR` (default: /data)
  - `BACKUP_DIR` (default: /backups)
  - `LOG_LEVEL` (default: INFO)
  - `ENVIRONMENT` (default: production)
- **Status:** Pending

### 3. Fix Database Persistence
- **Problem:** Database resets when container is removed
- **Root Cause:** DATABASE_URL currently points to `/app/data/borgmatic.db` which is inside container
- **Solution:**
  - Change default DATABASE_URL to `/data/borgmatic.db`
  - Mount `/data` volume to host directory
  - Ensure proper permissions for UID 1001
- **Files to modify:**
  - `app/config.py` - Update default DATABASE_URL
  - `docker-compose.yml` - Update volume mounts
  - `Dockerfile` - Create /data directory
- **Status:** Pending

### 4. Default Config Directory (Portainer-style)
- **Why:** Follow Docker best practices like Portainer
- **Implementation:**
  - Single `/data` directory for all persistent data
  - Structure:
    ```
    /data/
    ├── borgmatic.db (SQLite database)
    ├── ssh_keys/ (SSH key storage)
    ├── logs/ (Application logs)
    └── config/ (Borgmatic YAML configs)
    ```
  - When no volume mounted: Docker creates named volume automatically
  - When volume mounted: User controls the location
- **Environment Variable:** `DATA_DIR=/data` (configurable)
- **Status:** Pending

### 5. Fix SSH Commands
- **Issues Found in Logs:**
  - "Load key error in libcrypto" - SSH key permission/format issue
  - "Connection timeout" errors - Network/firewall issues
  - Unnecessary retries and error clutter
- **Tasks:**
  - Review `app/api/ssh_keys.py` for all SSH operations
  - Fix SSH key file permissions (must be 600)
  - Remove unnecessary SSH connection retries
  - Improve error handling and user feedback
  - Test each SSH command:
    - ✓ SSH key generation
    - ✓ SSH key deployment (ssh-copy-id)
    - ✓ SSH connection testing
    - ✓ SSH repository initialization
  - Remove features that don't work or aren't needed
- **Status:** Pending

### 6. Backend Testing
- **Requirements:**
  - Test all API endpoints
  - Verify database persistence after container restart
  - Test SSH key operations
  - Verify environment variables work correctly
  - Test with mounted volumes and without
- **Status:** Pending

## Frontend Changes (After Backend Complete)

### 7. Modernize UI with Material-UI (MUI)
- **Why:** Modern, professional look with better UX
- **Tasks:**
  - Install MUI: `@mui/material @mui/icons-material @emotion/react @emotion/styled`
  - Replace current components with MUI components:
    - Buttons → MUI Button
    - Forms → MUI TextField, Select
    - Tables → MUI Table/DataGrid
    - Cards → MUI Card
    - Navigation → MUI AppBar, Drawer
    - Alerts → MUI Alert, Snackbar
  - Implement MUI theme with dark mode support
  - Use MUI icons instead of custom icons
- **Status:** Pending

### 8. Fix UI Alignments and Design
- **Issues to Address:**
  - Inconsistent spacing
  - Poor mobile responsiveness
  - Layout alignment issues
  - Typography inconsistencies
- **Improvements:**
  - Use MUI Grid/Box for consistent layouts
  - Implement proper spacing system (8px baseline)
  - Add responsive breakpoints
  - Improve form layouts
  - Better visual hierarchy
  - Add loading states and skeleton loaders
  - Improve error message display
- **Status:** Pending

## Implementation Order

1. ✅ Document all tasks (this file)
2. ⏳ Backend: Change port to 8081
3. ⏳ Backend: Create .env.example
4. ⏳ Backend: Fix database persistence
5. ⏳ Backend: Implement /data directory structure
6. ⏳ Backend: Fix SSH commands
7. ⏳ Backend: Test everything thoroughly
8. ⏳ Frontend: Install and configure MUI
9. ⏳ Frontend: Modernize components
10. ⏳ Frontend: Fix alignments and responsive design
11. ⏳ Final testing and cleanup
12. ⏳ Delete this document

## Docker Run Command (After Changes)

```bash
docker run -d \
  --name borgmatic-web-ui \
  -p 8081:8081 \
  -v borgmatic_data:/data \
  -v /path/to/backups:/backups \
  -e SECRET_KEY=$(openssl rand -base64 32) \
  ainullcode/borgmatic-ui:latest
```

## Portainer Stack (After Changes)

```yaml
version: '3.8'
services:
  borgmatic-ui:
    image: ainullcode/borgmatic-ui:latest
    container_name: borgmatic-web-ui
    ports:
      - "8081:8081"
    volumes:
      - borgmatic_data:/data
      - /path/to/backups:/backups
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - PORT=8081
      - LOG_LEVEL=INFO
    restart: unless-stopped

volumes:
  borgmatic_data:
```

---
**Note:** This document will be deleted after all tasks are completed.
