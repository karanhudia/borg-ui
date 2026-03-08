# Feature request: JSON syntax highlighting in the backup log terminal

## Summary

The backup log terminal renders all output as plain white text. Borg produces structured
JSON log messages (via `--log-json`) for progress, stats, and warnings. Colorising JSON
tokens in-place makes these dense messages significantly easier to scan at a glance.

## Background

When borg is run with `--log-json`, every status line is a JSON object:

```json
{"type":"progress_message","operation":5,"msgid":null,"finished":false,"message":"Calculating statistics... 1048576 kB"}
{"type":"archive_progress","original_size":10737418240,"compressed_size":2147483648,"deduplicated_size":536870912,"nfiles":12543,"path":"/etc/ssl/private/ca.key","time":1709123456.789}
{"type":"log_message","name":"borg.archive","level":"WARNING","message":"Item has a hardlink to a file inside the repository."}
```

Without highlighting, the keys, string values, numbers, and keywords all render
identically. With highlighting, the type and key fields stand out immediately and
error/warning messages are easy to spot.

## Proposed colour scheme

Following VS Code Dark+ conventions (familiar to most developers):

| Token type | Colour | Hex | Example |
|------------|--------|-----|---------|
| Object keys | Light blue | `#9cdcfe` | `"type"`, `"message"` |
| String values | Orange-red | `#ce9178` | `"progress_message"`, `"WARNING"` |
| Numbers | Light green | `#b5cea8` | `10737418240`, `1709123456.789` |
| Booleans / null | Blue | `#569cd6` | `true`, `false`, `null` |
| Punctuation | Default text | `#d4d4d4` | `{ } [ ] : ,` |

Non-JSON lines (plain borg output, hook script output) are rendered unchanged.

## Implementation approach

A single-pass regex tokenizer avoids a full JSON parse-and-re-serialize round-trip,
preserving the original formatting and whitespace exactly.

The key challenge is distinguishing keys from string values — only quoted strings
immediately followed by `:` are keys:

```
/"key"\s*(?=:)/   → object key    → light blue
/"value"/         → string value  → orange-red
/\d+(\.\d+)?/    → number        → light green
/true|false|null/ → keyword       → blue
/[{}[\],:]      / → punctuation   → default
```

The colorizer is applied per log line only when the trimmed line starts with `{` or `[`
and parses as valid JSON, so plain-text lines have zero overhead.

## Performance considerations

- The regex runs once per new log line as it arrives, not on every render.
- Each rendered log line should be wrapped in `React.memo` so that appending a new line
  at the bottom does not trigger re-renders of the hundreds of already-rendered lines
  above it.

## Affected files

- `frontend/src/components/TerminalLogViewer.tsx` — add `colorizeJsonLine()` helper and
  memoised `LogLine` sub-component; replace the current plain `{log.content}` render

---

## Working implementation

This feature is implemented in a fork. Clone and build to try it:

```bash
git clone https://github.com/djlongy/borg-ui.git
cd borg-ui
docker build -f Dockerfile.dev -t borg-ui-dev .
docker run -d \
  --name borg-ui-test \
  -p 8082:8081 \
  -e SECRET_KEY=changeme \
  -e ADMIN_USERNAME=admin \
  -e ADMIN_PASSWORD=admin \
  borg-ui-dev
```

Run any backup and open the log viewer — JSON lines are colourised automatically.
Plain-text lines (hook script output, borg info messages) are unaffected.

> `Dockerfile.dev` uses `npx vite build` (skips TypeScript type-checking) so the
> build completes even if dev dependencies are mismatched. On amd64 hosts use
> `docker buildx build --platform linux/amd64 -f Dockerfile.dev ...` instead.

**Relevant commit**: [`c8f5e74`](https://github.com/djlongy/borg-ui/commit/c8f5e74)
`feat(sudo): add use_sudo option for remote SSH backups + fix log viewer`

**Fork**: https://github.com/djlongy/borg-ui
