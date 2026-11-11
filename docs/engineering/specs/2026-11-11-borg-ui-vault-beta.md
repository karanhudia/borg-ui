# Borg UI Vault, closed beta

Status: design, awaiting owner approval
Date: 2026-11-11
Owner: Karan Hudia
Repos touched: `borg-ui` (the app), `borg-ui-license-platform` (Worker, storefront, admin, and the new storage node)

This spec is the single source of truth for the Vault beta. The four
implementation plans listed in section 15 argue from it. If a plan and this
spec disagree, the spec wins and the plan is wrong.

Writing rule for everything produced under this spec (code comments, UI copy,
emails, docs, commit messages): never use an em dash. Use a period, a comma or
parentheses.

## 1. What Vault is and why it exists

Vault is a Borg repository that Borg UI hosts for the customer. The customer
pays a yearly subscription, and Borg UI gets an offsite copy with no hostname,
username or key to copy by hand.

Why now: Pro features alone have sold about ten licences. Vault is the only
planned product that is recurring and that stacks on top of a licence. A
waitlist has been live at borgui.com/vault since 2026-10-28 and promises
specific things, which this beta must keep:

1. Encryption happens on the customer's machine. We store data we cannot read.
2. Access is Borg over SSH.
3. Data sits in an EU data centre.
4. Append-only access, so ransomware on the customer's server cannot destroy
   older backups.
5. Restore works from anywhere Borg runs, with or without Borg UI.
6. Waitlist members get 20% off their first year.

Success for the beta: up to ten invited waitlist members pay real money, connect
a Vault from inside Borg UI in under two minutes, and nobody is surprised by a
charge, a read-only switch or a deletion.

## 2. Goals, non-goals, anti-goals

### Goals

- G1. A storage node we own: one Linux host that gives each customer an
  isolated account with a hard size limit and append-only Borg access.
- G2. Paid yearly subscriptions through Paddle, the platform's first recurring
  product, with the whole lapse lifecycle automated.
- G3. An invite-only checkout on borgui.com for waitlist members.
- G4. A "Connect Vault" flow inside Borg UI: one dialog, no manual SSH setup.
- G5. A usage meter and clear status (active, payment failed, read-only,
  deletion date) inside Borg UI and in email.
