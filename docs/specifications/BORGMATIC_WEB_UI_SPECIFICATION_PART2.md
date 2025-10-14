# Borgmatic Web UI - Technical Specification (Part 2)

## 4. User Interface Design

### 4.1 Design Principles

#### 4.1.1 Responsive Design
- **Mobile-First**: Optimized for touch interfaces
- **Progressive Enhancement**: Core functionality works without JavaScript
- **Accessibility**: WCAG 2.1 AA compliance
- **Performance**: Minimal bundle size and fast loading

#### 4.1.2 Visual Design
- **Color Scheme**: Dark mode with high contrast
- **Typography**: System fonts for performance
- **Icons**: SVG icons for scalability
- **Layout**: Grid-based responsive layout

### 4.2 Component Structure

```
src/
├── components/
│   ├── common/
│   │   ├── Header.tsx
│   │   ├── Sidebar.tsx
│   │   ├── Loading.tsx
│   │   └── ErrorBoundary.tsx
│   ├── dashboard/
│   │   ├── StatusCard.tsx
│   │   ├── MetricsChart.tsx
│   │   └── QuickActions.tsx
│   ├── config/
│   │   ├── YamlEditor.tsx
│   │   ├── ConfigValidator.tsx
│   │   └── TemplateSelector.tsx
│   ├── backup/
│   │   ├── BackupControl.tsx
│   │   ├── ProgressMonitor.tsx
│   │   └── JobQueue.tsx
│   ├── archives/
│   │   ├── ArchiveList.tsx
│   │   ├── FileBrowser.tsx
│   │   └── ArchiveDetails.tsx
│   ├── restore/
│   │   ├── RestoreWizard.tsx
│   │   ├── PathSelector.tsx
│   │   └── RestoreProgress.tsx
│   ├── schedule/
│   │   ├── CronEditor.tsx
│   │   ├── JobList.tsx
│   │   └── ExecutionHistory.tsx
│   ├── logs/
│   │   ├── LogViewer.tsx
│   │   ├── LogFilter.tsx
│   │   └── LogSearch.tsx
│   ├── settings/
│   │   ├── SystemSettings.tsx
│   │   ├── AuthSettings.tsx
│   │   └── NotificationSettings.tsx
│   └── health/
│       ├── SystemHealth.tsx
│       ├── BackupHealth.tsx
│       └── AlertManager.tsx
```

### 4.3 State Management

#### 4.3.1 Context Structure
```typescript
interface AppState {
  auth: AuthState;
  dashboard: DashboardState;
  backup: BackupState;
  config: ConfigState;
  archives: ArchivesState;
  restore: RestoreState;
  schedule: ScheduleState;
  logs: LogsState;
  settings: SettingsState;
  health: HealthState;
}
```

#### 4.3.2 Real-time Updates
- **Server-Sent Events**: For live log streaming and progress updates
- **WebSocket Fallback**: For environments requiring WebSocket support
- **Polling**: Fallback for environments with limited real-time capabilities

## 5. Backend Architecture

### 5.1 FastAPI Application Structure

```
app/
├── main.py                 # Application entry point
├── config.py              # Configuration management
├── database/
│   ├── models.py          # SQLAlchemy models
│   ├── database.py        # Database connection
│   └── migrations/        # Database migrations
├── api/
│   ├── auth.py            # Authentication endpoints
│   ├── dashboard.py       # Dashboard endpoints
│   ├── config.py          # Configuration endpoints
│   ├── backup.py          # Backup endpoints
│   ├── archives.py        # Archive endpoints
│   ├── restore.py         # Restore endpoints
│   ├── schedule.py        # Schedule endpoints
│   ├── logs.py            # Log endpoints
│   ├── settings.py        # Settings endpoints
│   └── health.py          # Health endpoints
├── core/
│   ├── borgmatic.py       # Borgmatic CLI interface
│   ├── scheduler.py        # Cron job management
│   ├── notifications.py    # Notification system
│   └── security.py        # Security utilities
├── models/
│   ├── auth.py            # Authentication models
│   ├── backup.py          # Backup models
│   ├── config.py          # Configuration models
│   └── system.py          # System models
└── utils/
    ├── logger.py          # Logging utilities
    ├── validators.py      # Validation utilities
    └── helpers.py         # Helper functions
```

