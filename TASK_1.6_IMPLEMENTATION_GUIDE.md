# Task 1.6 Implementation Guide: Backup Execution with Real-time Logging

## Overview
This guide provides complete implementation details for Task 1.6: Backup Execution with Real-time Logging. This task requires modifying both backend and frontend to support real-time log streaming during backup operations.

## Current Status
- **Phase 1 Progress**: 5/6 tasks completed (83%)
- **Completed**: Tasks 1.1, 1.2, 1.3, 1.4, 1.5
- **Current Task**: Task 1.6 (TO DO)

## Requirements (from IMPLEMENTATION_TASKS.md)

### Backend Requirements:
1. Execute `borgmatic --verbosity 1 --files` to show file-level details
2. Stream output line-by-line to a log file in real-time
3. Create endpoint to fetch new log entries incrementally
4. Run backups asynchronously (non-blocking)
5. Return exact error messages without interpretation
6. Track backup status: running, completed, failed

### Frontend Requirements:
1. Terminal-style log viewer with dark background
2. Poll log endpoint every 2-3 seconds while backup is running
3. Auto-scroll to latest log entry
4. "Copy Logs" button functionality
5. Display timestamps for each log entry
6. Show errors exactly as returned (no friendly messages)

---

## Part 1: Backend Changes

### Step 1: Update BackupJob Model

**File**: `app/database/models.py`

Add these fields to the `BackupJob` class (around line 100):

```python
class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id = Column(Integer, primary_key=True, index=True)
    repository = Column(String)  # Repository path/name
    status = Column(String, default="pending")  # pending, running, completed, failed
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    progress = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)  # Full logs (stored after completion)
    log_file_path = Column(String, nullable=True)  # Path to streaming log file
    created_at = Column(DateTime, default=datetime.utcnow)
```

### Step 2: Create Backup Service with Real-time Logging

**File**: `app/services/backup_service.py` (NEW FILE)

```python
import asyncio
import os
from datetime import datetime
from pathlib import Path
import structlog
from sqlalchemy.orm import Session
from app.database.models import BackupJob
from app.config import settings

logger = structlog.get_logger()

class BackupService:
    """Service for executing backups with real-time log streaming"""

    def __init__(self):
        self.log_dir = Path("/data/logs")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    async def execute_backup(self, job_id: int, repository: str, config_file: str, db: Session):
        """Execute backup with real-time log streaming"""

        # Get job
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            logger.error("Job not found", job_id=job_id)
            return

        # Create log file
        log_file = self.log_dir / f"backup_{job_id}.log"
        job.log_file_path = str(log_file)
        job.status = "running"
        job.started_at = datetime.utcnow()
        db.commit()

        # Build command
        cmd = ["borgmatic", "create", "--verbosity", "1", "--files"]
        if repository:
            cmd.extend(["--repository", repository])
        if config_file:
            cmd.extend(["--config", config_file])
        elif settings.borgmatic_config_path:
            cmd.extend(["--config", settings.borgmatic_config_path])

        try:
            # Execute command and stream to log file
            with open(log_file, 'w') as f:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
                )

                # Stream output line by line
                async for line in process.stdout:
                    line_str = line.decode('utf-8', errors='replace')
                    timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
                    log_line = f"[{timestamp}] {line_str}"
                    f.write(log_line)
                    f.flush()  # Force write to disk immediately

                # Wait for process to complete
                await process.wait()

                # Update job status
                if process.returncode == 0:
                    job.status = "completed"
                    job.progress = 100
                else:
                    job.status = "failed"
                    job.error_message = f"Backup failed with exit code {process.returncode}"

                job.completed_at = datetime.utcnow()

                # Read full logs and store in database
                with open(log_file, 'r') as log_read:
                    job.logs = log_read.read()

                db.commit()
                logger.info("Backup completed", job_id=job_id, status=job.status)

        except Exception as e:
            logger.error("Backup execution failed", job_id=job_id, error=str(e))
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            db.commit()

# Global instance
backup_service = BackupService()
```

### Step 3: Update Backup API Endpoints

**File**: `app/api/backup.py`

Replace the `start_backup` endpoint (around line 26):

