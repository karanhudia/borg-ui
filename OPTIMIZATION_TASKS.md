# Borgmatic UI Optimization Tasks

## ✅ Completed Tasks

### Backend Completed
1. ✅ **Port 8081** - Changed default port from 8000 to 8081
2. ✅ **Database Persistence** - Database now persists in `/data/borgmatic.db` volume
3. ✅ **Data Directory Structure** - Implemented `/data` directory for all persistent data
4. ✅ **.env.example** - Created environment variable template
5. ✅ **SSH Commands** - Analyzed and verified SSH operations
6. ✅ **Repository Path Restrictions** - Removed restrictions, any path now allowed

### Frontend Completed
7. ✅ **Material-UI Installation** - MUI, icons, emotion, and theme configured
8. ✅ **Layout Modernization** - Navigation with MUI AppBar, Drawer, responsive design
9. ✅ **Unified SSH Connections Page** - Merged SSH Keys + Connections into single tab
   - 40/60 split layout (SSH Keys | Connections)
   - Click key to view its connections
   - All features preserved: Quick Setup, Generate, Deploy, Test, Edit, Delete
   - Connection monitoring with auto-refresh (30s)
   - Statistics cards with MUI components
   - Responsive Stack/Box layout

---

## 🔄 Remaining Tasks

### Frontend Tasks

### 1. Improve Repository Creation Form
**Priority: Medium**
- Add dropdown to select from existing SSH connections
- Two repository types:
  1. **SSH Repository**: `ssh://user@host/path`
     - Dropdown populated from active SSH connections
     - Auto-fill username, host, port from selected connection
  2. **Local Repository**: `/any/local/path`
     - Already supports any path
     - Auto-creates directories
- Better form validation and user feedback
- **Files**: `frontend/src/pages/Repositories.tsx`

### 2. Configuration-First Workflow
**Priority: Low**
- Disable all features until valid config saved
- Configuration contains:
  - Source directories (what to backup)
  - Repository (where to backup)
  - Schedule (when to backup)
  - Retention rules
- Auto-generate Borgmatic YAML from UI settings
- Persist in `/data/config/` by default
- **Files**: Multiple - requires architectural changes

### 3. Modernize Remaining Components with MUI
**Priority: Medium**
- **Dashboard.tsx** - Statistics, recent backups, system status
- **Config.tsx** - Configuration forms
- **Backup.tsx** - Backup operations
- **Archives.tsx** - Archive browsing
- **Restore.tsx** - Restore operations
- **Schedule.tsx** - Cron scheduling
- **Repositories.tsx** - Repository management
- **Settings.tsx** - User settings
- Replace all Tailwind classes with MUI components
- Consistent spacing (8px baseline)
- Responsive breakpoints
- Loading states and skeleton loaders

### 4. Fix UI Alignments and Overall Design
**Priority: Medium**
- Consistent spacing across all pages
- Better mobile responsiveness
- Improved form layouts
- Better visual hierarchy
- Consistent typography
- Better error message display
- Loading states and transitions

---

## 📊 Progress Summary

**Backend**: ✅ 100% Complete (6/6 tasks)
**Frontend**: ⏳ 35% Complete (3/8 tasks)
**Overall**: ⏳ 64% Complete (9/14 tasks)

---

## 🚀 Current State

The application is now running at **http://localhost:8081** with:
- Material-UI theme and components
- Modern navigation layout
- Unified SSH Connections page
- Database persistence in `/data` volume
- Environment variable configuration

**Bundle size**: 726 kB (gzipped: 211 kB)

---

## 📝 Next Steps

1. **Test the unified SSH Connections page** - Verify all functionality works
2. **Add SSH connection dropdown to Repository form** - Quick win for better UX
3. **Modernize remaining pages** - Dashboard, Config, Backup, etc.
4. **Polish UI design** - Spacing, responsiveness, loading states
5. **Consider Configuration-First workflow** - If time permits

---

## 🐳 Docker Commands

### Current Setup
```bash
# Run with default volume
docker-compose up -d

# Access at
http://localhost:8081

# View logs
docker-compose logs -f borgmatic-ui
```

### Docker Run Command
```bash
docker run -d \
  --name borgmatic-web-ui \
  -p 8081:8081 \
  -v borgmatic_data:/data \
  -v /path/to/backups:/backups \
  -e SECRET_KEY=$(openssl rand -base64 32) \
  ainullcode/borgmatic-ui:latest
```

### Portainer Stack
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

**Note:** This document tracks remaining optimization tasks. Delete after all tasks are completed.