### 5.2 Borgmatic Integration

#### 5.2.1 CLI Interface
```python
class BorgmaticInterface:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.borgmatic_cmd = "borgmatic"
    
    async def run_backup(self, repository: str = None) -> dict:
        """Execute backup operation"""
        cmd = [self.borgmatic_cmd, "create"]
        if repository:
            cmd.extend(["--repository", repository])
        
        return await self._execute_command(cmd)
    
    async def list_archives(self, repository: str) -> dict:
        """List archives in repository"""
        cmd = [self.borgmatic_cmd, "list", "--repository", repository]
        return await self._execute_command(cmd)
    
    async def _execute_command(self, cmd: List[str]) -> dict:
        """Execute command with real-time output capture"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        return {
            "return_code": process.returncode,
            "stdout": stdout.decode(),
            "stderr": stderr.decode()
        }
```

### 5.3 Database Schema

#### 5.3.1 Core Tables
```sql
-- Users table for authentication
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Backup jobs table
CREATE TABLE backup_jobs (
    id INTEGER PRIMARY KEY,
    repository VARCHAR(255) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    error_message TEXT,
    logs TEXT
);

-- Configuration backups
CREATE TABLE config_backups (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Scheduled jobs
CREATE TABLE scheduled_jobs (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    cron_expression VARCHAR(100) NOT NULL,
    repository VARCHAR(255),
    enabled BOOLEAN DEFAULT TRUE,
    last_run TIMESTAMP,
    next_run TIMESTAMP
);

-- System logs
CREATE TABLE system_logs (
    id INTEGER PRIMARY KEY,
    level VARCHAR(10) NOT NULL,
    message TEXT NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    source VARCHAR(50)
);
```

## 6. API Design

### 6.1 Authentication API

#### 6.1.1 Endpoints
```python
# Authentication
POST /api/auth/login
POST /api/auth/logout
POST /api/auth/refresh
GET /api/auth/me

# User management
GET /api/auth/users
POST /api/auth/users
PUT /api/auth/users/{user_id}
DELETE /api/auth/users/{user_id}
```

#### 6.1.2 Security Implementation
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username
```

### 6.2 Dashboard API

#### 6.2.1 Status Endpoint
```python
@router.get("/api/dashboard/status")
async def get_dashboard_status(current_user: str = Depends(get_current_user)):
    """Get comprehensive dashboard status"""
    try:
        # Get backup status
        backup_status = await borgmatic.get_backup_status()
        
        # Get system metrics
        system_metrics = await get_system_metrics()
        
        # Get scheduled jobs
        scheduled_jobs = await get_scheduled_jobs()
        
        return {
            "backup_status": backup_status,
            "system_metrics": system_metrics,
            "scheduled_jobs": scheduled_jobs,
            "last_updated": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting dashboard status: {e}")
        raise HTTPException(status_code=500, detail="Failed to get dashboard status")
```

### 6.3 Real-time Updates

#### 6.3.1 Server-Sent Events
```python
@router.get("/api/events/backup-progress/{job_id}")
async def backup_progress_events(job_id: str):
    """Stream backup progress updates"""
    async def event_generator():
        while True:
            # Check if job is still running
            job_status = await get_job_status(job_id)
            
            if job_status["status"] in ["completed", "failed", "cancelled"]:
                yield f"data: {json.dumps(job_status)}\n\n"
                break
            
            yield f"data: {json.dumps(job_status)}\n\n"
            await asyncio.sleep(1)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Content-Type": "text/event-stream"
        }
    )
``` 