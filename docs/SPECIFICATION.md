---
layout: default
title: Technical Specification
nav_order: 8
description: "Architecture and technical details"
---

# Borg Web UI - Technical Specification

## 1. Executive Summary

This document outlines the technical specification for a lightweight web-based user interface for Borg, designed to run efficiently on resource-constrained devices like Raspberry Pi or Odroid. The solution provides comprehensive visualization and control over backup operations without requiring command-line interaction.

### 1.1 Key Objectives
- **Resource Efficiency**: Minimal memory and CPU footprint suitable for ARM-based devices
- **Comprehensive Functionality**: Full backup management capabilities through web interface
- **Easy Deployment**: Docker-based containerization for simplified deployment
- **Security**: Authentication and secure remote access capabilities
- **User Experience**: Intuitive interface for non-technical users

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Browser  │    │   Borg     │    │   System        │
│   (Frontend)   │◄──►│   Web UI        │◄──►│   (Backend)     │
│                │    │   (Backend)      │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Borg     │
                       │   CLI Interface │
                       └─────────────────┘
```

### 2.2 Technology Stack

#### Backend
- **Framework**: FastAPI (Python 3.10+)
- **Process Management**: Subprocess for Borg CLI interaction
- **Authentication**: JWT-based with bcrypt password hashing
- **Database**: SQLite for lightweight storage
- **Logging**: Structured logging with rotation

#### Frontend
- **Framework**: React 18 with TypeScript
- **Styling**: Tailwind CSS for lightweight, responsive design
- **State Management**: React Context + useReducer
- **HTTP Client**: Axios for API communication
- **Real-time Updates**: Server-Sent Events (SSE)

#### Containerization
- **Runtime**: Docker with multi-stage builds
- **Base Image**: Python 3.10-slim for minimal footprint
- **Web Server**: Gunicorn with Uvicorn workers

## 3. Core Components Specification

### 3.1 Dashboard Component

#### 3.1.1 Features
- **Backup Status Overview**: Real-time status of all configured repositories
- **Storage Metrics**: Disk usage, backup size, compression ratios
- **Scheduling Display**: Next scheduled backup times
- **Quick Actions**: Manual backup, restore, and configuration buttons
- **System Health**: CPU, memory, and disk usage monitoring

#### 3.1.2 Data Flow
```
Dashboard → API → Borg CLI → System → Real-time Updates
```

#### 3.1.3 API Endpoints
```python
GET /api/dashboard/status
GET /api/dashboard/metrics
GET /api/dashboard/schedule
GET /api/dashboard/health
```

### 3.2 Configuration Management

#### 3.2.1 Configuration Viewer
- **YAML Editor**: Syntax-highlighted editor with validation
- **Configuration Templates**: Pre-built templates for common scenarios
- **Validation**: Real-time YAML syntax and Borg configuration validation
- **Backup/Restore**: Configuration backup and restore capabilities

#### 3.2.2 API Endpoints
```python
GET /api/config/current
PUT /api/config/update
POST /api/config/validate
GET /api/config/templates
POST /api/config/backup
POST /api/config/restore
```

### 3.3 Backup Control

#### 3.3.1 Manual Backup Operations
- **Repository Selection**: Choose specific repositories for backup
- **Progress Monitoring**: Real-time progress with detailed logs
- **Cancel Operations**: Ability to cancel running backups
- **Prune Integration**: Automatic pruning after backup completion

#### 3.3.2 API Endpoints
```python
POST /api/backup/start
GET /api/backup/status/{job_id}
DELETE /api/backup/cancel/{job_id}
GET /api/backup/logs/{job_id}
```

### 3.4 Archive Browser

#### 3.4.1 Archive Management
- **Repository Listing**: Browse all configured repositories
- **Archive Details**: View archive metadata, size, and contents
- **File Browser**: Navigate archive contents with search
- **Archive Operations**: Delete, rename, and tag archives

#### 3.4.2 API Endpoints
```python
GET /api/archives/list
GET /api/archives/{archive_id}/info
GET /api/archives/{archive_id}/contents
DELETE /api/archives/{archive_id}
POST /api/archives/{archive_id}/rename
```

### 3.5 Restore Functionality

#### 3.5.1 Restore Operations
- **Archive Selection**: Choose source archive for restore
- **Path Selection**: Select files/directories to restore
- **Destination Configuration**: Choose restore location
- **Progress Monitoring**: Real-time restore progress
- **Dry Run**: Preview restore operations

#### 3.5.2 API Endpoints
```python
POST /api/restore/preview
POST /api/restore/start
GET /api/restore/status/{job_id}
DELETE /api/restore/cancel/{job_id}
GET /api/restore/logs/{job_id}
```

### 3.6 Scheduling Management

#### 3.6.1 Cron Integration
- **Schedule Editor**: Visual cron expression builder
- **Job Management**: View, edit, and delete scheduled jobs
- **Execution History**: Track scheduled job executions
- **Manual Trigger**: Execute scheduled jobs manually

#### 3.6.2 API Endpoints
```python
GET /api/schedule/jobs
POST /api/schedule/job
PUT /api/schedule/job/{job_id}
DELETE /api/schedule/job/{job_id}
POST /api/schedule/job/{job_id}/trigger
GET /api/schedule/history
```

### 3.7 Log Management

#### 3.7.1 Log Viewer
- **Real-time Logs**: Live log streaming with filtering
- **Log Levels**: Filter by error, warning, info, debug
- **Search Functionality**: Full-text search across logs
- **Export Capabilities**: Download logs in various formats

#### 3.7.2 API Endpoints
```python
GET /api/logs/stream
GET /api/logs/search
GET /api/logs/download
GET /api/logs/levels
```

### 3.8 System Settings

#### 3.8.1 Settings Management
- **Authentication**: User management and password changes
- **Network Configuration**: Port settings and access controls
- **Backup Settings**: Default backup parameters
- **Notification Settings**: Email and webhook configurations

#### 3.8.2 API Endpoints
```python
GET /api/settings/system
PUT /api/settings/system
GET /api/settings/auth
PUT /api/settings/auth
GET /api/settings/notifications
PUT /api/settings/notifications
```

### 3.9 Health Monitoring

#### 3.9.1 System Health
- **Resource Monitoring**: CPU, memory, disk usage
- **Backup Health**: Repository status and integrity
- **Network Monitoring**: Connectivity and performance
- **Alert System**: Configurable alerts for issues

#### 3.9.2 API Endpoints
```python
GET /api/health/system
GET /api/health/backups
GET /api/health/network
POST /api/health/alerts
```

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
│   ├── borg.py       # Borg CLI interface
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

### 5.2 Borg Integration

#### 5.2.1 CLI Interface
```python
class BorgInterface:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.borg_cmd = "borg"
    
    async def run_backup(self, repository: str = None) -> dict:
        """Execute backup operation"""
        cmd = [self.borg_cmd, "create"]
        if repository:
            cmd.extend(["--repository", repository])
        
        return await self._execute_command(cmd)
    
    async def list_archives(self, repository: str) -> dict:
        """List archives in repository"""
        cmd = [self.borg_cmd, "list", "--repository", repository]
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
        backup_status = await borg.get_backup_status()
        
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

