# Automatic Database Scanning And Setup

## Problem

Backup-plan source setup is path-first. That works for files, but database users need help finding supported database stores and adding the pre/post plan hooks that keep a filesystem backup consistent.

## Scope

- Add a local database discovery endpoint that returns supported database candidates, their source paths, confidence, and editable stop/start hook templates.
- Add a source discovery panel to backup-plan source setup with databases available now and containers shown as a future source type.
- Add a guided responsive dialog that scans databases, lets the user review detected candidates or supported templates, edit generated scripts, and apply the result to the current backup plan.
- Applying a candidate adds the source path and creates pre/post plan scripts through the existing script library API.

## Supported Engines

- PostgreSQL
- MySQL / MariaDB
- MongoDB
- Redis

## Non-Goals

- Remote SSH database scanning.
- Docker container scanning implementation.
- Database credential collection or logical dump execution.
- Automatic editing of existing scripts.

## UX Notes

- Existing path-based local and remote source setup remains the primary baseline.
- Discovery is an additive assistant below the source location controls.
- The dialog uses the existing responsive dialog pattern, so it becomes a bottom sheet on mobile.
- Containers are visible as a disabled planned option to make the source model extensible without implying support.
