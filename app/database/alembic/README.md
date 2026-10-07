# Database migrations

The schema is managed by Alembic against a single baseline, and the same
migration body must work on **both SQLite and Postgres**. The engine and URL come
from the application settings (`env.py` reads `settings.database_url`), and every
migration is rendered in batch mode, so one migration serves SQLite (table
rebuild) and Postgres (native `ALTER`) alike.

The CI test matrix applies every migration to SQLite **and** Postgres, so most
dialect mistakes fail hard on the Postgres leg rather than slipping through. Four
conventions keep a migration dialect-agnostic:

1. **DDL only through the `op` API** — never a raw SQL string. `op.add_column`,
   `op.create_index`, `batch_op.alter_column`, and so on. Raw SQL freezes one
   dialect's grammar.
2. **Boolean defaults as `sa.false()` / `sa.true()`** — never a literal `0`/`1`.
   `ADD COLUMN f BOOLEAN DEFAULT 0` is accepted by SQLite and rejected by Postgres
   with a `DatatypeMismatch`.
3. **Data migrations through SQLAlchemy Core** — `table.update().values(flag=True)`,
   never a raw `UPDATE ... SET flag = 1`. Same reason as (2).
4. **`server_default` must render per dialect** — use `sa.func.now()`, never
   `sa.text('CURRENT_TIMESTAMP')` or `sa.text('0')`. `autogenerate` **freezes the
   dialect it ran against** into every `server_default`, so never ship a generated
   one unreviewed: generated against SQLite it dies loudly on Postgres; generated
   against Postgres it passes on SQLite and then breaks at the first insert.

**For anything SQLite cannot `ALTER`** — dropping or altering a column, changing a
constraint, changing a foreign-key action — wrap it in `op.batch_alter_table(...)`.
On SQLite, Alembic performs the create-copy-drop-rename rebuild automatically; on
Postgres it emits a native `ALTER`. One body, both dialects.

**When a batch operation touches an AUTOINCREMENT table**, pass
`table_kwargs={"sqlite_autoincrement": True}`. The rebuild loses AUTOINCREMENT
otherwise, and reflection can never see that it is gone, so the drift would be
permanent and invisible. (The baseline's `create_table` renders it correctly;
only `batch_alter_table` needs the reminder.)

## Workflow

1. Change `models.py`. AUTOINCREMENT is derived from the primary key, so a new
   single-integer-PK table gets it automatically; a new constraint is named by the
   metadata naming convention automatically.
2. `alembic revision --autogenerate -m "<what>"`.
3. **Review the generated file.** Fix every `server_default` to a dialect-agnostic
   form (convention 4); confirm any `batch_alter_table` on an AUTOINCREMENT table
   carries `sqlite_autoincrement`. These two — AUTOINCREMENT on a batch rebuild and
   a frozen `server_default` — are the things `autogenerate` gets wrong, because it
   is blind to both.
4. **Add an upgrade test.** A module under `tests/migrations/` declaring
   `REVISION = "<id>"` that uses the `upgraded_from` fixture: it builds a
   database with each release's own code, adds the rows your revision touches,
   upgrades it the way a container starts and hands you the result to check.
   Test from every release that does not have the revision yet
   (`upgrade_paths.releases_before(REVISION)`), not from the parent revision on
   an empty database. A revision without such a module fails CI.
5. Run the test suite. It applies the migration to SQLite and to Postgres; a
   dialect violation fails the Postgres leg.

Rule of thumb: **anything the framework can enforce, it does; the two it cannot
see — AUTOINCREMENT on a batch rebuild, and a frozen `server_default` — are the two
you review by hand.**

## Upgrade paths

`tests/migrations/test_upgrade_paths.py` builds a database with every release
since 2.3.0, and the last release of each line before Alembic, using that
release's own code from its git tag. It seeds one row per table (plus one
orphan per foreign key in a pre-Alembic database), upgrades it with
`python -m app.database.db_upgrade` into SQLite and Postgres, and checks that
every row survived, that orphans were handled, and that every table reads back
through the models. It needs the release tags: `git fetch --tags <upstream>`.