## 7. Docker Implementation

### 7.1 Multi-stage Dockerfile

```dockerfile
# Build stage for frontend
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --only=production
COPY frontend/ .
RUN npm run build

# Build stage for backend
FROM python:3.10-slim AS backend-builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.10-slim AS production
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    cron \
    borgbackup \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies
COPY --from=backend-builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY --from=frontend-builder /app/frontend/build ./app/static

# Create non-root user
RUN useradd -m -u 1000 borg && \
    chown -R borg:borg /app

# Switch to non-root user
USER borg

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/health/system || exit 1

# Start application
CMD ["gunicorn", "app.main:app", "--bind", "0.0.0.0:8000", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker"]
```

### 7.2 Docker Compose Configuration

```yaml
version: '3.8'

services:
  borg-ui:
    build: .
    container_name: borg-web-ui
    ports:
      - "8080:8000"
    volumes:
      - ./config:/app/config:ro
      - ./backups:/backups:ro
      - ./logs:/app/logs
      - /etc/cron.d:/etc/cron.d:ro
    environment:
      - BORG_CONFIG_PATH=/app/config
      - BORG_BACKUP_PATH=/backups
      - LOG_LEVEL=INFO
      - SECRET_KEY=${SECRET_KEY}
    restart: unless-stopped
    networks:
      - borg-network

  # Optional: PostgreSQL for production
  postgres:
    image: postgres:13-alpine
    container_name: borg-db
    environment:
      - POSTGRES_DB=borg
      - POSTGRES_USER=borg
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    networks:
      - borg-network

networks:
  borg-network:
    driver: bridge

volumes:
  postgres_data:
```