- G6. A safe way to actually free space on an append-only Vault ("space
  release"), delayed by seven days with an email the owner can cancel from.
- G7. Everything testable without AWS or Hetzner: the node runs in Docker with
  the same image that runs in production.

### Non-goals (beta)

- Borg 2 repositories on Vault. Vault repositories are Borg 1 only.
- Public self-serve signup. Checkout needs a valid invite.
- Self-serve tier changes. The admin changes a tier by hand (section 9.6).
- More than one Vault per licence, or a Vault without a licence.
- More than one storage node, or automatic placement.
- The 2 TB and 5 TB tiers and "more than 5 TB". The code supports all four
  sizes; the beta only configures prices for 250 GB and 1 TB.
- Recording renewal payments as order rows. The first renewal is in November
  2027. State stays correct on renewal (section 7.4); revenue rows for
  renewals are a follow-up that must land before 2027-10-01.
- Analytics journey events for Vault. Beta numbers are read from the licence
  database.
- A Hetzner Storage Box backend. The node is a plain Linux host; moving it to
  Hetzner is a data copy and a DNS change (section 13).
- A second copy of customer data. The beta has one copy on one volume, and the
  checkout page and the welcome email say so.

### Anti-goals (would make this a failure even if it works)

- A customer loses data without three prior emails and seven days of final
  notice. Deletion must be impossible to trigger by a single bug (section 8.4).
- Any in-app nag. The Vault card appears only for installs whose licence owns
  a Vault. There is no promotion of Vault inside the app in this beta.
- A mixed-language journey. English, German, Spanish and Italian each cover
  the whole path (invite email, checkout, lifecycle emails, in-app strings).
- One tenant reading or writing another tenant's data.
- Raw AWS addresses in customer configuration. Customers only ever see
  `*.vault.borgui.com` names.

## 3. Decisions the owner made

These came from the owner in conversation on 2026-11-10 and 2026-11-11.

- D1. Build Vault next, as a paid product.
- D2. We run our own storage node. The beta runs on AWS in Frankfurt
  (eu-central-1) paid from USD 2000 of credits, then moves to Hetzner before
  the credits end.
- D3. Beta customers pay real money from day one, with the 20% waitlist
  discount on the first year.
- D4. Lapse timeline: payment fails, nothing changes for about two weeks while
  Paddle retries. Still unpaid, the Vault is read-only for 30 days (restores
  work, new backups do not). A final notice goes out 7 days before deletion,
  then data is deleted. Cancelling on purpose keeps the Vault until the paid
  year ends, then follows the same read-only and deletion steps. Going over
  the size limit fails new backups with a clear message; nothing is deleted
  and nothing is charged automatically.
- D5. Buying happens on the website, connecting happens in the app. One Vault
  per licence. One connect screen.
- D6. Prices (EUR, billed yearly, VAT not included), from
  `frontend/src/lib/vaultTiers.js` in the licence platform: storage 4, 9, 16,
  35 a month for 250 GB, 1 TB, 2 TB, 5 TB. Bought together with Vault, Lite
  costs 29 a year (list 49) and Pro 59 a year (list 79). Existing licence
  holders pay storage only.

## 4. Decisions made in this spec (my calls, owner may veto)

- C1. Tenant isolation is one Unix user per Vault plus a forced
  `borg serve --append-only --restrict-to-path <home>` command per SSH key.
  Size limits are XFS user quotas, enforced by the kernel. Verified in a
  throwaway container on 2026-11-11 (section 14).
- C2. "Read-only" is implemented by lowering the hard quota to current usage
  plus 64 MiB. Borg still needs to write lock files to read, so a truly
  read-only filesystem would break restores. Verified.
- C3. The hard quota is the sold size plus 5%. The app reports "full" at the
  sold size. The slack lets Borg finish bookkeeping writes.
- C4. The node is one Docker image that runs both in tests and in production,
  with all state on the data volume. The licence Worker cannot open SSH
  connections, so it drives the node over HTTPS.
- C5. The node lives in the licence platform repository under `vault-node/`.
  That repository is private; the app repository is public.
- C6. The app registers its existing system SSH key with the Vault. No new key
  type.
- C7. Bundle purchases (Vault plus Lite or Pro) are one Paddle subscription
  with two yearly items. The licence minted for a bundle renews with the
  subscription.
- C8. The "add to backup plan" checkbox from the mockup becomes a link on the
  success step that opens Backup Plans. Updating a plan from the dialog would
  need the full plan payload and is not worth the risk in a beta.
- C9. Space release (G6) is in scope because without it a full append-only
  Vault can never free space, and D4 tells the customer to "upgrade or prune".
- C10. Vault account state is independent of licence expiry. An expired (not
  revoked) licence key still authenticates Vault API calls, because the Vault
  is paid for separately.
- C11. All four languages for the full journey (section 12).
- C12. Deletion requires a recorded final notice at least 7 days old and no
  admin hold (section 8.4).

## 5. System overview

```
 Customer browser            Borg UI app (customer's server)
   | invite link                 | licence key + instance id
   v                             v
 borgui.com storefront  --->  license.borgui.com (Cloudflare Worker + D1)
   Paddle checkout               |  ^ Paddle webhooks
                                 |  | hourly cron
                                 v
                        node1.vault.borgui.com:443   (node API, bearer token)
                        <username>.vault.borgui.com:22 (customer Borg over SSH)
                                 ^
 Borg UI app  -------------------+  borg create / extract over SSH
```

Three components, three trust boundaries:

| Component | Where | Trusts | Is trusted by |
|---|---|---|---|
| Storage node | `borg-ui-license-platform/vault-node/` | the Worker (bearer token) | nobody else |
| Licence Worker | `borg-ui-license-platform/backend/` | Paddle (signed webhooks), admin token | node, storefront, app |
| Borg UI app | `borg-ui` | licence Worker over HTTPS | the customer |

Customer SSH keys are never trusted beyond their forced command. The app never
talks to the node API. The storefront never talks to the node API.

## 6. Storage node

### 6.1 Layout

Everything persistent lives on one XFS volume mounted with the `uquota` option
at `/srv/vault`.

```
/srv/vault/
  .node/state.json        desired state of every account (root only, 0600)
  .node/ssh/              sshd host keys (generated once, root only)
  <username>/             one home per Vault, owner <username>, mode 0700
     <repo-slug>/         Borg repositories the customer creates
```

`username` is the Vault id with the `vlt_` prefix replaced by `v`, for example
Vault `vlt_3fa9c01b22aa` has user `v3fa9c01b22aa`. It must match
`^v[0-9a-f]{12}$`. Any other value is rejected with 400 before anything
touches the system.

Unix uids start at 20000 and are stored in `state.json`, so quotas (which XFS
keeps per uid) survive a container rebuild. The container is stateless: on
start it recreates every user, key file and quota from `state.json`.

### 6.2 SSH access

- sshd listens on port 22 inside the container, host keys from
  `/srv/vault/.node/ssh/`.
- `AuthorizedKeysFile /etc/borg-vault/keys/%u`, root owned, mode 0644, one
  file per user, rewritten by the node agent. Customers cannot change it.
- `PasswordAuthentication no`, `PermitRootLogin no`,
  `AllowGroups vaultusers`. Every Vault user is in group `vaultusers`.
- Each key line is exactly:
  `command="borg serve --append-only --restrict-to-path /srv/vault/<username>",restrict <type> <base64>`
- Accounts get the shell `/bin/sh` (sshd needs a shell to run the forced
  command) and the password field `*` (a locked `!` password makes OpenSSH
  refuse the login when PAM is off).
- Public keys are validated against
  `^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(256|384|521)) [A-Za-z0-9+/]+={0,3}$`
  after the comment is stripped. Anything else is rejected with 400. This is
  the injection boundary for the authorized keys file.
- Borg on the node is Borg 1.4.x from the Debian trixie package, pinned by the
  image digest. Borg 2 is not installed.

### 6.3 Quotas and read-only

- Hard limit: `xfs_quota -x -c 'limit -u bhard=<N>k <username>' /srv/vault`.
- Usage for all users in one call: `xfs_quota -x -c 'report -u -b -N' /srv/vault`
  (columns: user, used KiB, soft, hard).
- Freeze (read-only) has two layers, both applied on `frozen: true`.
  1. Borg refuses the writes. Every key line of the account is written with
     `--storage-quota 10M` in the forced command:
     `command="borg serve --append-only --storage-quota 10M --restrict-to-path /srv/vault/<username>",restrict <type> <base64>`.
     Borg then rejects every new object, so `borg create`, `borg delete` and
     `borg prune` fail with "The storage quota (10.00 MB) has been exceeded",
     including a backup that adds no new data. `borg list`, `borg extract`
     and `borg check` keep working, and removing the flag makes writes work
     again. Verified on Borg 1.4.0. `10M` is the smallest value Borg accepts,
     so a repository that holds less than 10 MB is not stopped by this layer.
  2. No new repositories. The home directory, and every directory below it
     that is not a Borg repository and not inside one, is handed to root
     (`chown root:root`, mode `0755`), so the account can no longer create a
     directory anywhere a new repository could go. A repository is a
     directory that holds a file `config` and a directory `data`; the walk
     does not descend into it. Plain directories matter because Borg accepts
     nested paths such as `<home>/group/second`. All of this matters because `borg init` through a
     `borg serve` that carries `--storage-quota` writes that quota into the
     new repository's own config, where it would stay after the freeze ends
     and cap that repository at 10 MB for good. Existing repository
     directories still belong to the account, so Borg can take its locks and
     restores work. Verified on Borg 1.4.0: `borg init` fails, `borg list`,
     `borg extract` and `borg check` work.
  3. The quota backstop, for a small repository and for anything that is not
     Borg. On the first request with `frozen: true`, compute
     `frozen_limit_bytes = used_bytes + 64 MiB`, store it in `state.json`,
     and apply it as the hard limit. Later requests with `frozen: true` keep
     the stored value. The 64 MiB are room for Borg lock files and an index
     rebuild during a restore; they are not a write allowance, layer 1
     removes that.
  `frozen: false` writes the normal key lines again, gives those directories
  back to the account (mode `0700`), clears the stored value and applies
  `quota_bytes`.

  What a frozen Vault can still take, on purpose: a repository that existed
  before the freeze and holds less than 10 MB can grow until it reaches
  10 MB, and all of them together by at most 64 MiB. Closing that would mean
  filtering Borg's protocol or taking the segment directories away from the
  account, and the second breaks restores after an interrupted backup (Borg
  removes leftover segments when it opens the repository). The amounts are
  too small to matter for a lapsed account.
- A backup that hits the limit fails on the client with
  `OSError: [Errno 122] Disk quota exceeded`. The repository stays readable.
  Space held by the aborted transaction is reclaimed by the next successful
  write. Both verified.

### 6.4 Node API

HTTP on `0.0.0.0:8080` inside the container, published only through Caddy on
443 with a Let's Encrypt certificate for `node1.vault.borgui.com`. Every
request except `GET /healthz` needs `Authorization: Bearer <VAULT_NODE_TOKEN>`,
compared in constant time. Wrong or missing token: 401 with an empty body.

All responses are JSON. Sizes are bytes (integers).

Account object:

```json
{
  "username": "v3fa9c01b22aa",
  "uid": 20000,
  "quota_bytes": 1050000000000,
  "used_bytes": 312000000000,
  "frozen": false,
  "keys": 1,
  "compact": null,
  "ssh_host_key": "ssh-ed25519 AAAA..."
}
```

`compact` is null or
`{"state": "running" | "done" | "failed", "started_at": "...", "finished_at": "..." | null, "freed_bytes": 0, "error": "..." | null}`.

| Method and path | Body | Result |
|---|---|---|
| `GET /healthz` | | `200 {"ok": true}` |
| `PUT /v1/accounts/{username}` | `{"quota_bytes": int, "frozen": bool, "keys": ["<type> <base64>", ...]}` | `200` account object. Creates the account if missing. Idempotent: the body is the full desired state. `keys` may be empty. |
| `GET /v1/accounts` | | `200 {"accounts": [account, ...]}` |
| `GET /v1/accounts/{username}` | | `200` account object, or `404` |
| `DELETE /v1/accounts/{username}` | | `200 {"deleted": true}`. Removes the user, its key file, its quota and its home directory. Also `200` when the account does not exist. |
| `POST /v1/accounts/{username}/compact` | | `202` account object with `compact.state == "running"`. `409` if one is already running. |

Errors: `400 {"error": "<code>"}` with codes `invalid_username`,
`invalid_key`, `invalid_quota` (not an integer, below 1 GiB or above 10 TiB),
`too_many_keys` (more than 5); `404 {"error": "not_found"}`.

Compaction runs, for every direct child directory of the home that contains a
file named `config`, `runuser -u <username> -- borg compact <dir>`, one after
another, in a background thread. `freed_bytes` is usage before minus usage
after. If Borg cannot take the repository lock (a backup is running), the
state is `failed` with the Borg message and the caller retries later.

Compaction headroom: Borg writes the rewritten segments before it removes the
old ones, so a Vault that sits at its limit could never free space. While a
compaction runs, the account's hard limit is the limit it would otherwise
have plus `COMPACT_HEADROOM_BYTES = 4 GiB`. The normal limit is applied again
when the run ends, whatever the result, and by the start-up reconcile when
the container died in the middle of a run.

The headroom belongs to the whole account, so a backup that runs at the same
time can use it. That is accepted: a compaction that runs out of space fails
cleanly and is retried by the release logic (section 10), and an account that
ends above its restored limit loses nothing; its next backup fails with
"Disk quota exceeded" until space is released, the same as any Vault over its
limit.

### 6.5 Running it

- `vault-node/Dockerfile`: `debian:trixie-slim` plus `borgbackup`,
  `openssh-server`, `xfsprogs`, `python3`. Entry point `entrypoint.sh` starts
  sshd and the agent.
- `vault-node/docker-compose.yml` (production): services `node` (privileged,
  port 22, volume `/srv/vault` bound from the host) and `caddy` (port 443).
- `vault-node/docker-compose.dev.yml` (tests and local): sets
  `VAULT_DEV_LOOP_SIZE=1G`, which makes the entry point create a loop XFS
  image and mount it with `uquota` at `/srv/vault`, because a developer
  machine has no XFS volume. Agent on port 18080, SSH on port 10022.
- The agent is Python standard library only. No pip dependencies.

## 7. Billing

### 7.1 Paddle catalog (owner creates these in sandbox, then live)

One product "Borg UI Vault storage" with four yearly recurring EUR prices, and
one product "Borg UI plan with Vault" with two yearly recurring EUR prices.

| Worker variable | Meaning | Amount (EUR, yearly) |
|---|---|---|
| `PADDLE_VAULT_250GB_PRICE_ID` | storage 250 GB | 48 |
| `PADDLE_VAULT_1TB_PRICE_ID` | storage 1 TB | 108 |
| `PADDLE_VAULT_2TB_PRICE_ID` | storage 2 TB | 192 (leave empty in beta) |
| `PADDLE_VAULT_5TB_PRICE_ID` | storage 5 TB | 420 (leave empty in beta) |
| `PADDLE_VAULT_LITE_PRICE_ID` | Lite bought with Vault | 29 |
| `PADDLE_VAULT_PRO_PRICE_ID` | Pro bought with Vault | 59 |

A tier or plan whose price id is empty cannot be bought
(`400 tier_unavailable`).

Paddle dashboard settings the owner must set: payment recovery retries on,
final action "Cancel subscription". The API key needs permission to read and
write subscriptions, write discounts, and create customer portal sessions.

### 7.2 Tiers

| Tier id | Sold size (`quota_bytes`) | Hard limit sent to the node |
|---|---|---|
| `250gb` | 250 000 000 000 | 262 500 000 000 |
| `1tb` | 1 000 000 000 000 | 1 050 000 000 000 |
| `2tb` | 2 000 000 000 000 | 2 100 000 000 000 |
| `5tb` | 5 000 000 000 000 | 5 250 000 000 000 |

Hard limit = `floor(quota_bytes * 1.05)`.

### 7.3 Checkout

1. The admin invites a waitlist row (or any email) from the admin site. The
   Worker creates an invite (valid 14 days), mints a Paddle discount (20%,
   `recur: false`, `usage_limit: 1`, `restrict_to` all six Vault price ids,
   `expires_at` the invite expiry), and emails the invite link
   `https://borgui.com[/<lang>]/vault/join?invite=<token>`.
2. The join page loads the invite, shows the available tiers and the three
   plan choices (Lite, Pro, "I already have a licence"), and for the third
   choice asks for the licence key.
3. `POST /v1/vault/orders` validates everything again on the server, creates a
   pending row in the existing `orders` table, and returns the Paddle checkout
   payload: one item (storage) or two items (storage plus plan), the discount
   id, and `customData: {order_id, product: "vault"}`.
4. Paddle Checkout opens in the overlay. On success the browser goes to the
   existing success page, which now also shows "Your Vault is ready" steps.

Order row conventions: `orders.plan` is `lite` or `pro` for a bundle and the
literal `vault` for storage only. `orders.metadata_json` carries
`{"product": "vault", "tier": "...", "vault_plan": "lite" | "pro" | "licensed", "invite_id": "...", "license_id": "..." (licensed only), "lang": "..."}`.

### 7.4 Webhooks

The existing endpoint `POST /v1/payments/paddle/webhook` gains two branches,
both placed before the existing licence fulfilment logic.

Branch A, subscription events (`event_type` starts with `subscription.`):
apply the snapshot (section 8.2) and return 200. Unknown subscription ids are
logged and answered with 200. Paddle does not guarantee the order of
webhooks, so such an event can belong to a Vault that fulfilment has not
created yet. It is not lost: fulfilment step 6 reads the subscription's
current state from Paddle.

Branch B, `transaction.completed` whose order has
`metadata.product == "vault"`: run Vault fulfilment. `transaction.paid` is
ignored for Vault orders, because Paddle only guarantees `subscription_id` on
`transaction.completed`.

A third guard protects existing behaviour: any transaction whose `origin` is
not `web` (for example `subscription_recurring`) skips all order logic. A
completed renewal transaction moves `paid_through` forward and, for a bundle,
the licence expiry to `paid_through + 14 days`.

Vault fulfilment, every step idempotent, in this order:

1. Store the paid amount on the order (existing `updateOrderPaymentAmount`).
2. Bundle: call the existing `fulfillOrder` to mint one licence, using the
   bundle plan price id for the quantity check. Storage only: mark the order
   paid with a guarded update (`WHERE status = 'pending'`) and set
   `orders.license_id` to the customer's existing licence.
3. Insert the `vault_accounts` row (`INSERT OR IGNORE` on `order_id`) with
   `status = 'active'`, `paddle_subscription_id`, and `paid_through` from the
   transaction's `billing_period.ends_at`.
4. Bundle only: move the minted licence's `expires_at` to
   `paid_through + 14 days`.
5. Mark the invite redeemed.
6. Catch up on the subscription: `GET /subscriptions/{id}` and apply the
   result as a snapshot, with the subscription's `updated_at` as
   `sub_event_at`. This covers a `subscription.past_due` or a cancellation
   that arrived before the account existed. A successful read sets
   `sub_synced_at`, and the step runs whenever an account has a subscription
   id and no `sub_synced_at`. A Paddle failure does not fail the webhook:
   `sub_synced_at` stays empty and reconcile (8.5) tries again. The marker is
   separate from `sub_event_at` on purpose: an older webhook that arrives
   after a failed read must not make the read look done. Reconcile also
   repeats the read later (8.5), because a webhook can be lost for good.
   Skipped when no Paddle API key is configured.
7. Create the account on the node (`PUT`, no keys yet). A node failure does
   not fail the webhook: it records `node_error` and the hourly cron retries.
8. After the response (`waitUntil`): the existing licence email and admin
   notification for bundles, then the `vault_ready` email.

If any of steps 1 to 5 throws, the handler answers 500 so Paddle retries.

## 8. Vault lifecycle

### 8.1 Stored state (`vault_accounts`)

`status` is one of `active`, `past_due`, `read_only`, `deleted`. It is derived
(section 8.2) and stored for querying. The inputs are stored as they arrive
from Paddle:

- `sub_status`: Paddle's subscription status (`active`, `past_due`, `paused`,
  `canceled`, `trialing`).
