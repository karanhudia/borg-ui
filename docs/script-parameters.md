# Script Parameters

Script parameters allow you to create reusable scripts that can be customized for different repositories without duplicating code. This feature enables you to build a library of parameterized scripts for common tasks like database backups, file processing, or API calls.

## Overview

Script parameters use bash's native `${PARAM}` or `${PARAM:-default}` syntax. When you create a script, Borg UI automatically detects parameter placeholders and generates a configuration interface for them.

## Parameter Syntax

### Basic Parameter

```bash
#!/bin/bash
echo "Processing ${FILE_PATH}"
```

This creates a required parameter called `FILE_PATH`.

### Parameter with Default Value

```bash
#!/bin/bash
DB_HOST="${DB_HOST:-localhost}"
echo "Connecting to database at $DB_HOST"
```

This creates an optional parameter `DB_HOST` with a default value of `localhost`.

### Multiple Parameters

```bash
#!/bin/bash
# Backup MySQL database
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME}"
DB_USER="${DB_USER}"
DB_PASSWORD="${DB_PASSWORD}"

mysqldump -h $DB_HOST -P $DB_PORT -u $DB_USER -p$DB_PASSWORD $DB_NAME > /backup/$DB_NAME.sql
```

This script has 5 parameters:
- `DB_HOST` (optional, default: localhost)
- `DB_PORT` (optional, default: 3306)
- `DB_NAME` (required)
- `DB_USER` (required)
- `DB_PASSWORD` (required, auto-detected as password type)

## Parameter Types

Borg UI automatically detects parameter types based on naming conventions:

### Text Parameters

Default type for most parameters. Used for URLs, file paths, names, etc.

```bash
API_URL="${API_URL}"
BACKUP_DIR="${BACKUP_DIR}"
```

### Password Parameters

Automatically detected when parameter names contain:
- `_PASSWORD`
- `_TOKEN`
- `_SECRET`
- `_KEY`
- `_API_KEY`
- `_PASSPHRASE`
- `_AUTH`
- `_CREDENTIAL`

Password parameters are:
- Encrypted in the database
- Masked in the UI (shown as `***`)
- Input fields show/hide toggle

```bash
DB_PASSWORD="${DB_PASSWORD}"
API_TOKEN="${API_TOKEN}"
SECRET_KEY="${SECRET_KEY}"
AWS_ACCESS_KEY="${AWS_ACCESS_KEY}"
```

## Naming Conventions

Parameter names must follow `UPPER_SNAKE_CASE` format:
- ✅ `DB_HOST`
- ✅ `API_TOKEN`
- ✅ `BACKUP_DIR_PATH`
- ❌ `dbHost` (camelCase not supported)
- ❌ `db-host` (kebab-case not supported)
- ❌ `db_host` (lowercase not supported)

## Creating Parameterized Scripts

### 1. Create the Script

Navigate to **Scripts Library** and click **Create Script**.

```bash
#!/bin/bash
# PostgreSQL Backup Script
#
# This script backs up a PostgreSQL database to a file

PG_HOST="${PG_HOST:-localhost}"
PG_PORT="${PG_PORT:-5432}"
PG_DATABASE="${PG_DATABASE}"
PG_USER="${PG_USER}"
PG_PASSWORD="${PG_PASSWORD}"
BACKUP_FILE="${BACKUP_FILE:-/tmp/backup.sql}"

export PGPASSWORD="$PG_PASSWORD"
pg_dump -h $PG_HOST -p $PG_PORT -U $PG_USER $PG_DATABASE > "$BACKUP_FILE"

echo "Database backed up to $BACKUP_FILE"
```

### 2. Save and Review Parameters

After saving, Borg UI automatically detects 6 parameters:
- `PG_HOST` (text, optional)
- `PG_PORT` (text, optional)
- `PG_DATABASE` (text, required)
- `PG_USER` (text, required)
- `PG_PASSWORD` (password, required)
- `BACKUP_FILE` (text, optional)

### 3. Assign to Repository

When assigning the script to a repository:

