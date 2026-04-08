# Borg UI Updates Worker

Cloudflare Worker for serving OTA manifests on `updates.borgui.com`.

Endpoints:

- `/announcements.json`
- `/plan-content.json`

The JSON source of truth stays in the main repo docs files:

- [`../docs/announcements.json`](../docs/announcements.json)
- [`../docs/plan-content.json`](../docs/plan-content.json)

## Local commands

```bash
cd updates-worker
npm install
npm run typecheck
npm run dev
```

## Deploy

```bash
cd updates-worker
npm run deploy:updates
```
