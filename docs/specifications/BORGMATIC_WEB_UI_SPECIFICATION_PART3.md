# Borgmatic Web UI - Technical Specification (Part 3)

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
FROM python:3.9-slim AS backend-builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Production stage
FROM python:3.9-slim AS production
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    cron \
    borgbackup \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies
COPY --from=backend-builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# Copy application code
COPY app/ ./app/
COPY --from=frontend-builder /app/frontend/build ./app/static

# Create non-root user
RUN useradd -m -u 1000 borgmatic && \
    chown -R borgmatic:borgmatic /app

# Switch to non-root user
USER borgmatic

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
  borgmatic-ui:
    build: .
    container_name: borgmatic-web-ui
    ports:
      - "8080:8000"
    volumes:
      - ./config:/app/config:ro
      - ./backups:/backups:ro
      - ./logs:/app/logs
      - /etc/cron.d:/etc/cron.d:ro
    environment:
      - BORGMATIC_CONFIG_PATH=/app/config
      - BORGMATIC_BACKUP_PATH=/backups
      - LOG_LEVEL=INFO
      - SECRET_KEY=${SECRET_KEY}
    restart: unless-stopped
    networks:
      - borgmatic-network

  # Optional: PostgreSQL for production
  postgres:
    image: postgres:13-alpine
    container_name: borgmatic-db
    environment:
      - POSTGRES_DB=borgmatic
      - POSTGRES_USER=borgmatic
      - POSTGRES_PASSWORD=${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped
    networks:
      - borgmatic-network

networks:
  borgmatic-network:
    driver: bridge

volumes:
  postgres_data:
```

### 7.3 Environment Configuration

```bash
# .env file
SECRET_KEY=your-secret-key-here
DB_PASSWORD=your-db-password
BORGMATIC_CONFIG_PATH=/app/config
BORGMATIC_BACKUP_PATH=/backups
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
    config_path = os.getenv("BORGMATIC_CONFIG_PATH")
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
    return await borgmatic.get_repository_status()
```

#### 9.2.2 Database Optimization
```python
# Database connection pooling
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    "sqlite:///borgmatic.db",
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
# tests/test_borgmatic.py
import pytest
from app.core.borgmatic import BorgmaticInterface

@pytest.fixture
def borgmatic_interface():
    return BorgmaticInterface("/tmp/test_config")

@pytest.mark.asyncio
async def test_run_backup(borgmatic_interface):
    result = await borgmatic_interface.run_backup("test_repo")
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

This technical specification provides a comprehensive framework for developing a lightweight, feature-rich web UI for Borgmatic. The solution addresses all core requirements while maintaining focus on resource efficiency and ease of deployment.

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

This specification provides a solid foundation for building a production-ready Borgmatic web UI that meets all requirements while maintaining the lightweight, efficient design necessary for resource-constrained devices. 