- `paid_through`: end of the last paid billing period. Only a paid
  transaction moves it (first checkout or a `subscription_recurring`
  renewal), never a subscription event, because Paddle may roll the billing
  period forward before a renewal is paid. It is not an input of the rule
  below.
- `welcome_sent_at`: when the `vault_ready` email went out.
- `cancel_at`: effective date of a scheduled cancellation, or null.
- `past_due_since`: when the subscription first became `past_due`, cleared
  when it is `active` again.
- `sub_event_at`: `occurred_at` of the last applied event. Older events are
  ignored.
- `sub_synced_at`: when the subscription was last read from Paddle directly
  (7.4, fulfilment step 6, and 8.5). Empty means that read is still owed.
- `hold_until`: admin hold. Deletion never happens before this date.

### 8.2 Derivation (one pure function)

```
evaluateVault(account, now) -> { status, readOnlyAt, deleteAt, frozen, notices[] }

healthy  = sub_status in (active, trialing) and cancel_at is null
R (read-only starts):
  healthy                         -> null
  active with cancel_at           -> cancel_at
  any unhealthy status with a
  past_due_since                  -> past_due_since + 14 days
  canceled or paused, never
  past due                        -> canceled_at, else sub_event_at,
                                     else created_at (never "now")
D (deletion) = R + 30 days, or null when R is null
status = deleted   if deleted_at is set
         read_only if R is set and now >= R
         past_due  if sub_status == past_due
         active    otherwise
frozen = status == read_only
```

