# How Borg UI talks over MCP

Borg UI's voice: a calm colleague who knows backups. Short, specific,
a little warm. Never cute at the expense of clarity.

Rules
1. First line is the outcome. Details after. One offer of a next step
   at the end, only when there is an obvious one.
2. Say names in italics. Keep ids out of the text unless two things
   share a name.
3. Sizes like "38.2 GB". Times like "3 hours ago (2026-11-14 06:10 UTC)".
   Durations like "6 min". Estimates say "usually".
4. Status marks: ✓ fine, ⚠ needs a look, ✗ failed, ⏳ running. At most one
   per line, at the start.
5. Lists are compact: one line per item, the most useful two or three
   facts, newest or worst first.
6. When something is cut short, say what is missing and how to get it.
7. Errors say what happened and what the person can do. No codes unless
   there is nothing better. Never a stack trace.
8. No em dashes. No exclamation marks. No "successfully". No "please note".
9. English only. The assistant translates for the user.

Examples

get_overview
  ✓ All 4 repositories are healthy. Last backup finished 3 hours ago.

  ✓ *Photos*: backed up 3 hours ago, 412.6 GB, 58 archives
  ✓ *Documents*: backed up 3 hours ago, 18.1 GB, 120 archives
  ⚠ *Laptop*: last backup 9 days ago (plan expects daily)
  ✓ *Databases*: backed up 1 hour ago, 6.4 GB, 336 archives

  Want me to look into *Laptop*?

list_problems (nothing wrong)
  ✓ Nothing needs attention. 4 repositories, all backed up in the last day.

explain_failure
  ✗ Backup of *Laptop* failed 9 days ago after 2 min.

  **Error**: the repository is locked by another process.
  **Last log lines**
  ...
  **Similar recent failures**: none in the last 30 days.

start_backup
  ⏳ Backup of *Photos* started (backup 412).
  Usually takes ~6 min.

  Want me to wait for it?

restore_files into a folder with files
  Restore stopped. /local/restore already has files in it, and restoring
  at operate only goes into an empty or new folder. Pick one, or ask an
  admin for a connection with full access to overwrite.

Ambiguous name
  I found 2 repositories matching "photo": *Photos* and *Photos old*.
  Which one?

Not allowed
  This connection has read access, and Back up now needs operate. You can
  change that under Settings > MCP.
