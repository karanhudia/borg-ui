"""Build a database the way a released version did, then seed it.

Runs in a subprocess whose working directory and import path are the
release's own `app` tree, so every model, migration and default comes from
that release. It imports nothing from the current code base.

    python build_release.py <alembic|legacy> <request.json> <manifest.json>

The request names extra rows to add (``{"rows": {table: [values, ...]}}``)
and whether to add orphans. The manifest written back records the primary
key, the foreign keys and the other values of every row this script
inserted, so the caller can find each one, and what it held, after the
upgrade.
"""

import datetime
import json
import sys

from sqlalchemy import Integer, MetaData, String, create_engine, insert, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.types import TypeDecorator

# Far outside any id the seed creates; an orphan points here.
MISSING_ID = 900_000


def build(mode):
    if mode == "alembic":
        from app.database.db_upgrade import upgrade_from_settings

        upgrade_from_settings()
        return

    # Before Alembic the schema came from the models at import, then the
    # legacy migrations at startup. Twice: an install has restarted at least
    # once, and the second pass is where some migrations finish their work.
    from app.database.database import Base, engine
    import app.database.models  # noqa: F401
    from app.database.migrations import run_migrations

    for _ in range(2):
        Base.metadata.create_all(bind=engine)
        run_migrations()
    engine.dispose()


def _value(column, model_column, n):
    """A value of the column's type, distinct per row number `n`."""
    kind = model_column.type if model_column is not None else column.type
    if isinstance(kind, TypeDecorator):
        kind = kind.impl
    try:
        python_type = kind.python_type
    except NotImplementedError:
        python_type = str
    if python_type is bool:
        return True
    if python_type is int:
        return n
    if python_type is float:
        return n + 0.5
    if python_type is datetime.datetime:
        return datetime.datetime(2026, 9, 1, 12, 0, n % 60)
    if python_type is datetime.date:
        return datetime.date(2026, 9, 1)
    if python_type in (dict, list):
        return {}
    if python_type is bytes:
        return b"seed"
    text = f"{column.table.name}.{column.name}.{n}"
    length = getattr(column.type, "length", None)
    if isinstance(column.type, String) and length:
        text = text[-length:]
    return text


def _generated_pk(table):
    """The primary key column the database assigns, if there is one."""
    pk = list(table.primary_key.columns)
    if len(pk) == 1 and isinstance(pk[0].type, Integer) and not pk[0].foreign_keys:
        return pk[0]
    return None


def seed(request):
    from app.config import settings
    from app.database.database import Base
    import app.database.models  # noqa: F401

    models = Base.metadata.tables
    # A plain engine: SQLite does not enforce foreign keys unless asked to,
    # which is what lets the orphans below in, as it did for old installs.
    engine = create_engine(settings.database_url)
    db = MetaData()
    db.reflect(bind=engine)
    extra = request.get("rows", {})
    manifest = {"rows": {}, "orphans": [], "skipped_orphans": [], "added": {}}
    manifest["missing_tables"] = sorted(set(extra) - set(db.tables))
    if manifest["missing_tables"]:
        return manifest  # the caller skips: this release predates the table
    first = {}  # table -> primary key values of its first seeded row
    counter = 0

    def row_values(table, given, n, orphan_column=None):
        model = models.get(table.name)
        values = {}
        generated = _generated_pk(table)
        for column in table.columns:
            model_column = model.columns.get(column.name) if model is not None else None
            if column.name in given:
                value = given[column.name]
            elif column is generated:
                continue
            elif column.name == orphan_column:
                value = MISSING_ID
            elif orphan_column and column.foreign_keys and column.nullable:
                # Only the orphan's own pointer dangles; leaving the others
                # empty also keeps a one-to-one link from colliding.
                value = None
            elif column.foreign_keys:
                fk = next(iter(column.foreign_keys))
                parent = first.get(fk.column.table.name)
                value = parent.get(fk.column.name) if parent else None
                if value is None and fk.column.table is table:
                    continue  # self-reference on the first row: leave it NULL
            else:
                value = _value(column, model_column, n)
            values[column.name] = value
        return values

    def add(conn, table, values):
        """Insert a row; return its key, its references and its other values.

        Values are recorded as the application meant them, before a column
        type such as an encrypted string turned them into what is stored.
        """
        model = models.get(table.name)
        stored = dict(values)
        for name, value in values.items():
            model_column = model.columns.get(name) if model is not None else None
            if model_column is not None and isinstance(
                model_column.type, TypeDecorator
            ):
                stored[name] = model_column.type.process_bind_param(
                    value, engine.dialect
                )
        result = conn.execute(insert(table).values(**stored))
        generated = _generated_pk(table)
        key = {c.name: values.get(c.name) for c in table.primary_key.columns}
        if generated is not None and key[generated.name] is None:
            key[generated.name] = result.inserted_primary_key[0]
        refs, plain = {}, {}
        for column in table.columns:
            if column.name not in values or column.primary_key:
                continue
            if column.foreign_keys:
                if values[column.name] is not None:
                    refs[column.name] = values[column.name]
            else:
                plain[column.name] = values[column.name]
        return {"key": key, "refs": refs, "values": plain}

    with engine.begin() as conn:
        for table in db.sorted_tables:
            if table.name in ("alembic_version", "sqlite_sequence"):
                continue
            counter += 1
            row = add(conn, table, row_values(table, {}, counter))
            first[table.name] = row["key"]
            manifest["rows"].setdefault(table.name, []).append(row)

        for name, rows in extra.items():
            table = db.tables[name]
            for given in rows:
                counter += 1
                row = add(conn, table, row_values(table, given, counter))
                manifest["added"].setdefault(name, []).append(row)

        if request.get("orphans"):
            for table in db.sorted_tables:
                for column in table.columns:
                    fks = [
                        fk for fk in column.foreign_keys if fk.column.table is not table
                    ]
                    if not fks:
                        continue
                    counter += 1
                    values = row_values(table, {}, counter, column.name)
                    try:
                        with conn.begin_nested():
                            key = add(conn, table, values)["key"]
                    except IntegrityError as exc:
                        # A required one-to-one link to the only parent row.
                        manifest["skipped_orphans"].append(
                            f"{table.name}.{column.name}: {exc.orig}"
                        )
                        continue
                    manifest["orphans"].append(
                        {
                            "table": table.name,
                            "column": column.name,
                            "nullable": column.nullable,
                            "key": key,
                        }
                    )

        if engine.dialect.name == "postgresql":
            # Rows given an explicit id leave the sequence behind, a state no
            # install is in; a revision inserting later would collide.
            for table in db.sorted_tables:
                pk = _generated_pk(table)
                if pk is not None:
                    conn.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{table.name}', "
                            f'\'{pk.name}\'), MAX("{pk.name}")) FROM "{table.name}"'
                        )
                    )
    engine.dispose()
    return manifest


def _decode(obj):
    """Dates and datetimes arrive tagged; JSON has no type for them."""
    if "__datetime__" in obj:
        return datetime.datetime.fromisoformat(obj["__datetime__"])
    if "__date__" in obj:
        return datetime.date.fromisoformat(obj["__date__"])
    return obj


def main():
    mode, request_path, manifest_path = sys.argv[1:4]
    with open(request_path) as fh:
        request = json.load(fh, object_hook=_decode)
    build(mode)
    manifest = seed(request)
    with open(manifest_path, "w") as fh:
        json.dump(manifest, fh, default=str)


if __name__ == "__main__":
    main()