### 7.3 Environment Configuration

```bash
# .env file
SECRET_KEY=your-secret-key-here
DB_PASSWORD=your-db-password
BORG_CONFIG_PATH=/app/config
BORG_BACKUP_PATH=/backups
LOG_LEVEL=INFO
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ORIGINS=http://localhost:3000,http://localhost:8080
```

## 8. Deployment Considerations

### 8.1 Resource Requirements

#### 8.1.1 Minimum Requirements
- **CPU**: 1 core ARM Cortex-A53 or equivalent
- **RAM**: 512MB (1GB recommended)
- **Storage**: 2GB for application + backup storage
- **Network**: Ethernet or WiFi connection

#### 8.1.2 Recommended Requirements
- **CPU**: 2+ cores ARM Cortex-A72 or equivalent
- **RAM**: 2GB
- **Storage**: 8GB+ for application and backup storage
- **Network**: Gigabit Ethernet

### 8.2 Security Considerations

#### 8.2.1 Authentication
- **JWT Tokens**: Secure token-based authentication
- **Password Hashing**: bcrypt with salt rounds
- **Session Management**: Configurable session timeouts
- **Rate Limiting**: API rate limiting to prevent abuse

#### 8.2.2 Network Security
- **HTTPS**: TLS/SSL encryption for all communications
- **CORS**: Configurable Cross-Origin Resource Sharing
- **Firewall**: Port restrictions and access controls
- **VPN**: Optional VPN integration for remote access

#### 8.2.3 Data Security
- **Encryption**: Backup data encryption at rest
- **Access Control**: Role-based access control
- **Audit Logging**: Comprehensive audit trail
- **Backup Security**: Encrypted configuration backups

### 8.3 Monitoring and Logging

#### 8.3.1 Application Monitoring
```python
# Health check endpoints
@router.get("/api/health/system")
async def system_health():
    return {
        "cpu_usage": get_cpu_usage(),
        "memory_usage": get_memory_usage(),
        "disk_usage": get_disk_usage(),
        "uptime": get_system_uptime()
    }

@router.get("/api/health/backups")
async def backup_health():
    return {
        "repositories": await get_repository_status(),
        "last_backup": await get_last_backup_time(),
        "backup_errors": await get_recent_backup_errors()
    }
```

#### 8.3.2 Logging Configuration
```python
# Structured logging setup
import structlog

structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)
```

### 8.4 Backup and Recovery

#### 8.4.1 Configuration Backup
```python
async def backup_configuration():
    """Backup current configuration"""
    config_path = os.getenv("BORG_CONFIG_PATH")
    backup_dir = "/app/backups/config"
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{backup_dir}/config_backup_{timestamp}.tar.gz"
    
    with tarfile.open(backup_file, "w:gz") as tar:
        tar.add(config_path, arcname="config")
    
    return backup_file
```

#### 8.4.2 Disaster Recovery
- **Configuration Backup**: Automatic backup of all configurations
- **Database Backup**: Regular SQLite database backups
- **Application Backup**: Docker image and configuration backups
- **Recovery Procedures**: Documented recovery procedures

## 9. Performance Optimization

### 9.1 Frontend Optimization

#### 9.1.1 Bundle Optimization
```javascript
// webpack.config.js
module.exports = {
  optimization: {
    splitChunks: {
      chunks: 'all',
      cacheGroups: {
        vendor: {
          test: /[\\/]node_modules[\\/]/,
          name: 'vendors',
          chunks: 'all',
        },
      },
    },
  },
  performance: {
    hints: 'warning',
    maxEntrypointSize: 512000,
    maxAssetSize: 512000,
  },
};
```

#### 9.1.2 Lazy Loading
```typescript
// Lazy load components for better performance
const Dashboard = lazy(() => import('./components/dashboard/Dashboard'));
const ConfigEditor = lazy(() => import('./components/config/ConfigEditor'));
const ArchiveBrowser = lazy(() => import('./components/archives/ArchiveBrowser'));
```

