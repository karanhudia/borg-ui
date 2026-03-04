---
phase: 05-locale-file-completion-and-ci-validation
plan: "03"
subsystem: frontend-i18n
tags: [locale, translations, spanish, german, i18next, gap-closure]
dependency_graph:
  requires: [05-02]
  provides: [LOC-02, LOC-03]
  affects: [frontend/src/locales/es.json, frontend/src/locales/de.json]
tech_stack:
  added: []
  patterns: [i18next interpolation tokens preserved in translated strings]
key_files:
  created: []
  modified:
    - frontend/src/locales/es.json
    - frontend/src/locales/de.json
decisions:
  - "12 English placeholder values in es.json (backup/borg/service domains) replaced with real Spanish translations"
  - "12 English placeholder values in de.json (backup/borg/service domains) replaced with real German translations"
  - "i18next interpolation tokens ({{count}}, {{exitCode}}, {{failed}}, {{total}}) preserved exactly in all translated strings"
metrics:
  duration: "2 min"
  completed: "2026-03-04"
  tasks_completed: 2
  files_modified: 2
---

# Phase 5 Plan 03: Spanish and German Translations for 12 Placeholder backend.* Keys — Summary

**One-liner:** Replaced all 12 English placeholder values in es.json and de.json (backup cancellation, borg errors, restore failures) with real Spanish and German translations; parity holds at 2064 keys.

## Tasks Completed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | Add real Spanish translations for 12 placeholder keys in es.json | 735fe7b | frontend/src/locales/es.json |
| 2 | Add real German translations for 12 placeholder keys in de.json | 1a6c9f7 | frontend/src/locales/de.json |

## What Was Built

### Task 1 — Spanish translations (es.json)

Replaced 12 English placeholder values under `backend.errors.backup`, `backend.errors.borg`, and `backend.errors.service` with real Spanish translations:

- `backup.cancelledByUser` → "Copia de seguridad cancelada por el usuario"
- `backup.cancelledByUserProcessNotFound` → "Copia de seguridad cancelada por el usuario (proceso no encontrado, puede que ya haya terminado)"
- `borg.additionalErrors` → "Se encontraron errores adicionales: {{count}}"
- `borg.exitCodeError` → "Error de Borg (código de salida {{exitCode}})"
- `borg.unknownError` → "Ocurrió un error desconocido de Borg"
- `service.postBackupHooksAlsoFailed` → "Los hooks post-copia de seguridad también fallaron: {{failed}}/{{total}} scripts fallaron"
- `service.restoreFailed` → "La restauración falló"
- `service.restoreFailedExitCode` → "El proceso de restauración terminó con el código {{exitCode}}"
- `service.restoreFailedZeroFiles` → "Restauración fallida: 0 archivos extraídos (código de salida {{exitCode}}). Consulte los registros para más detalles."
- `service.restoreFailedZeroFilesNoOutput` → "Restauración fallida: 0 archivos extraídos (código de salida {{exitCode}}). Sin salida de error de Borg. Es posible que los archivos no existan en el archivo o que el acceso esté denegado."
- `service.restoreFailedZeroFilesPathNotFound` → "Restauración fallida: 0 archivos extraídos (código de salida {{exitCode}}). Ruta no encontrada en el archivo o el destino no existe."
- `service.restoreFailedZeroFilesPermission` → "Restauración fallida: 0 archivos extraídos (código de salida {{exitCode}}). Permiso denegado - puede que necesite acceso de root o una ruta de destino diferente."

### Task 2 — German translations (de.json)

Replaced the same 12 English placeholder values with real German translations:

- `backup.cancelledByUser` → "Backup vom Benutzer abgebrochen"
- `backup.cancelledByUserProcessNotFound` → "Backup vom Benutzer abgebrochen (Prozess nicht gefunden, möglicherweise bereits abgeschlossen)"
- `borg.additionalErrors` → "Weitere Fehler aufgetreten: {{count}}"
- `borg.exitCodeError` → "Borg-Fehler (Exitcode {{exitCode}})"
- `borg.unknownError` → "Unbekannter Borg-Fehler aufgetreten"
- `service.postBackupHooksAlsoFailed` → "Post-Backup-Hooks sind ebenfalls fehlgeschlagen: {{failed}}/{{total}} Skripte fehlgeschlagen"
- `service.restoreFailed` → "Wiederherstellung fehlgeschlagen"
- `service.restoreFailedExitCode` → "Der Wiederherstellungsprozess wurde mit Code {{exitCode}} beendet"
- `service.restoreFailedZeroFiles` → "Wiederherstellung fehlgeschlagen: 0 Dateien extrahiert (Exitcode {{exitCode}}). Prüfen Sie die Protokolle für Details."
- `service.restoreFailedZeroFilesNoOutput` → "Wiederherstellung fehlgeschlagen: 0 Dateien extrahiert (Exitcode {{exitCode}}). Keine Fehlerausgabe von Borg. Dateien existieren möglicherweise nicht im Archiv oder der Zugriff wurde verweigert."
- `service.restoreFailedZeroFilesPathNotFound` → "Wiederherstellung fehlgeschlagen: 0 Dateien extrahiert (Exitcode {{exitCode}}). Pfad nicht im Archiv gefunden oder Ziel existiert nicht."
- `service.restoreFailedZeroFilesPermission` → "Wiederherstellung fehlgeschlagen: 0 Dateien extrahiert (Exitcode {{exitCode}}). Zugriff verweigert - möglicherweise benötigen Sie Root-Zugriff oder einen anderen Zielpfad."

## Verification Results

```
es.json PASS: all 12 gap keys have real translations
de.json PASS: all 12 gap keys have real translations
PASS: Locale parity check PASSED. All 3 locale files share the same 2064 keys.
```

- `npm run check:locales` exits 0
- Key count unchanged at 2064 in all three locale files
- Zero English placeholder values remain in any backend.* key across es.json and de.json

## Requirements Satisfied

- **LOC-02:** ALL backend.* keys in es.json now have real Spanish translations — no English placeholders remain
- **LOC-03:** ALL backend.* keys in de.json now have real German translations — no English placeholders remain
- **LOC-04:** Key parity confirmed at 2064 keys across all three locale files
- **QUAL-02:** CI parity enforcement unchanged; `check:locales` still exits 0

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- FOUND: frontend/src/locales/es.json
- FOUND: frontend/src/locales/de.json
- FOUND commit: 735fe7b (Task 1 - Spanish translations)
- FOUND commit: 1a6c9f7 (Task 2 - German translations)
