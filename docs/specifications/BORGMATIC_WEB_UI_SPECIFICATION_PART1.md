# Borgmatic Web UI - Technical Specification (Part 1)

## 1. Executive Summary

This document outlines the technical specification for a lightweight web-based user interface for Borgmatic, designed to run efficiently on resource-constrained devices like Raspberry Pi or Odroid. The solution provides comprehensive visualization and control over backup operations without requiring command-line interaction.

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
│   Web Browser  │    │   Borgmatic     │    │   System        │
│   (Frontend)   │◄──►│   Web UI        │◄──►│   (Backend)     │
│                │    │   (Backend)      │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                              │
                              ▼
                       ┌─────────────────┐
                       │   Borgmatic     │
                       │   CLI Interface │
                       └─────────────────┘
```

### 2.2 Technology Stack

#### Backend
- **Framework**: FastAPI (Python 3.9+)
- **Process Management**: Subprocess for Borgmatic CLI interaction
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
- **Base Image**: Python 3.9-slim for minimal footprint
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
Dashboard → API → Borgmatic CLI → System → Real-time Updates
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
- **Validation**: Real-time YAML syntax and Borgmatic configuration validation
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