1. Go to repository **Scripts** tab
2. Click **Assign Script**
3. Select your parameterized script
4. Fill in parameter values:
   - `PG_DATABASE`: `production_db`
   - `PG_USER`: `postgres`
   - `PG_PASSWORD`: `secure-password-here`
   - Leave `PG_HOST`, `PG_PORT`, `BACKUP_FILE` empty to use defaults

### 4. Test the Script

Use the **Test** button to execute the script with your parameter values before running it as part of a backup.

## System Variables

In addition to your custom parameters, scripts have access to system-provided environment variables:

- `REPOSITORY_ID`: Repository ID
- `REPOSITORY_NAME`: Repository name
- `REPOSITORY_PATH`: Full repository path
- `BORG_REPO`: Alias for `REPOSITORY_PATH`
- `BACKUP_STATUS`: Backup result (for post-backup scripts)
  - `success`: Backup completed successfully
  - `failure`: Backup failed
  - `warning`: Backup completed with warnings
- `HOOK_TYPE`: Hook type
  - `pre-backup`: Script runs before backup
  - `post-backup`: Script runs after backup

### Example Using System Variables

```bash
#!/bin/bash
# Send backup notification

WEBHOOK_URL="${WEBHOOK_URL}"
SERVICE_NAME="${SERVICE_NAME}"

# Use system variables
MESSAGE="Backup of $REPOSITORY_NAME to $BORG_REPO completed with status: $BACKUP_STATUS"

curl -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{\"text\": \"$MESSAGE\", \"service\": \"$SERVICE_NAME\"}"
```

## Security Best Practices

### 1. Use Password Parameters for Secrets

Always use password-type naming for sensitive data:

```bash
# ✅ Good
API_TOKEN="${API_TOKEN}"
DB_PASSWORD="${DB_PASSWORD}"

# ❌ Bad
API_CREDENTIALS="${API_CREDENTIALS}"  # Won't be encrypted
DATABASE_PASS="${DATABASE_PASS}"      # Won't be encrypted
```

### 2. Don't Hardcode Secrets

```bash
# ❌ Bad - hardcoded password
DB_PASSWORD="my-password-123"

# ✅ Good - parameterized
DB_PASSWORD="${DB_PASSWORD}"
```

### 3. Quote Variables in Shell Commands

Always quote variables to prevent word splitting and injection:

```bash
# ✅ Good
mysqldump -h "$DB_HOST" -u "$DB_USER" "$DB_NAME" > "$BACKUP_FILE"

# ❌ Bad
mysqldump -h $DB_HOST -u $DB_USER $DB_NAME > $BACKUP_FILE
```

## Example Scripts

### Database Backup (MySQL)

```bash
#!/bin/bash
set -e

DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-3306}"
DB_NAME="${DB_NAME}"
DB_USER="${DB_USER}"
DB_PASSWORD="${DB_PASSWORD}"

BACKUP_DIR="/tmp/mysql-backups"
mkdir -p "$BACKUP_DIR"

BACKUP_FILE="$BACKUP_DIR/${DB_NAME}_$(date +%Y%m%d_%H%M%S).sql"

mysqldump \
  -h "$DB_HOST" \
  -P "$DB_PORT" \
  -u "$DB_USER" \
  -p"$DB_PASSWORD" \
  "$DB_NAME" > "$BACKUP_FILE"

gzip "$BACKUP_FILE"

echo "Backup saved: ${BACKUP_FILE}.gz"
```

### API Health Check

```bash
#!/bin/bash
API_URL="${API_URL}"
API_TOKEN="${API_TOKEN}"
TIMEOUT="${TIMEOUT:-10}"

response=$(curl -s -w "%{http_code}" -o /dev/null \
  --max-time "$TIMEOUT" \
  -H "Authorization: Bearer $API_TOKEN" \
  "$API_URL/health")

if [ "$response" = "200" ]; then
  echo "API is healthy"
  exit 0
else
  echo "API health check failed: HTTP $response"
  exit 1
fi
```

### File Sync to S3

