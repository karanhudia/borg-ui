# Automatic Database Scanning And Setup Plan

## Plan

1. Add backend source discovery primitives:
   - Service model for source types, database candidates, and generated script templates.
   - Local scanner based on running processes and common data paths.
   - Authenticated API endpoint for admin/operator users.
2. Add focused backend tests:
   - Process-based detection extracts source paths and service names.
   - API returns source type metadata, detected databases, and supported templates.
3. Add frontend API types and UI:
   - Source discovery panel in backup-plan source setup.
   - Database discovery dialog with detected databases and template fallback.
   - Editable pre/post scripts and apply action that creates scripts and updates plan state.
4. Add focused frontend tests:
   - Scan entry point renders alongside existing path setup.
   - Applying a database creates scripts and updates source directories/script IDs.
5. Validate:
   - Targeted backend and frontend tests.
   - Required backend checks.
   - Required frontend locale, typecheck, lint, and build checks.
   - Runtime walkthrough of the backup-plan source setup path.