Constants: `PAST_DUE_GRACE_DAYS = 14`, `READ_ONLY_DAYS = 30`,
`FINAL_NOTICE_DAYS = 7`, `REMINDER_AFTER_DAYS = 15`.

When the result is healthy again, `notices_json` is reset to `{}` so a later
episode sends its emails again. A `recovered` email is sent only if
`payment_failed` or `read_only_start` had gone out.

### 8.3 Notices (each sent once per episode, recorded in `notices_json`)

| Key | When it is due |
|---|---|
| `payment_failed` | `sub_status == past_due` |
| `cancel_scheduled` | `cancel_at` is set and status is `active` |
| `read_only_start` | status is `read_only` |
| `read_only_reminder` | status is `read_only` and `now >= R + 15 days` |
| `final_notice` | status is `read_only` and `now >= D - 7 days` |
| `deleted` | after deletion |
| `recovered` | healthy again after any of the above |
| `renewal_offer` | status is `read_only`, `sub_status` is `canceled`, `final_notice` is recorded, and no email of this episode has carried a renewal link yet. The Worker records `renew_link` (a time) in `notices_json` whenever it sends a lapse email with a renewal link; that marker decides this, not `canceled_at`, because a cancellation can be applied long after it happened. The offer is the `final_notice` email in its renewal form, with a deletion date of at least 7 days from now. Without it a customer whose cancellation reaches us after the final notice would only ever have received dead payment links. |

Every lapse email states the read-only date and the deletion date as calendar
dates, and carries one button. While the subscription still exists
(`sub_status` is not `canceled`) it is "Update payment", a Paddle customer
portal URL fetched at send time. Once Paddle has cancelled the subscription
that link can no longer save the Vault, so the button is "Renew your Vault", a
renewal link (section 8.6), and the email text says the subscription has ended.

### 8.4 Deletion rule

The cron deletes a Vault only when all of these hold:

1. `now >= D`.
2. `notices_json.final_notice` exists and is at least 7 days old.
3. `hold_until` is null or in the past.
4. `status` is `read_only`.
5. When `sub_status` is `canceled`: `notices_json.renew_link` exists and is at
   least 7 days old. The customer has then had a working renewal link for a
   week.
6. The subscription was read from Paddle in this same cron run, right before
   deleting, and the account still meets rules 1 to 5 afterwards. If the read
   fails, deletion waits for the next run. A recovery whose webhook never
   arrived is caught here. Without a Paddle API key the Worker cannot make
   that read, so it never deletes a Vault.

Because of rule 2, a missed cron run or an email outage delays deletion
instead of skipping the warning.

Deletion starts with a claim, one conditional update that sets `deleted_at`
and `status = 'deleted'` only where the row is still not deleted, still has
the `sub_status` the rules were evaluated with, and has no hold in the
future. A renewal that attached in the meantime (8.6) or a renewal order
that just placed a hold makes the claim fail, and nothing is deleted. Once
the claim has succeeded no renewal can attach any more, because attaching
requires `deleted_at IS NULL`. Only then does the Worker call the node
`DELETE`, cancel the Paddle subscription if it is not already canceled, and
send the `deleted` email. If the node call fails, the account keeps
`node_error` and the cron repeats the node call on every run until it has
worked; the email goes out after that.