```bash
#!/bin/bash
set -e

AWS_ACCESS_KEY="${AWS_ACCESS_KEY}"
AWS_SECRET_KEY="${AWS_SECRET_KEY}"
S3_BUCKET="${S3_BUCKET}"
S3_PREFIX="${S3_PREFIX:-backups}"
LOCAL_PATH="${LOCAL_PATH}"

export AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY"
export AWS_SECRET_ACCESS_KEY="$AWS_SECRET_KEY"

aws s3 sync "$LOCAL_PATH" "s3://${S3_BUCKET}/${S3_PREFIX}/" \
  --exclude ".DS_Store" \
  --exclude "*.tmp"

echo "Synced $LOCAL_PATH to s3://${S3_BUCKET}/${S3_PREFIX}/"
```

### Webhook Notification

```bash
#!/bin/bash
WEBHOOK_URL="${WEBHOOK_URL}"
MESSAGE_PREFIX="${MESSAGE_PREFIX:-Backup}"

# Use system variables
if [ "$BACKUP_STATUS" = "success" ]; then
  COLOR="good"
  EMOJI="✅"
elif [ "$BACKUP_STATUS" = "failure" ]; then
  COLOR="danger"
  EMOJI="❌"
else
  COLOR="warning"
  EMOJI="⚠️"
fi

MESSAGE="$EMOJI $MESSAGE_PREFIX of *$REPOSITORY_NAME* $BACKUP_STATUS"

curl -X POST "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -d "{
    \"attachments\": [{
      \"color\": \"$COLOR\",
      \"text\": \"$MESSAGE\"
    }]
  }"
```

## Troubleshooting

### Parameter Not Detected

If your parameter isn't being detected:

1. Check naming convention: Must be `UPPER_SNAKE_CASE`
2. Check syntax: Must be `${PARAM}` or `${PARAM:-default}`
3. Save the script again to trigger re-parsing

### Parameter Value Not Working

If your parameter value isn't being used:

1. Check the parameter name matches exactly (case-sensitive)
2. Verify the script uses `$PARAM` or `${PARAM}` to reference it
3. Check script execution logs for actual values

### Password Not Encrypted

Password encryption is automatic for parameters with names containing:
- `_PASSWORD`, `_TOKEN`, `_SECRET`, `_KEY`, etc.

If your password isn't encrypted, rename it to match one of these patterns.

### Script Fails with "Command not found"

Environment variables are passed correctly, but:

1. Ensure required tools are installed in the container
2. Check file paths are absolute
3. Verify permissions on executables

## Validation Rules

- **Required parameters**: Must have a non-empty value when no default is provided
- **Maximum length**: Parameter values cannot exceed 10,000 characters
- **Parameter names**: Must match `/^[A-Z_][A-Z0-9_]*$/` pattern

## Limitations

- Parameter syntax is limited to bash's `${VAR}` and `${VAR:-default}` formats
- Complex parameter types (numbers, arrays, objects) are not supported
- Parameters cannot reference other parameters
- Cannot use parameter values in shebang line

## API Reference

For programmatic access to script parameters:

### Create Script with Parameters

```bash
POST /api/scripts
{
  "name": "My Script",
  "content": "#!/bin/bash\necho ${MY_PARAM}",
  "category": "custom",
  "timeout": 300
}
```

Response includes auto-parsed `parameters` array.

### Assign Script with Parameters

```bash
POST /api/repositories/{repo_id}/scripts
{
  "script_id": 123,
  "hook_type": "pre-backup",
  "parameter_values": {
    "MY_PARAM": "my-value",
    "MY_PASSWORD": "secret"
  }
}
```

Password values are automatically encrypted.

### Update Parameter Values

```bash
PUT /api/repositories/{repo_id}/scripts/{assignment_id}
{
  "parameter_values": {
    "MY_PARAM": "new-value"
  }
}
```

## Related Documentation

- [Scripts Library Overview](usage-guide.md#scripts-library)
- [Pre/Post Backup Hooks](docker-hooks.md)
- [Security Best Practices](security.md)