```python
import asyncio
from app.services.backup_service import backup_service

@router.post("/start", response_model=BackupResponse)
async def start_backup(
    backup_request: BackupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Start a manual backup operation"""
    try:
        # Create backup job record
        backup_job = BackupJob(
            repository=backup_request.repository or "default",
            status="pending"
        )
        db.add(backup_job)
        db.commit()
        db.refresh(backup_job)

        # Execute backup asynchronously (non-blocking)
        asyncio.create_task(
            backup_service.execute_backup(
                backup_job.id,
                backup_request.repository,
                backup_request.config_file,
                db
            )
        )

        logger.info("Backup job created", job_id=backup_job.id, user=current_user.username)

        return BackupResponse(
            job_id=backup_job.id,
            status="pending",
            message="Backup job started"
        )
    except Exception as e:
        logger.error("Failed to start backup", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start backup: {str(e)}"
        )
```

Add new endpoint for streaming logs (add after the `get_backup_logs` endpoint, around line 200):

```python
@router.get("/logs/{job_id}/stream")
async def stream_backup_logs(
    job_id: int,
    offset: int = 0,  # Line number to start from
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get incremental backup logs (for real-time streaming)"""
    try:
        job = db.query(BackupJob).filter(BackupJob.id == job_id).first()
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Backup job not found"
            )

        # If no log file yet, return empty
        if not job.log_file_path or not os.path.exists(job.log_file_path):
            return {
                "job_id": job.id,
                "status": job.status,
                "lines": [],
                "total_lines": 0,
                "has_more": job.status == "running"
            }

        # Read log file from offset
        lines = []
        with open(job.log_file_path, 'r') as f:
            all_lines = f.readlines()
            total_lines = len(all_lines)

            # Get lines from offset onwards
            if offset < total_lines:
                lines = [{"line_number": offset + i + 1, "content": line.rstrip('\n')}
                         for i, line in enumerate(all_lines[offset:])]

        return {
            "job_id": job.id,
            "status": job.status,
            "lines": lines,
            "total_lines": total_lines,
            "has_more": job.status == "running"
        }

    except Exception as e:
        logger.error("Failed to stream backup logs", error=str(e), job_id=job_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch logs: {str(e)}"
        )
```

---

## Part 2: Frontend Changes

### Step 4: Update API Service

**File**: `frontend/src/services/api.ts`

Add to the `backupAPI` object (around line 82):

```typescript
export const backupAPI = {
  startBackup: (repository?: string) => api.post('/backup/start', { repository }),
  getStatus: (jobId: string) => api.get(`/backup/status/${jobId}`),
  getAllJobs: () => api.get('/backup/jobs'),
  cancelJob: (jobId: string) => api.post(`/backup/cancel/${jobId}`),
  getLogs: (jobId: string) => api.get(`/backup/logs/${jobId}`),
  // NEW: Stream logs incrementally
  streamLogs: (jobId: string, offset: number) =>
    api.get(`/backup/logs/${jobId}/stream`, { params: { offset } }),
}
```

### Step 5: Create Terminal Log Viewer Component

**File**: `frontend/src/components/TerminalLogViewer.tsx` (NEW FILE)

