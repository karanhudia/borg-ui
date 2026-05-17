# Borg Check Extra Flags Spec

## Goal

Allow advanced users to pass additional Borg `check` flags from the repository check dialog, scheduled check configuration, and backup plan maintenance checks without adding one UI control per Borg option.

## Context

Current Borg UI check flows only carry `max_duration`. The backend then adds `--repository-only --max-duration <seconds>` when a duration is set and runs `borg check --progress --log-json` for Borg 1 or the Borg 2 equivalent. There is no check-specific flag field in the API, database models, scheduled checks, backup plans, or repository check dialog.

Official Borg check options vary by Borg version. Borg 1.4 documents options including `--repository-only`, `--archives-only`, `--verify-data`, `--repair`, `--save-space`, and archive filters. Borg 2.0 beta documents similar options plus Borg 2-specific archive matching and `--find-lost-archives`. A single advanced text field is the least brittle way to support these options.

## Design

Add a nullable `check_extra_flags` string wherever a check can be configured or launched:

- `repositories.check_extra_flags` stores the scheduled check default for a repository.
- `backup_plans.check_extra_flags` stores the plan-level post-backup check flags.
- `check_jobs.extra_flags` captures the exact flags used by a manual, scheduled, or plan-triggered check job.

The API accepts and returns the same `check_extra_flags` field for manual repository checks, Borg 2 manual checks, check schedules, and backup plans. Values are trimmed before persistence. Empty strings become `None` for persisted schedule/plan defaults and are omitted from command execution.

Command execution parses the text with `shlex.split` and appends the parsed arguments to the subprocess argument list before the repository target. No shell execution is introduced. If parsing fails, Borg UI logs the parse error and skips the extra flags, matching the existing backup custom flag behavior.

## UI

Use Borg UI's current advanced-options language:

- Repository check dialog: add a labeled optional text field under max duration.
- Scheduled check dialog: add a labeled optional text field under max duration and prefill from existing schedule data.
- Backup plan schedule/maintenance step: when "Run check after successful repository backups" is enabled, add the same optional field under max duration.
- Review surfaces display the configured flags as compact code text where relevant.

The UI stays restrained: standard MUI `TextField`, helper text, no heavy left accent borders, no decorative visual treatment, and no placeholder-only labeling.

## Validation

Backend validation covers:

- manual repository check creates a `CheckJob` with `extra_flags`;
- Borg 2 check route creates a `CheckJob` with `extra_flags`;
- scheduled check update/get persists and returns `check_extra_flags`;
- scheduled check dispatch copies repository `check_extra_flags` into the job;
- backup plan create/update serializes `check_extra_flags`;
- backup plan maintenance jobs copy plan `check_extra_flags` into the check job;
- Borg 1 and Borg 2 check services parse and append extra flags to the command.

Frontend validation covers:

- `BorgApiClient.checkRepository` forwards `check_extra_flags` for Borg 1 and Borg 2 routes;
- scheduled check UI submits `check_extra_flags`;
- backup plan payload includes trimmed `check_extra_flags`;
- Storybook shows the manual check advanced flags state and snapshots are regenerated.