### 8.5 Reconcile (hourly cron and after every subscription event)

For each account that is not deleted:

1. Read the subscription from Paddle first (7.4, fulfilment step 6) when the
   account has a subscription id and the read is due: `sub_synced_at` is
   empty, or older than 24 hours, or older than 1 hour for an account that is
   not healthy. Paddle gives up on a webhook after about two days, so
   webhooks alone could leave a customer who paid in the read-only state.
   Then evaluate (8.2). Persist `status`, `read_only_at`, `delete_at`.
2. Sync the node when the desired state differs from the last synced state
   (`quota`, `frozen`, key list), or when `node_error` is set.
3. Send due notices.
4. Apply the deletion rule.
5. Drive space release (section 10).

The hourly cron first fetches `GET /v1/accounts` once and stores `used_bytes`
and `used_checked_at` on every account.

Cron expression: `17 * * * *`.

### 8.6 Renewal after the subscription was cancelled

Paddle cancels the subscription when its payment retries run out, and a
customer who cancelled on purpose has a cancelled subscription from the end of
the paid year. Both happen inside the read-only window, and Paddle cannot
bring a cancelled subscription back. A customer who wants to keep the Vault
therefore buys a new subscription, and the Worker attaches it to the Vault
that exists. Nothing on the node changes: same Vault id, same username, same
keys, same data.

- A renewal invite is a row in `vault_invites` with `renew_vault_id` set. It
  copies email, language and tier from the account, has no discount, and
  expires 30 days after it was created. What really ends it is the Vault:
  the invite stops working once the Vault is deleted or has a subscription
  again. (An expiry at `delete_at` would hand out dead links whenever a late
  final notice or an admin hold delays deletion.) Its plan is the licence's plan when the account is a bundle
  and that plan is `lite` or `pro` with a price id; otherwise `licensed`
  (storage only).
- It can only be created for an account that is not deleted and whose
  `sub_status` is `canceled` (`409 vault_deleted`, `409 subscription_active`).
- Who creates it: the Worker, each time it sends `read_only_start`,
  `read_only_reminder`, `final_notice` or `renewal_offer` for a cancelled
  subscription (the
  token is stored only as a hash, so each email gets a fresh invite), and the
  admin through `POST /v1/admin/vault/accounts/:vaultId/renewal`.
- The join page shows a renewal invite as "Renew your Vault": fixed size, no
  plan choice, no licence key field, no discount line.
- `POST /v1/vault/orders` with a renewal invite ignores the tier, plan and
  licence key in the request. It uses the invite's tier and plan and the
  account's licence, skips the `vault_exists` check, sends no discount, and
  adds `"renew_vault_id"` to the order metadata. It answers
  `409 vault_deleted` or `409 subscription_active` when the account changed in
  the meantime.
- Fulfilment of an order whose metadata has `renew_vault_id` does not create
  anything. It marks the order paid, then on the account sets the new
  `paddle_subscription_id`, `sub_status = 'active'`, `paid_through` from the
  transaction, clears `cancel_at`, `canceled_at`, `past_due_since`,
  `sub_event_at` and `sub_synced_at`, sets `bundle_license` to whether a plan item was bought,
  extends a bundle licence to `paid_through + 14 days`, marks the invite
  redeemed and reconciles. Reconcile unfreezes the node and sends
  `recovered`. Repeating the webhook changes nothing (the account already has
  that subscription id). No licence is minted and no `vault_ready` email goes
  out.
- A paid renewal must not lose to deletion. Creating a renewal order sets
  the Vault's `hold_until` to at least 96 hours from now, so a Vault is not
  deleted while a checkout for it is open or its webhook is on the way.
  A `transaction.paid` event for a renewal order sets the hold again, to 96
  hours from then, so the usual gap between "paid" and "completed" is
  covered too. Known remaining risk: the hold counts from the order and from
  the paid event, while Paddle's redelivery window counts from each delivery
  attempt. A customer who pays in the last hours of the hold, and whose paid
  and completed events are both delayed past it, can find the Vault deleted.
  That payment is surplus (below) and refunded, but the data is gone. Closing
  this would need the Paddle transaction id of every open renewal checkout
  and a lookup before each deletion; it is left out of the beta on purpose.
- Attaching is one conditional update (`... WHERE sub_status = 'canceled' AND
  deleted_at IS NULL`). Of two renewals paid for one Vault (two tabs, or two
  emails), exactly one wins it.
- A renewal that cannot attach, because it lost that update or because the
  Vault is gone, is surplus: its order is marked paid, its new subscription
  is cancelled immediately through the Paddle API (so it never bills again),
  and the admin is emailed to refund it. The cleanup does not depend on
  Paddle delivering the webhook again: the webhook first writes a row into
  `vault_surplus_renewals` (order id, Vault id, subscription id) and then
  tries both steps. Each step that worked is recorded on the row
  (`canceled_at`, `notified_at`), and the hourly cron repeats whatever is
  still missing for as long as it takes. A subscription that Paddle already
  reports as cancelled is not cancelled twice.
- A late event of the old subscription must not undo the renewal: a
  subscription event that matches an account only by order id is ignored when
  the account already has a different subscription id.


## 9. Licence Worker API

Base URL `https://license.borgui.com`. Error shape everywhere:
`{"error": {"code": "...", "message": "..."}}`.

### 9.1 Vault object (returned to the app)

```json
{
  "vault_id": "vlt_3fa9c01b22aa",
  "tier": "1tb",
  "quota_bytes": 1000000000000,
  "used_bytes": 312000000000,
  "used_checked_at": "2026-11-11T10:17:00.000Z",
  "status": "active",
  "paid_through": "2027-11-11T09:00:00.000Z",
  "cancel_at": null,
  "read_only_at": null,
  "delete_at": null,
  "host": "v3fa9c01b22aa.vault.borgui.com",
  "port": 22,
  "username": "v3fa9c01b22aa",
  "base_path": "/srv/vault/v3fa9c01b22aa",
  "host_key": "v3fa9c01b22aa.vault.borgui.com ssh-ed25519 AAAA...",
  "connected": true,
  "release": null
}
```

`connected` is true when this `instance_id` has a registered key. `release` is
null or `{"state": "scheduled" | "running" | "done" | "failed", "release_at": "..."}`.
`host_key` is one known_hosts line per key type, joined with `\n`.

### 9.2 App endpoints (credential: licence key plus instance id)