```typescript
import React, { useEffect, useRef, useState } from 'react'
import { Box, Button, Typography, Paper, IconButton } from '@mui/material'
import { ContentCopy, Download } from '@mui/icons-material'
import { toast } from 'react-hot-toast'

interface LogLine {
  line_number: number
  content: string
}

interface TerminalLogViewerProps {
  jobId: string
  status: string
  onFetchLogs: (offset: number) => Promise<{
    lines: LogLine[]
    total_lines: number
    has_more: boolean
  }>
}

export const TerminalLogViewer: React.FC<TerminalLogViewerProps> = ({
  jobId,
  status,
  onFetchLogs
}) => {
  const [logs, setLogs] = useState<LogLine[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const logContainerRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  // Fetch logs on mount and poll while running
  useEffect(() => {
    const fetchLogs = async () => {
      if (isLoading) return

      setIsLoading(true)
      try {
        const offset = logs.length
        const result = await onFetchLogs(offset)

        if (result.lines.length > 0) {
          setLogs(prev => [...prev, ...result.lines])
        }
      } catch (error) {
        console.error('Failed to fetch logs:', error)
      } finally {
        setIsLoading(false)
      }
    }

    // Initial fetch
    fetchLogs()

    // Poll every 2 seconds while running
    if (status === 'running') {
      const interval = setInterval(fetchLogs, 2000)
      return () => clearInterval(interval)
    }
  }, [status, logs.length])

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  // Handle scroll - disable auto-scroll if user scrolls up
  const handleScroll = () => {
    if (logContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = logContainerRef.current
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
      setAutoScroll(isAtBottom)
    }
  }

  // Copy logs to clipboard
  const handleCopyLogs = () => {
    const logText = logs.map(log => log.content).join('\n')
    navigator.clipboard.writeText(logText)
    toast.success('Logs copied to clipboard')
  }

  // Download logs as file
  const handleDownloadLogs = () => {
    const logText = logs.map(log => log.content).join('\n')
    const blob = new Blob([logText], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `backup_${jobId}_logs.txt`
    a.click()
    URL.revokeObjectURL(url)
    toast.success('Logs downloaded')
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight={600}>
          Backup Logs
        </Typography>
        <Box sx={{ display: 'flex', gap: 1 }}>
          <Button
            size="small"
            startIcon={<ContentCopy size={16} />}
            onClick={handleCopyLogs}
            disabled={logs.length === 0}
          >
            Copy Logs
          </Button>
          <Button
            size="small"
            startIcon={<Download size={16} />}
            onClick={handleDownloadLogs}
            disabled={logs.length === 0}
          >
            Download
          </Button>
        </Box>
      </Box>

      {/* Terminal */}
      <Paper
        ref={logContainerRef}
        onScroll={handleScroll}
        sx={{
          bgcolor: '#1e1e1e',
          color: '#d4d4d4',
          fontFamily: 'Consolas, Monaco, "Courier New", monospace',
          fontSize: '0.875rem',
          p: 2,
          height: 500,
          overflowY: 'auto',
          overflowX: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-all',
          '&::-webkit-scrollbar': {
            width: '8px',
          },
          '&::-webkit-scrollbar-track': {
            background: '#2d2d2d',
          },
          '&::-webkit-scrollbar-thumb': {
            background: '#555',
            borderRadius: '4px',
          },
          '&::-webkit-scrollbar-thumb:hover': {
            background: '#666',
          },
        }}
      >
        {logs.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {status === 'running' ? 'Waiting for logs...' : 'No logs available'}
          </Typography>
        ) : (
          logs.map((log) => (
            <Box key={log.line_number} sx={{ mb: 0.5 }}>
              <Typography
                component="span"
                sx={{
                  color: '#858585',
                  fontSize: '0.8rem',
                  mr: 2,
                  userSelect: 'none'
                }}
              >
                {log.line_number}
              </Typography>
              <Typography component="span" sx={{ color: '#d4d4d4' }}>
                {log.content}
              </Typography>
            </Box>
          ))
        )}

        {/* Running indicator */}
        {status === 'running' && (
          <Box sx={{ display: 'flex', alignItems: 'center', mt: 2 }}>
            <Box
              sx={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                bgcolor: '#4ade80',
                mr: 1,
                animation: 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                '@keyframes pulse': {
                  '0%, 100%': { opacity: 1 },
                  '50%': { opacity: 0.5 },
                },
              }}
            />
            <Typography sx={{ color: '#4ade80', fontSize: '0.875rem' }}>
              Backup in progress...
            </Typography>
          </Box>
        )}
      </Paper>

      {/* Auto-scroll indicator */}
      {!autoScroll && status === 'running' && (
        <Box sx={{ mt: 1, textAlign: 'center' }}>
          <Button
            size="small"
            onClick={() => {
              setAutoScroll(true)
              if (logContainerRef.current) {
                logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight
              }
            }}
          >
            New logs available - Click to scroll to bottom
          </Button>
        </Box>
      )}
    </Box>
  )
}

export default TerminalLogViewer
```

### Step 6: Update Backup Page to Use Terminal Viewer

**File**: `frontend/src/pages/Backup.tsx`

Add import at the top:
```typescript
import TerminalLogViewer from '../components/TerminalLogViewer'
```

Add state for viewing job logs:
```typescript
const [viewingJobLogs, setViewingJobLogs] = useState<string | null>(null)
```

Add function to fetch logs:
```typescript
const fetchJobLogs = async (jobId: string, offset: number) => {
  const response = await backupAPI.streamLogs(jobId, offset)
  return response.data
}
```

Add this after the "Recent Jobs" Card (around line 455):

