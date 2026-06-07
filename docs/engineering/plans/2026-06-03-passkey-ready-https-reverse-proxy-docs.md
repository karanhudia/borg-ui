# Passkey-Ready HTTPS Reverse Proxy Docs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Borg UI's deployment docs explicit that production passkeys require a stable HTTPS origin and proxy-owned TLS automation.

**Architecture:** Keep this as a docs-only change. Update the authentication page for the passkey requirement, and update the reverse-proxy page for the deployer stance, examples, and certificate-tooling ownership.

**Tech Stack:** Markdown, VitePress docs build.

---

## Task 1: User-Facing Documentation

**Files:**
- Modify: `docs/authentication.md`
- Modify: `docs/reverse-proxy.md`

- [x] **Step 1: Update passkey requirements**

  In `docs/authentication.md`, make the passkey requirements state that non-localhost deployments require HTTPS and that passkeys are bound to the stable public origin.

- [x] **Step 2: Add passkey-ready reverse proxy guidance**

  In `docs/reverse-proxy.md`, add guidance covering same-origin frontend/API access, `PUBLIC_BASE_URL`, forwarded headers, and `TRUSTED_PROXIES`.

- [x] **Step 3: Clarify TLS ownership**

  In `docs/reverse-proxy.md`, document reverse-proxy or orchestrator TLS termination as the supported production path. State that Borg UI does not manage TLS private keys, certificate issuance, or renewal inside the app process.

- [x] **Step 4: Update proxy examples**

  In `docs/reverse-proxy.md`, make Caddy and Traefik examples explicitly present automatic Let's Encrypt as the low-friction option, and make NGINX guidance explain that HTTP challenge, Cloudflare DNS challenge, and other DNS providers belong to the user's proxy/certificate tooling.

## Task 2: Validation And Handoff

**Files:**
- Verify: `docs/authentication.md`
- Verify: `docs/reverse-proxy.md`

- [x] **Step 1: Run whitespace validation**

  Run:

  ```bash
  git diff --check
  ```

- [x] **Step 2: Run docs rendering validation**

  Run:

  ```bash
  cd docs && npm run build
  ```

- [x] **Step 3: Run targeted content review**

  Run:

  ```bash
  rg -n "passkey registration and login must happen from HTTPS|Passkey registration and login require a stable HTTPS|PUBLIC_BASE_URL|TRUSTED_PROXIES|Let's Encrypt|Cloudflare DNS challenge|certificate" docs/authentication.md docs/reverse-proxy.md
  ```

- [ ] **Step 4: Publish**

  Commit with the commit skill, push with the push skill, create or update the PR using the repository template, attach it to BOR-130, add the `symphony` PR label, sweep PR feedback/checks, update the Linear workpad, and move the issue to Human Review only after validation and checks pass.
