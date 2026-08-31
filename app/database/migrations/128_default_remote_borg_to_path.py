"""Use the remote PATH for newly configured SSH connections."""


def upgrade(connection):
    """Keep existing paths because default and explicit values are indistinguishable."""


def downgrade(connection):
    print("✓ Downgrade skipped for migration 128")
