# Archive folder download

## Goal

Let a viewer download one selected directory from the archive browser as a
streamed `.tar` file, without restoring it to server or agent storage.

## Acceptance criteria

- A directory selection exposes a **Download folder** action; file download
  behavior remains unchanged.
- Borg 1 and Borg 2 invoke `export-tar` for exactly the selected path and
  stream the bytes to the browser.
- Agent-backed repositories use the existing artifact relay; no archive bytes
  travel through WebSocket/base64 or persist on the server.
- The endpoint retains viewer access checks, safe attachment filename handling,
  first-byte error responses, and disconnect/idle cleanup.
- Focused backend, agent command, frontend utility/component, and Storybook
  coverage demonstrate the changed state.

## Non-goals

- ZIP, gzip, format selection, multi-selection export, progress percentage, or
  temporary archive files.
