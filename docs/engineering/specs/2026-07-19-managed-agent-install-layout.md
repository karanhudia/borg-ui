# Managed Agent Installation Spec

Status: target picture. Supersedes parts of `2026-05-22-borg-installer-management.md`
regarding where a node's software comes from.

## Problem

`GET /agent/install.sh` installs a managed agent, and everything it needs comes
from somewhere outside the deployment:

1. **It requires internet access.** Not to the Borg UI server the agent enrolls
   against — to GitHub and PyPI. An air-gapped site cannot install an agent at
   all, however well its own network is provisioned.
2. **It installs build tooling on the host.** Borg 2 is compiled from source on
   the target machine, so `build-essential`, `python3-dev` and five `-dev`
   packages are installed — and never removed. A machine enrolled as a backup
   agent is left with a compiler it did not ask for.
3. **The agent code comes from a branch, not a release.** The installer runs
   `pip install git+https://github.com/…@main`. That is an external repository
   and a moving target, with three consequences: the agent need not match the
   server it talks to; two machines enrolled on different days within one
   release cycle need not match each other; and neither is visible to whoever
   installed them.
4. **Only Debian-family systems are supported.** The installer refuses anything
   else, although nothing about the agent itself is Debian-specific.

## Where things come from

The distinction that resolves most of this: the enrolling server should provide
what only it can provide, and everything else should come from where the site
already gets its software.

| Component | Source | Rationale |
| --- | --- | --- |
| Agent package | the enrolling server | Only that server knows which agent belongs to it. |
| Agent dependencies | the enrolling server | Six small wheels; without them a server-provided agent still cannot be installed offline. |
| Borg | the site's own channels, or the published binaries | Air-gapped sites mirror their distribution, and Borg is in it. |
| python3, curl | the distribution | Already mirrored; nothing to solve. |

A node then needs to reach exactly one host — the one it is enrolling against
anyway.

## Agent package and dependencies

The image builds the agent as a `py3-none-any` wheel and serves it. The agent is
pure Python, so there is nothing to compile for it on any platform, and its
dependency closure is six wheels totalling under 1 MB, each available in
universal (`py3-none-any`) form:

```
requests  urllib3  idna  certifi  charset_normalizer  websocket-client
```

Served alongside the agent wheel, the installer can use
`pip install --no-index --find-links <server>/agent/dist/ borg-ui-agent`, and the
installation becomes **air-gapped by construction**: no PyPI, no GitHub, one
host. It also settles problem 3 outright — the agent matches its server because
it comes from it, and two machines enrolled a week apart get the same agent as
long as the server has not changed.

`--agent-source git` remains available for development.

## Borg

Borg publishes no wheels on PyPI, only sdists, so any pip-based install compiles
on the target machine. It does publish static single-file binaries per release,
built against glibc, covering x86_64 and aarch64. That gives three sources, none
of which compiles anything:

- **`server`** — the static binary matching the version the server runs,
  verified against a checksum manifest kept in this repository. Exact version
  parity, but it fetches from the release URL, so it is an online default rather
  than an air-gapped one.
- **`distro`** — the distribution's package, which is what an air-gapped site's
  mirror provides. The version is then the distribution's: Ubuntu 24.04 ships
  Borg 1.2.8 where a server may run 1.4.4, but Alpine 3.24 ships 1.4.4 exactly,
  so this is not uniformly a downgrade.
- **`detect`** — use whatever is already installed, verify its major version,
  and report when it differs from the server's instead of proceeding silently.

Compiling Borg on the target stays possible but should not be a default: it
reintroduces exactly the toolchain that problem 2 is about. Where no static
binary exists — 32-bit ARM, musl — the installer should name the distribution
route rather than fail on a download that was never going to work.

### Keeping the manifest current

The `server` source is only as current as the checksum manifest it verifies
against, and the version parity it promises only holds while that manifest tracks
what the runtime base builds. The version is stated once, in the Dockerfile ARG,
and `refresh_borg_binary_manifest.py` derives the manifest from it; a `--latest`
mode asks GitHub which releases exist and, when a newer one publishes the Linux
binaries this installer needs, bumps the ARG and regenerates the manifest. A
weekly workflow runs that mode and opens a PR, so the pin drifts behind
borgbackup by at most a release rather than by however long nobody happened to
look.

Not every newer release is a safe adoption, and the changelog does not say which
are: borgbackup drops and adds published binaries silently — 1.4.5 stopped
shipping the glibc 2.31 x86_64 build, raising that floor to 2.35 with no release
note. So `--latest` measures the incoming binaries against the ones they replace,
per architecture, and reports any narrowing — an architecture that disappears, or
a glibc floor that rises past machines that were covered — in the PR title and a
warning in its body. It flags rather than blocks: the affected machines fall back
to `--borg-source distro`, so the regression is a decision for the reviewer, not
a reason to withhold the release.

That PR is deliberately incomplete. The version is also written into the string
tests on purpose — they are the checklist for adopting a version — and the
runtime-base image tag carries a manual revision, so the PR fails CI until a
human reconciles both. The workflow does the mechanical half and makes the
remaining half visible; it does not merge. This keeps the repository's pin
current, which is distinct from the non-goal of upgrading Borg on an
already-installed node.

## Platform support

Once the agent comes from the server and Borg has a distribution route, nothing
in the installation is Debian-specific except the package-manager invocations
and the service manager. Supporting further families is then a matter of
abstracting those two, not of new architecture — which is what makes problem 4
tractable rather than open-ended.

## Provisioning

An installed agent is not yet a working one. Before it backs anything up it
needs, on the server side: an enrolment, a registered repository, and a backup
plan; optionally a check schedule. Today the installer performs the enrolment
only, and the rest is manual work in the UI.

Given an administrator credential, the installer can do all of it, as a chain in
which each step is a precondition for the next:

1. obtain an administrator bearer token,
2. mint a one-time enrolment token and register the agent — or recognise that
   this machine is already enrolled, and re-enrol if the server no longer knows
   it,
3. register the repository this agent will use, together with its passphrase,
   which the server stores and hands back per job,
4. optionally set a check schedule (auxiliary — nothing depends on it),
5. optionally register a backup plan.

Every step has to be idempotent: re-running the installer on a provisioned
machine must converge rather than duplicate. A failure in the chain must abort
rather than leave a half-provisioned agent behind.

A personal access token is the right credential to ask for. A username and
password is a weaker fallback, because password login can be disabled
server-side (`oidc_disable_local_auth`), and it then fails for administrators
too.

## Interactive mode

The values this needs — server URL, agent name, repository URL and passphrase,
whether to register a plan — are exactly what an interactive installer can ask
for, which is friendlier than a command line of eight flags. Non-interactive use
must remain possible for automation: every prompt needs a corresponding flag,
and supplying the flag suppresses the prompt.

The passphrase is entered once and handed to the server, which is where
repository credentials already live. It is not written to the node.

## Open decisions

- **Who creates the Borg repository?** Registering it with Borg UI is not the
  same as it existing. Creating it during installation needs the passphrase and
  a reachable target at that moment, and moves a class of failure into the
  installer; requiring it to exist beforehand puts a manual step in front of
  installation.
- **How far does provisioning go by default?** Enrolment alone is defensible, and
  so is the full chain whenever an administrator token is supplied.
- **Whether the agent should carry a scoped credential of its own**, so that the
  installer never holds an administrator token, even transiently.

## Non-goals

Replacing an existing Borg binary; automatic Borg upgrades; macOS and Windows.