All take JSON `{"license_key": "...", "instance_id": "..."}` plus the listed
fields. The licence is looked up by key hash and must not be revoked; it may be
expired (C10). Rate limit: 60 requests an hour per IP, bucket `vault_ip`.
Failures: `400 license_invalid`, `429 vault_rate_limited`.

| Path | Extra fields | Result |
|---|---|---|
| `POST /v1/vault/status` | | `{"vault": <vault object> or null}` |
| `POST /v1/vault/keys` | `public_key`, `label` (optional, 64 chars) | Registers or replaces this instance's key, syncs the node now, returns `{"vault": ...}`. Errors: `404 vault_not_found`, `409 vault_deleted`, `400 invalid_key`, `409 too_many_keys` (5 per Vault), `502 node_unavailable`. |
| `POST /v1/vault/portal` | | `{"url": "<Paddle update payment URL>"}`. `404 vault_not_found`. |
| `POST /v1/vault/release` | | Schedules space release (section 10). Returns `{"vault": ...}`. `409 release_pending`, `409 vault_read_only`, `502 email_failed`. |
| `POST /v1/vault/release/cancel` | | Cancels a scheduled release. Returns `{"vault": ...}`. |

### 9.3 Storefront endpoints (public)

| Path | Body | Result |
|---|---|---|
| `GET /v1/vault/invites/:token` | | `{"email", "lang", "tier", "plan", "percent": 20, "renewal": false, "expiresAt", "tiers": [{"id", "available": bool}], "plans": {"lite": bool, "pro": bool, "licensed": true}}` or `404 invite_not_found` (unknown, used or expired). For a renewal invite (8.6): `"renewal": true`, `"percent": 0`, only the invite's tier is `available`, only the invite's plan is true in `plans`; `404 invite_not_found` when its Vault is deleted or its subscription is no longer cancelled. |
| `POST /v1/vault/orders` | `{"invite", "tier", "plan", "license_key"?}` | `{"orderId", "paddle": {"environment", "clientToken", "items": [{"priceId", "quantity": 1}], "discountId", "successUrl", "customData"}}`. Errors: `404 invite_not_found`, `400 tier_unavailable`, `400 plan_unavailable`, `400 license_key_required`, `400 license_invalid`, `409 vault_exists` (that licence already owns a Vault). Renewal invites: section 8.6, also `409 vault_deleted`, `409 subscription_active`; `discountId` is null. |
| `POST /v1/vault/release/cancel-link` | `{"token"}` | `{"result": "cancelled"}` or `404`. The link in the release email. |

The existing `GET /v1/storefront/orders/:orderId` adds
`"vault": {"tier": "...", "status": "..."}` or `null` to its summary.

### 9.4 Admin endpoints (existing admin bearer middleware)

| Path | Body | Result |
|---|---|---|
| `POST /v1/admin/vault/invites` | `{"signup_id"}` or `{"email", "tier", "plan", "lang"}` | Creates the invite, the discount and the email. Returns the invite without its token hash, plus `inviteUrl`. `409 invite_exists` when that signup already has an invite that is neither redeemed nor expired. Without a Paddle API key no discount is created. |
| `GET /v1/admin/vault/invites` | | list |
| `GET /v1/admin/vault/accounts` | | list of accounts with key count |
| `POST /v1/admin/vault/accounts/:vaultId/hold` | `{"until": "<ISO date>" or null}` | sets or clears `hold_until` |
| `POST /v1/admin/vault/accounts/:vaultId/tier` | `{"tier"}` | section 9.6 |
| `POST /v1/admin/vault/accounts/:vaultId/sync` | | forces a node sync and returns the account |
| `POST /v1/admin/vault/accounts/:vaultId/release` | | runs space release now, without the delay |
| `POST /v1/admin/vault/accounts/:vaultId/renewal` | | Creates a renewal invite (8.6) and returns `{"inviteUrl": "..."}`. Sends no email. `409 vault_deleted`, `409 subscription_active`. |
| `DELETE /v1/admin/vault/accounts/:vaultId/keys/:keyId` | | removes one key and syncs the node |

### 9.5 Worker configuration

New variables in `wrangler.toml` (both environments): the six price ids of
7.1, `VAULT_SSH_DOMAIN = "vault.borgui.com"`, `VAULT_SSH_PORT = "22"`,
`VAULT_NODE_URL` (for example `https://node1.vault.borgui.com`). New secret:
`VAULT_NODE_TOKEN`. When `VAULT_NODE_URL` or `VAULT_NODE_TOKEN` is empty,
every Vault endpoint except the waitlist answers `503 vault_disabled` and the
cron does nothing.

### 9.6 Tier change by the admin

`POST /v1/admin/vault/accounts/:vaultId/tier`: `PATCH` the Paddle subscription
with the full item list (the new storage price, plus the plan price if the
subscription has one) and `proration_billing_mode: "prorated_immediately"`,
then update `tier` and `quota_bytes` and sync the node. Downgrades are refused
with `409 usage_exceeds_tier` when `used_bytes` is above the new sold size.

## 10. Space release

Problem: with append-only access, `borg prune` and `borg delete` hide archives
but free nothing. Only a compaction that runs on the node without the
append-only flag frees space, and once it runs the pruned archives are gone
for good. An attacker who controls the customer's server can prune everything.

Rule: compaction never runs immediately on a customer request.

1. The customer clicks "Release space" in Borg UI. `POST /v1/vault/release`
   works in three steps.
   a. Store `release_state = 'pending'`, `release_requested_at = now` and
      the token hash. A pending release is never compacted, but it can be
      cancelled, so the cancel link works from the first second.
   b. Send the `release_scheduled` email with the date (now + 7 days) and the
      cancel link (`https://borgui.com/vault/release?cancel=<token>`).
   c. When the email provider accepted it, activate the release with one
      conditional update: set `release_state = 'scheduled'` and
      `release_at = now + 7 days` only where the row is still `pending` with
      the same token hash. If no row changed, the customer cancelled first
      and it stays cancelled. There is no read followed by a write, so a
      cancellation cannot slip in between.
   If the provider does not accept the email, the pending fields are cleared
   and the answer is `502 email_failed`. If the Worker stops after step a or
   b, the release stays `pending` and nothing is ever compacted; a pending
   release older than 10 minutes counts as none and a new request replaces
   it. Acceptance by the provider is not proof of delivery; the app also
   shows the scheduled release and a cancel button on the Vault card. The
   app sees a pending release as no release (`"release": null`).
2. Until `release_at`, the customer can cancel from the app or the email link.
3. At `release_at` the cron calls the node `compact`, sets
   `release_state = 'running'`, and on later runs reads the node's `compact`
   state. `done`: send `release_done` with the freed size, clear the release
   fields. `failed`: retry on the next run, up to 24 times, then set
   `release_state = 'failed'` and email the admin.
4. No release is scheduled while the status is `read_only` or `deleted`
   (`409 vault_read_only`).

