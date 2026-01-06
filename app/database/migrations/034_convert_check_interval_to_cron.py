"""
Migration 034: Convert check interval_days to cron expressions

This migration:
1. Adds check_cron_expression column to repositories table
2. Converts existing check_interval_days values to cron expressions
3. Drops check_interval_days column

Interval to cron conversion:
- 1 day   -> "0 2 * * *" (daily at 2 AM)
- 7 days  -> "0 2 * * 0" (weekly on Sunday at 2 AM)
- 14 days -> "0 2 */14 * *" (every 14 days at 2 AM)
- 30 days -> "0 2 1 * *" (monthly on 1st at 2 AM)
- 90 days -> "0 2 1 */3 *" (quarterly on 1st at 2 AM)
- Other   -> "0 2 */{interval} * *" (every N days at 2 AM)
"""

from sqlalchemy import text


def interval_to_cron(interval_days: int) -> str:
    """Convert interval_days to cron expression"""
    if interval_days == 1:
        return "0 2 * * *"  # Daily at 2 AM
    elif interval_days == 7:
        return "0 2 * * 0"  # Weekly on Sunday at 2 AM
    elif interval_days == 14:
        return "0 2 */14 * *"  # Every 14 days at 2 AM
    elif interval_days == 30:
        return "0 2 1 * *"  # Monthly on 1st at 2 AM
    elif interval_days == 90:
        return "0 2 1 */3 *"  # Quarterly on 1st at 2 AM
    else:
        # For custom intervals, use */N syntax for day-of-month
        # Note: This is an approximation - cron doesn't support exact N-day intervals
        return f"0 2 */{interval_days} * *"


def upgrade(conn):
    """Add check_cron_expression and migrate data from check_interval_days"""

    # Check which columns exist
    result = conn.execute(text("PRAGMA table_info(repositories)"))
    existing_columns = {row[1] for row in result}

    has_cron_column = 'check_cron_expression' in existing_columns
    has_interval_column = 'check_interval_days' in existing_columns

    # Step 1: Add new column (nullable initially) if it doesn't exist
    if not has_cron_column:
        conn.execute(text("""
            ALTER TABLE repositories
            ADD COLUMN check_cron_expression TEXT
        """))
        print("✓ Added check_cron_expression column")
    else:
        print("⊘ Column check_cron_expression already exists, skipping")

    # Step 2: Migrate data from check_interval_days to check_cron_expression
    # Only if the old column still exists
    if has_interval_column:
        # Get all repositories with check_interval_days set
        result = conn.execute(text("""
            SELECT id, check_interval_days
            FROM repositories
            WHERE check_interval_days IS NOT NULL
        """))

        repositories = result.fetchall()

        # Convert each interval to cron expression
        for repo_id, interval_days in repositories:
            cron_expr = interval_to_cron(interval_days)
            conn.execute(
                text("""
                    UPDATE repositories
                    SET check_cron_expression = :cron_expr
                    WHERE id = :repo_id
                """),
                {"cron_expr": cron_expr, "repo_id": repo_id}
            )

        if repositories:
            print(f"✓ Migrated {len(repositories)} repositories from check_interval_days to check_cron_expression")

    # Step 3: Drop the old column if it still exists
    # Note: SQLite doesn't support DROP COLUMN easily, so we check first
    if has_interval_column:
        try:
            conn.execute(text("""
                ALTER TABLE repositories
                DROP COLUMN check_interval_days
            """))
            print("✓ Dropped check_interval_days column")
        except Exception as e:
            print(f"! Could not drop check_interval_days column (may require SQLite 3.35+): {e}")
            print("! The column will remain but is no longer used")
    else:
        print("⊘ Column check_interval_days already removed, skipping")

    conn.commit()


def downgrade(conn):
    """
    Restore check_interval_days column (data loss warning!)

    Note: This downgrade will convert cron expressions back to interval_days
    with best-effort approximation. Some precision may be lost.
    """

    # Step 1: Add back check_interval_days column
    conn.execute(text("""
        ALTER TABLE repositories
        ADD COLUMN check_interval_days INTEGER
    """))

    # Step 2: Convert cron expressions back to intervals (best effort)
    cron_to_interval_map = {
        "0 2 * * *": 1,       # Daily
        "0 2 * * 0": 7,       # Weekly
        "0 2 */14 * *": 14,   # Every 14 days
        "0 2 1 * *": 30,      # Monthly
        "0 2 1 */3 *": 90,    # Quarterly
    }

    # Get all repositories with cron expressions
    result = conn.execute(text("""
        SELECT id, check_cron_expression
        FROM repositories
        WHERE check_cron_expression IS NOT NULL
    """))

    repositories = result.fetchall()

    for repo_id, cron_expr in repositories:
        # Try exact match first
        interval_days = cron_to_interval_map.get(cron_expr)

        # If no exact match, try to parse */N pattern
        if interval_days is None and cron_expr:
            try:
                parts = cron_expr.split()
                if len(parts) == 5 and parts[2].startswith("*/"):
                    interval_days = int(parts[2][2:])
            except:
                # Default to 7 days if unable to parse
                interval_days = 7

        if interval_days is not None:
            conn.execute(
                text("""
                    UPDATE repositories
                    SET check_interval_days = :interval_days
                    WHERE id = :repo_id
                """),
                {"interval_days": interval_days, "repo_id": repo_id}
            )

    # Step 3: Drop cron_expression column
    conn.execute(text("""
        ALTER TABLE repositories
        DROP COLUMN check_cron_expression
    """))

    conn.commit()
