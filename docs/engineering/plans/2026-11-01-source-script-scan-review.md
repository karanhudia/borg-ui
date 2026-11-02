# Source-script reuse and remote scan review fixes

- [x] Reproduce reuse failures after deleting the base script and when parameter definitions change. Search all numbered template copies even when the base name is free; compare effective explicit or inferred parameters before reusing a script.
- [x] Reproduce remote shell startup exit 127 being called an unreachable host, and SSH exit 255 after probe startup being treated as a command failure.
- [x] Emit a remote exit-status marker through a POSIX shell exit trap. Treat SSH exit 255 as a transport failure unless the probe explicitly reports a matching remote exit. Strip internal markers from warnings and preserve partial detections for scan-command failures.
- [x] Verify 105 script-library/source-discovery tests and targeted partial-detection and real-shell exit-trap checks. Ruff lint/format and whitespace checks pass.

Nine cases failed before implementation. No actual SSH connections or destructive script executions were performed; shell tests use controlled scripts. Existing dependency deprecations remain. No UI, locale string or version changed.