What the customer is told (app, docs and the `release_done` email): "Space
release runs 7 days after you ask for it. For 7 more days after it has run,
our support can bring back what it removed. After that it is gone for good.
If you did not ask for a release, cancel it."

### 10.1 Retained copy (7 days after every compaction)

The delay protects against a release nobody asked for. It does not protect
archives pruned after a release the owner did ask for: someone who takes over
the customer's server on day 6 can prune everything, and the compaction on
day 7 would remove it. So nothing a compaction removes is gone at once.

- Before the node compacts a repository it takes a retained copy of it:
  `cp -r --reflink=always <repo> /srv/vault/.node/retained/<username>/<copy id>/<repo name>`,
  run as root while the account holds the repository lock (the agent starts
  `borg with-lock <repo> sh -c 'echo locked; read _'` as the account, waits
  for the line `locked`, copies, then closes the command's input). If the
  lock cannot be taken, that repository is not copied and not compacted, and
  the compaction counts as failed, as before. If the compaction itself fails
  after the copy, the copy is removed.
- Nothing may be written between the copy and the compaction, or the
  compaction could remove something the copy does not hold. Borg cannot keep
  one lock across both, so the node closes the door first: for the whole
  compaction run the account's key lines are the frozen ones (6.3, layer 1),
  which makes Borg refuse every write of a session that logs in from then
  on. A session that was already writing holds the repository lock, so the
  copy fails and nothing is compacted. The normal key lines come back when
  the run ends, in the same step that restores the limit. A backup that
  starts during a compaction therefore fails with Borg's storage quota
  message; it would have failed on the repository lock anyway. What is left
  is a session that logged in before the door closed and takes the lock in
  the instant between copy and compaction: it could add an archive and
  delete it again, and only that archive, seconds old, would be missing from
  the copy.
- The copy is a reflink copy: it shares its blocks with the repository, so
  taking it is fast and costs no space at first. It belongs to root and lives
  outside every home directory, so the account cannot reach or delete it and
  it does not count against the account's quota.
- Effect, verified on Borg 1.4.0 and XFS: after the compaction the account's
  usage drops at once (114 MiB to 57 MiB in the test), while the space on the
  disk is only really free when the copy is removed. The node therefore
  needs spare disk for up to 7 days of released space; the runbook watches
  free space.
- A copy is kept `RETAIN_DAYS = 7` days. Expired copies are removed when the
  agent starts and on every `GET /v1/accounts` (the Worker calls it hourly).
  Deleting an account removes its copies too. The account object gains
  `retained_until`: the latest expiry, or null.
- The file system must support reflinks (`reflink=1`, the default of
  `mkfs.xfs`). The agent checks this at start and refuses to run without it.
- Recovery is done by the admin on the node, on a customer's request:
  `python3 -m agent.recover <username> <repo name> [--as-of <UTC time>]`.
  It moves the live repository into the retained area (kept 7 days, so the
  step can be undone), puts a reflink copy of the retained copy in its place,
  owned by the account, and applies the account's limit again afterwards
  (the limit is lifted during the swap, because the recovered repository can
  be larger than the limit allows; the account is then over its limit until
  it releases space again, and loses nothing).
- `--as-of` is what brings pruned archives back. A retained copy still holds
  every segment, but its newest state already has the archives marked as
  deleted. Borg's append-only log (`transactions` in the repository) lists
  every transaction with its time. The tool keeps the last transaction at or
  before the given time, removes the segment files after it and the
  `index.*`, `hints.*` and `integrity.*` files (Borg rebuilds them), and
  removes copied lock files. Verified: an archive deleted before the
  compaction is listed, extracts and passes `borg check` afterwards. The
  admin cannot list archives (no passphrase), so the customer names a time
  at which the backups were still good.
- After a recovery the customer's Borg refuses the repository once with
  "Cache, or information obtained from the security directory is newer than
  repository", because the repository went back in time. That is Borg's
  rollback protection working. A fresh client works at once (verified); on
  the existing install the customer removes the repository's local cache and
  security info (`borg delete --cache-only <repo>`, per Borg's documentation)
  or removes the repository from Borg UI and adds it again.
- Limit that remains: recovery needs someone to notice within 7 days of the
  compaction, 14 days after the release was requested, and it needs the
  passphrase, which only the customer has.

## 11. Borg UI app

### 11.1 Backend

- Migration: add nullable `ssh_connections.vault_id` (string). Mirror it on
  the `SSHConnection` model.
- `app/services/vault_service.py`:
  - `async get_vault_status(db) -> dict`: returns
    `{"vault": ..., "connection_id": int | None, "repository_count": int, "reason": None | "no_license_key" | "service_unavailable"}`.
    Never raises for an unreachable licence service; it returns
    `vault: None, reason: "service_unavailable"`. `host_key` is removed from
    the vault object before returning.
  - `async connect_vault(db) -> dict`: ensures the system SSH key exists
    (generating an ed25519 one through the existing helpers if not), calls
    `/v1/vault/keys`, upserts the `SSHConnection` (host, username, port,
    `ssh_key_id`, `default_path = base_path`, `vault_id`), pins the host key
    from the licence service with the existing `pin_host_key`, runs the
    existing connection test, and returns
    `{"connection_id", "base_path", "vault": ...}`.
  - `async vault_portal_url(db)`, `async request_release(db)`,
    `async cancel_release(db)`.
- `app/api/vault.py`, prefix `/api/vault`, every route admin only:
  `GET /api/vault`, `POST /api/vault/connect`, `POST /api/vault/portal`,
  `POST /api/vault/release`, `POST /api/vault/release/cancel`. Each is added
  to `ROUTE_ACCESS_REGISTRY` as `admin`.
- Errors use the existing `_licensing_http_error` shape with codes
  `vault_status_failed`, `vault_connect_failed`, `vault_portal_failed`,
  `vault_release_failed`.

The repository itself is created by the existing `POST /api/repositories/`
with `connection_id`, so no Borg code changes.

### 11.2 Frontend

Location: `frontend/src/components/vault/`.

- `useVault.ts`: React Query hook, key `['vault']`, enabled for admins only,
  stale time 5 minutes.
- `VaultUsageMeter.tsx`: bar plus "312 GB of 1 TB used". Warning tone at 90%,
  error tone at 100%.
- `VaultStatusBanner.tsx`: nothing when active; otherwise one outlined, tinted
  banner (no left accent border) with the dates and an "Update payment"
  button.
- `VaultCard.tsx`: the card on the Repositories page, between the header and
  the repository groups. States: ready to connect, connected, past due,
  read-only, full, release scheduled.
- `ConnectVaultDialog.tsx`: built on `ResponsiveDialog`. Fields: repository
  name (default `vault-<hostname slug>`), passphrase, confirm passphrase. Three
  stages: form, working (connect, then create repository), done (with a button
  that opens Backup Plans).
- A "Vault" chip on repository rows whose path starts with
  `ssh://<username>@<host>`.

Repository payload sent after connect:
`{name, borg_version: 1, path: "<base_path>/<slug>", encryption: "repokey", compression: "lz4", passphrase, connection_id, mode: "full", executor_type: "server", execution_target: "ssh", storage_backend: "ssh"}`.
The slug is the name lowercased with every character outside `[a-z0-9-]`
replaced by `-`, runs of `-` collapsed, trimmed of `-`, at most 48 characters.

The card renders nothing when `vault` is null. There is no teaser.

### 11.3 Rules from `AGENTS.md` that apply

Use the `ui-ux-pro-max` skill before any UI decision or implementation. Every
new component gets a Storybook story covering each state. Use
`ResponsiveDialog`, never raw MUI `Dialog`. No heavy left accent borders. Do
not commit generated screenshots. Add every string to all four locale files
and run `npm run check:locales`. Do not bump versions.

## 12. Copy

English is the source. German, Spanish and Italian use the formal address
already used in `VAULT_CONFIRM_COPY` (`Sie`, `usted`, `Lei`). A test fails when
any language lacks any key.

Email kinds: `invite`, `vault_ready`, `payment_failed`, `cancel_scheduled`,
`read_only_start`, `read_only_reminder`, `final_notice`, `deleted`,
`recovered`, `release_scheduled`, `release_done`. English subjects:

| Kind | Subject |
|---|---|
| `invite` | Your Borg UI Vault invite |
| `vault_ready` | Your Borg UI Vault is ready |
| `payment_failed` | We could not renew your Borg UI Vault |
| `cancel_scheduled` | Your Borg UI Vault ends on {date} |
| `read_only_start` | Your Borg UI Vault is now read-only |
| `read_only_reminder` | Your Borg UI Vault will be deleted on {date} |
| `final_notice` | Final notice: your Borg UI Vault is deleted on {date} |
| `deleted` | Your Borg UI Vault has been deleted |
| `recovered` | Your Borg UI Vault is active again |
| `release_scheduled` | Space release on your Borg UI Vault is scheduled for {date} |
| `release_done` | Space released on your Borg UI Vault |

Body rules: say what happened, then the dates, then the one thing to do. No
exclamation marks, no "please", no "successfully". `vault_ready` must include
these two sentences: "Your backups are encrypted on your machine with a
passphrase only you have. We cannot read or recover them, so keep the
passphrase safe." and "During the beta your Vault is stored once, in one EU
data centre. Keep your local copy." The plans contain the full English text.

## 13. Operations

- AWS (beta): one EC2 instance in eu-central-1 (t4g.small is enough), Debian
  13, one EBS `sc1` volume formatted XFS and mounted with `uquota` at
  `/srv/vault`, an Elastic IP, security group open on 22 and 443 only. Admin
  access through SSM Session Manager, not through port 22.
- DNS at Cloudflare, proxy off (grey cloud): `*.vault.borgui.com A <Elastic IP>`
  and `node1.vault.borgui.com A <Elastic IP>`.
- Backups of the node itself: a daily EBS snapshot of the data volume, kept 7
  days, through AWS Data Lifecycle Manager. This protects against our own
  mistakes, not against a region outage.
- Cost guard: an AWS budget alert at USD 100 a month. Restore traffic costs
  about USD 0.09 per GB after the first 100 GB a month.
- Moving to Hetzner later: start the same compose file on the new host, stop
  customer SSH on the old one, `rsync -aHAX --numeric-ids` the volume
  (including `.node/`), start the node (it rebuilds users and quotas from
  `state.json`), point both DNS records at the new address. Customers change
  nothing because hostnames, host keys, usernames and paths stay the same.

The runbook with exact commands is plan 1, task 8.

## 14. What was verified on 2026-11-11

In a privileged `debian:bookworm` container with a loop XFS volume, Borg
1.2.4 and OpenSSH 9.2:

- A key with the forced command cannot get a shell (it gets Borg's usage
  text).
- A tenant cannot list or create a repository under another tenant's path
  ("Repository path not allowed").
- Two repositories in one home share one quota.
- Exceeding the quota fails the backup with
  `OSError: [Errno 122] Disk quota exceeded`, exit code 2; `borg list` and
  `borg extract` still work; the next small backup succeeds and usage drops
  back.
- Client `borg delete` plus client `borg compact` frees nothing under
  append-only.
- `borg compact` run on the node as the tenant user, without the key or
  passphrase, freed the space ("compaction freed about 62.92 MB").
- Freeze at usage plus 16 MiB: a 100 MB backup fails, list and extract work,
  raising the limit restores writes.

Not verified, and therefore gates:

- Gate A (plan 1): the same scenario on the real AWS host, where the XFS
  volume is mounted by the host and bound into the container.
- Gate B (plan 2): a real Paddle sandbox purchase with two recurring items in
  one checkout, and the exact webhook payloads. The docs confirm the field
  names used in this spec but do not state that two yearly prices can share a
  checkout.
- Gate C (plan 4): a real Borg UI install connecting to the real node.

Note: the ext4 quota format module is missing from stock Ubuntu cloud kernels
(it ships in `linux-modules-extra`). XFS quota is built in. That is why this
spec uses XFS.

## 15. Plans

Build order. Each plan produces something testable on its own.

1. `borg-ui-license-platform/docs/superpowers/plans/2026-11-11-vault-1-storage-node.md`
2. `borg-ui-license-platform/docs/superpowers/plans/2026-11-11-vault-2-worker.md`
   (needs plan 1 only for its end-to-end test)
3. `borg-ui-license-platform/docs/superpowers/plans/2026-11-11-vault-3-storefront-admin.md`
   (needs plan 2)
4. `borg-ui/docs/engineering/plans/2026-11-11-borg-ui-vault-app.md`
   (needs the API of plan 2; can be built against mocks in parallel)

Plans 1 and 4 can run in parallel with plan 2. Plan 3 follows plan 2.

## 16. Owner checklist (things only the owner can do)

1. Paddle sandbox: create the two products and six prices (7.1), set payment
   recovery to cancel, check the API key permissions.
2. AWS: create the host, volume, Elastic IP, budget alert and snapshot policy
   (plan 1, task 8).
3. Cloudflare DNS: the two records in section 13.
4. Secrets: `wrangler secret put VAULT_NODE_TOKEN --env production`, and the
   same token in the node's `.env`.
5. Run gates A, B and C.
6. Repeat step 1 in Paddle live, deploy, invite the first waitlist member.
7. Remove the sentence about planned prices from the Vault page once the first
   invite goes out, and drop the append-only claim if gate A fails.
8. Size the node's disk with room for retained copies (section 10.1): up to
   7 days of released space is still on disk.
9. In gate B, also let a sandbox subscription run into cancellation and buy
   the renewal link from the read-only email (8.6).
