# Borg output fixtures

Real `borg`/`borg2` output, captured inside the `borg-web-ui-dev` container
with the `borg-live-debug` skill on 2026-09-04.

- `borg --version`: `borg 1.4.5`
- `borg2 --version`: `borg 2.0.0b21`

## Recipe

Two archives, `first` and `second`, built from the same `src` tree. `first`
is created, then the tree is mutated, then `second` is created. `borg list
--json-lines` on `first` produced `borg{1,2}_list.jsonl`; `borg diff
--json-lines first second` produced `borg{1,2}_diff.jsonl`.

```bash
export BORG_PASSPHRASE=fixture
export BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK=yes
W=/tmp/fx; rm -rf $W; mkdir -p $W/src/dir_a $W/src/.cache
printf 'keep\n' > $W/src/keep.txt
printf 'grow\n' > $W/src/grow.txt
printf 'gone\n' > $W/src/gone.txt
printf 'x\n' > $W/src/dir_a/inner.txt
printf 'cached\n' > $W/src/.cache/blob
printf '#!/bin/sh\n' > $W/src/mode.sh
ln -s keep.txt $W/src/link_changed
ln -s keep.txt $W/src/link_removed
cd $W

# Borg 1
borg init -e repokey repo1
borg create repo1::first src
borg list --json-lines repo1::first > borg1_list.jsonl
printf 'grow more\n' >> src/grow.txt
rm src/gone.txt
printf 'new\n' > src/new.txt
mkdir src/dir_new; printf 'y\n' > src/dir_new/f.txt
chmod +x src/mode.sh
rm src/link_changed; ln -s grow.txt src/link_changed
rm src/link_removed
ln -s new.txt src/link_added
borg create repo1::second src
borg diff --json-lines repo1::first second > borg1_diff.jsonl

# reset src to the first state, then repeat for Borg 2 with:
# borg2 -r repo2 repo-create -e repokey-aes-ocb
# borg2 -r repo2 create first src
# borg2 -r repo2 list --json-lines first > borg2_list.jsonl
# ...same mutations...
# borg2 -r repo2 create second src
# borg2 -r repo2 diff first second --json-lines > borg2_diff.jsonl
```

## Format differences the parser (`app/core/borg_diff.py`) handles

- **`list --json-lines` entry shape** differs: Borg 1 keys are `type`, `mode`,
  `user`, `group`, `uid`, `gid`, `path`, `healthy`, `source`, `linktarget`,
  `flags`, `size`, `mtime`. Borg 2 keys are `flags`, `gid`, `group`, `hlid`,
  `inode`, `mode`, `mtime`, `path`, `size`, `target`, `type`, `uid`, `user`.
  Both carry `type` (`-` file, `d` directory, `l` symlink), `path`, and
  `size` (a symlink's `size` is its target string length, not real content,
  so the parser only reads `size` for `type == "-"`).
- **`diff --json-lines` "modified" entries** are identical in both versions:
  `{"type": "modified", "added": N, "removed": N}`.
- **`diff --json-lines` "added"/"removed" presence entries** differ: Borg 1
  reports `{"type": "added", "size": N}`; Borg 2 reports `{"type": "added",
  "added": N, "removed": 0}` (and the mirror for `"removed"`). The parser
  reads `size` when present, else `added` or `removed` by the entry's own
  type.
- **`diff --json-lines` mode changes**: Borg 1 uses `{"type": "mode",
  "old_mode": ..., "new_mode": ...}`; Borg 2 uses `{"type": "changed mode",
  "item1": ..., "item2": ...}`. The parser treats both `"mode"` and
  `"changed mode"` as a mode change and never reads the mode strings
  themselves.
- **Owner changes**: only observed as Borg 1's `{"type": "owner",
  "old_user": ..., "new_user": ..., "old_group": ..., "new_group": ...}`
  (attempting `chown` as a non-root user in the container did not actually
  change ownership; the entry still appeared, apparently reflecting a
  pre-existing owner mismatch from image build vs. archive metadata). The
  parser also accepts a hypothetical `"changed owner"` Borg 2 spelling by
  analogy with `"changed mode"`, though it was not observed live.
- **`"added directory"` / `"removed directory"` / `"added link"` /
  `"removed link"` / `"changed link"`**: identical spelling in both
  versions, never carry a size.
- **ctime/mtime-only changes**: when the only entries are `"ctime"` and/or
  `"mtime"` (a directory's timestamp moved, or a file's metadata changed
  without its content), Borg does not say "this path is unchanged" - it
  reports a delta with no presence and no `"modified"` entry. The parser
  treats this as `change="modified"`, `size_delta=0`.

## A real limitation this fixture surfaces

`borg diff --json-lines` carries no `type` (file/directory/symlink) field on
its entries, unlike `list --json-lines`. A directory whose only change is
its own mtime/ctime (for example `src` itself, bumped whenever a child is
added or removed) is therefore indistinguishable from a metadata-only file
change in the diff stream alone; `parse_diff_line` returns
`ChangeRecord(path, "modified", size_delta=0, is_directory=False)` for it,
same as it would for a file. Spec 6.5 says only the first archive's full
listing stores directories (as `added` rows, filtered out by
`collect_changes` since `is_directory` is true there); this diff-only case
is a narrow, harmless exception; the row is real (the directory's metadata
did change) and carries no content signal (`size_delta=0`), it is simply
not marked as a directory the way an `"added directory"`/`"removed
directory"` entry is.