```typescript
{/* Log Viewer Dialog */}
{viewingJobLogs && (
  <Dialog
    open={!!viewingJobLogs}
    onClose={() => setViewingJobLogs(null)}
    maxWidth="lg"
    fullWidth
  >
    <DialogTitle>
      Backup Job {viewingJobLogs} Logs
    </DialogTitle>
    <DialogContent>
      <TerminalLogViewer
        jobId={viewingJobLogs}
        status={recentJobs.find((j: BackupJob) => j.id === viewingJobLogs)?.status || 'unknown'}
        onFetchLogs={(offset) => fetchJobLogs(viewingJobLogs, offset)}
      />
    </DialogContent>
    <DialogActions>
      <Button onClick={() => setViewingJobLogs(null)}>Close</Button>
    </DialogActions>
  </Dialog>
)}
```

Update the "View Logs" button in the recent jobs table (around line 435):
```typescript
<Button
  size="small"
  onClick={() => setViewingJobLogs(job.id)}
>
  View Logs
</Button>
```

---

## Testing Checklist

After implementation, test the following:

1. **Start a backup**:
   - [ ] Backup starts without blocking the UI
   - [ ] Status changes to "running"
   - [ ] Job ID is returned immediately

2. **Real-time log streaming**:
   - [ ] Logs appear in terminal viewer within 2-3 seconds
   - [ ] New lines are added as backup progresses
   - [ ] Timestamps are visible for each line
   - [ ] Terminal auto-scrolls to bottom

3. **Log viewer functionality**:
   - [ ] "Copy Logs" button works
   - [ ] "Download" button creates a .txt file
   - [ ] Manual scrolling disables auto-scroll
   - [ ] "Scroll to bottom" button appears when scrolled up
   - [ ] Auto-scroll re-enables when scrolled to bottom

4. **Error handling**:
   - [ ] Failed backups show exact error messages
   - [ ] No "friendly" error interpretations
   - [ ] stderr is captured in logs
   - [ ] Exit codes are shown

5. **Completion**:
   - [ ] Logs stop updating when backup completes
   - [ ] Status changes to "completed" or "failed"
   - [ ] Full logs are stored in database
   - [ ] Completed jobs show all logs when reopened

---

## Database Migration

After updating the BackupJob model, create and run a migration:

```bash
# Inside the container or with alembic
docker exec -it borgmatic-web-ui bash
cd /app
alembic revision --autogenerate -m "Add log_file_path and other fields to BackupJob"
alembic upgrade head
```

---

## Commit Message Template

When committing Task 1.6, use this template:

```
feat: implement real-time backup logging (Task 1.6)

Backend changes:
- Added BackupService with async backup execution
- Implemented real-time log streaming to files in /data/logs/
- Added /api/backup/logs/{job_id}/stream endpoint for incremental log fetching
- Modified BackupJob model: added log_file_path, progress, logs fields
- Execute borgmatic with --verbosity 1 --files for detailed output
- Backups now run asynchronously (non-blocking)

Frontend changes:
- Created TerminalLogViewer component with dark terminal theme
- Implements log polling every 2 seconds while backup is running
- Auto-scroll to latest log entries
- "Copy Logs" and "Download" functionality
- Line numbers and timestamps displayed
- Exact error messages shown (no interpretation)
- Added log viewer dialog in Backup page

This completes Task 1.6: Backup Execution with Real-time Logging from IMPLEMENTATION_TASKS.md

🤖 Generated with [Claude Code](https://claude.com/claude-code)

Co-Authored-By: Claude <noreply@anthropic.com>
```

---

## Additional Notes

1. **Log File Cleanup**: Consider implementing log file rotation or cleanup to prevent disk space issues
2. **Performance**: The current implementation reads the entire log file on each poll. For very large logs, consider reading only the new portion
3. **Security**: Ensure log files are only accessible by authenticated users
4. **Progress Tracking**: The current implementation doesn't parse progress percentages from borgmatic output. This could be enhanced later.

---

## Next Steps After Task 1.6

Once Task 1.6 is complete, the next tasks from IMPLEMENTATION_TASKS.md are:

- **Phase 2**: Enhancement features (Tab order, Onboarding, Config validation, etc.)
- Update IMPLEMENTATION_TASKS.md progress tracking
- Consider Phase 2 and 3 tasks based on priority

---

**Document Created**: 2025-10-15
**For**: Task 1.6 Implementation
**Status**: Ready for implementation in fresh session
