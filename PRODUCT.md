# Product

## Register

product

## Users

Homelabbers, sysadmins, and small-team operators who self-host BorgBackup to protect their own infrastructure. They are technical: comfortable with SSH, Docker, cron, and the borg CLI. Their context when opening Borg UI is operational, not exploratory; they are either setting up a new backup target, checking that last night's backups ran, restoring a file someone deleted, or chasing why a job failed at 3am. They run this on a home server, a NAS, or a small fleet, and they expect the UI to be the same dependable layer their backups are.

Two adjacent audiences read the same surface: (1) first-time homelabbers evaluating Borg UI against alternatives like Vorta, Borgmatic, and Pika Backup, who need the first ten minutes to feel survivable; (2) Pro / Enterprise customers managing more than a handful of repositories and remote machines, who need scale and reliability the open source baseline has earned.

## Product Purpose

Replace the borg CLI ceremony with a web interface that runs the same backups, browses the same archives, and exposes the same flags, without losing the precision that makes borg trustworthy. Specifically:

- Run, schedule, and monitor backups against local, SSH, SFTP, and cloud (rclone) destinations.
- Browse archives and restore individual files or whole trees without dropping to the shell.
- Manage repositories, remote machines, SSH keys, backup plans, retention/prune policies, and pre/post hooks.
- Operate fleets of managed agents that push to a central Borg UI instance.
- Notify through 100+ Apprise services so backup failures don't sit silently.

Success looks like the user trusting the dashboard more than they trust their own cron + email setup, and never reaching for `borg list` again because the UI shows everything the CLI would.

## Brand Personality

**Calm. Modern. Precise.**

Voice and tone:
- **Calm and reassuring**, because the product's domain is data loss recovery. The interface is the safe pair of hands, not a stress-amplifier when a job fails. Failure states are factual, not alarmist; recoveries are obvious, not buried.
- **Modern and polished**, because it sits alongside Plex, Linear, Tailscale, and Proxmox in the same homelab dashboard tab. It should not look like a 2014 admin panel or a Bootstrap demo. Density and rhythm earn the comparison; chrome and gradients don't.
- **Technical and precise**, because the user is technical and respects technical surfaces. Show real paths, real flags, real exit codes, real archive IDs. Don't paper over borg's vocabulary with consumer euphemisms.

Emotional goal: a user who has just realized they need to restore something from three weeks ago feels relieved within five seconds of opening the app.

## Anti-references

What this explicitly is NOT:

- **Legacy admin shells**: Webmin, Cockpit, cPanel, 2014-era Bootstrap dashboards. Dense without rhythm, decorative without restraint, every form a wall of unlabeled inputs.
- **Consumer SaaS marketing patterns inside the app**: hero metric cards with gradient accents and supporting stats; aspirational empty-state illustrations; emoji-led tooltips; verbs like "supercharge" or "unleash". Borg UI is operational, not aspirational.
- **Hidden borg vocabulary**: don't rename "archive" to "snapshot" to be friendlier. The user came here knowing borg. Speak the same language.
- **Heavy left-accent borders on cards, alerts, list items, and status surfaces** (already enforced in AGENTS.md). Borders should be balanced or full-outline, with emphasis carried by background tint, icons, chips, or typography.
- **Visual themes that read as "AI made that"**: cream / sand / beige body backgrounds, tiny tracked all-caps eyebrows above every section, numbered `01 · 02 · 03` scaffolding on sections that aren't actually sequences, gradient text, decorative glassmorphism. Borg UI's identity is light/dark + blue, evolved over time; don't drift into the saturated AI defaults.

## Design Principles

1. **Operational over aspirational.** This is a tool people open to do a thing. Every screen should answer "what's the state, and what can I do about it" before it tries to be beautiful. Beauty earns its place by serving that answer, not by replacing it.

2. **Respect the user's expertise.** Show real borg paths, flags, repo IDs, and exit codes. Don't gate the precise view behind an "advanced" toggle. Add explanation where borg's own UX is genuinely confusing (cache locks, repo encryption modes), not where the CLI is already clear.

3. **Calm under failure.** Backup software fails: SSH drops, disks fill, locks linger, repos diverge. Failure states are the most important screens in the app. They must be factual, scannable, and route the user to the next action. No red walls, no panicked copy.

4. **Composed from shared primitives.** Wizards, dialogs, SSH pickers, schedule controls, rich select rows all exist as shared components. New surfaces compose them; they don't reinvent them. This is both an engineering principle and a design principle: visual consistency comes from real component reuse, not from a written style guide.

5. **Self-hosted but not 2014.** The app must look current alongside Plex, Linear, Tailscale, Proxmox. Modern type rhythm, generous spacing, real motion where it earns its place, light/dark that actually works in both modes. The fact that it's self-hosted and AGPL is not a license to look dated.

## Accessibility & Inclusion

Target: **WCAG 2.1 AA** across all product surfaces.

Concrete commitments derived from that target:

- **Contrast**: body text ≥ 4.5:1 against its background; large text (≥18px or bold ≥14px) ≥ 3:1; placeholder text same 4.5:1, not the muted-gray default. Verify against both light and dark themes.
- **Keyboard**: every interactive element reachable via Tab; visible focus ring on every focusable element; no keyboard traps in dialogs and wizards.
- **Screen readers**: semantic landmarks (main, nav, header), labeled form controls, status updates announced via `aria-live` for backup progress and toast notifications.
- **Reduced motion**: every transition and reveal animation has a `@media (prefers-reduced-motion: reduce)` alternative (typically a crossfade or instant transition). Backup progress indicators degrade to text-only updates under reduced motion.
- **Color is never the only signal**: success / warning / danger states pair color with an icon, label, or shape so color-blind users get the same information.
- **Internationalization is a real constraint**: en/de/es/it are shipped today. Layouts must tolerate ~30% string-length growth without overflow, especially in wizard step labels, button text, and table headers.