### 9.2 Backend Optimization

#### 9.2.1 Caching Strategy
```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend
from fastapi_cache.decorator import cache

@cache(expire=300)  # Cache for 5 minutes
async def get_dashboard_metrics():
    """Get cached dashboard metrics"""
    return await calculate_metrics()

@cache(expire=60)  # Cache for 1 minute
async def get_repository_status():
    """Get cached repository status"""
    return await borg.get_repository_status()
```

#### 9.2.2 Database Optimization
```python
# Database connection pooling
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    "sqlite:///borg.db",
    poolclass=QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True
)
```

## 10. Testing Strategy

### 10.1 Unit Testing

#### 10.1.1 Backend Tests
```python
# tests/test_borg.py
import pytest
from app.core.borg import BorgInterface

@pytest.fixture
def borg_interface():
    return BorgInterface("/tmp/test_config")

@pytest.mark.asyncio
async def test_run_backup(borg_interface):
    result = await borg_interface.run_backup("test_repo")
    assert result["return_code"] == 0
    assert "backup" in result["stdout"].lower()
```

#### 10.1.2 Frontend Tests
```typescript
// tests/components/Dashboard.test.tsx
import { render, screen } from '@testing-library/react';
import Dashboard from '../Dashboard';

test('renders dashboard with status cards', () => {
  render(<Dashboard />);
  expect(screen.getByText('Backup Status')).toBeInTheDocument();
  expect(screen.getByText('System Health')).toBeInTheDocument();
});
```

### 10.2 Integration Testing

#### 10.2.1 API Testing
```python
# tests/test_api.py
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_dashboard_status():
    response = client.get("/api/dashboard/status")
    assert response.status_code == 200
    assert "backup_status" in response.json()
```

### 10.3 End-to-End Testing

#### 10.3.1 Docker Testing
```yaml
# docker-compose.test.yml
version: '3.8'

services:
  test-app:
    build: .
    environment:
      - TESTING=true
      - DATABASE_URL=sqlite:///test.db
    volumes:
      - ./tests:/app/tests
    command: ["pytest", "/app/tests"]
```

## 11. Documentation

### 11.1 User Documentation

#### 11.1.1 Getting Started Guide
- **Installation**: Step-by-step Docker installation
- **Configuration**: Initial setup and configuration
- **First Backup**: Creating and running first backup
- **Troubleshooting**: Common issues and solutions

#### 11.1.2 User Manual
- **Dashboard**: Understanding the dashboard interface
- **Backup Management**: Creating and managing backups
- **Restore Operations**: Restoring data from archives
- **Scheduling**: Setting up automated backups
- **Monitoring**: Understanding system health and logs

### 11.2 Developer Documentation

#### 11.2.1 API Documentation
- **OpenAPI/Swagger**: Auto-generated API documentation
- **Endpoint Reference**: Detailed endpoint documentation
- **Authentication**: Authentication and authorization guide
- **Error Codes**: Comprehensive error code reference

#### 11.2.2 Development Guide
- **Setup**: Development environment setup
- **Architecture**: System architecture overview
- **Contributing**: Contribution guidelines
- **Testing**: Testing procedures and guidelines

## 12. Conclusion

This technical specification provides a comprehensive framework for developing a lightweight, feature-rich web UI for Borg. The solution addresses all core requirements while maintaining focus on resource efficiency and ease of deployment.

### 12.1 Key Success Factors

1. **Resource Efficiency**: Minimal footprint suitable for ARM devices
2. **Comprehensive Functionality**: Full backup management capabilities
3. **Security**: Robust authentication and data protection
4. **User Experience**: Intuitive interface for non-technical users
5. **Deployment Simplicity**: Docker-based deployment for easy installation
6. **Maintainability**: Well-structured codebase with comprehensive testing
7. **Scalability**: Architecture supports future enhancements

### 12.2 Next Steps

1. **Implementation**: Begin with core dashboard and backup functionality
2. **Testing**: Comprehensive testing across different ARM devices
3. **Documentation**: Complete user and developer documentation
4. **Deployment**: Create deployment packages and installation scripts
5. **Community**: Open source release and community engagement

This specification provides a solid foundation for building a production-ready Borg web UI that meets all requirements while maintaining the lightweight, efficient design necessary for resource-constrained devices. 