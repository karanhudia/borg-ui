---
title: Remote Clients
nav_order: 6
description: "Switch this browser between local and remote Borg UI backends"
---

# Remote Clients

Remote Clients let one Borg UI frontend use another Borg UI backend. This is
useful when you run Borg UI on several machines and want one browser session to
inspect or operate on a different machine without changing environment files or
opening another deployment URL.

Open Remote Clients from the Infrastructure navigation group. The global
backend target control near the account menu shows whether the browser is using
the local backend or a registered remote backend.

## Add a Remote Client

In Remote Clients, choose **Add remote client** and enter:

- client name: a short label such as `Studio NAS`
- backend URL: the Borg UI URL for the other machine

The URL can be a DNS name, LAN IP address, localhost URL, HTTPS deployment, or
an explicit `/api` path. Borg UI normalizes browser URLs to the matching API
base. For example:

| Entered URL | Stored API target |
| --- | --- |
| `https://nas.example.com` | `https://nas.example.com/api` |
| `https://nas.example.com/api` | `https://nas.example.com/api` |
| `192.168.1.42:8081` | `http://192.168.1.42:8081/api` |
| `http://localhost:8081` | `http://localhost:8081/api` |

Use HTTPS for production DNS deployments. Localhost and LAN URLs are supported
for trusted local networks and development.

## Health and Version Checks

Use **Check** on a remote client before switching. Borg UI checks:

- the remote web health endpoint
- the remote `/api/system/info` endpoint
- the remote Borg UI version reported by that backend

The client row shows online, offline, unknown, or incompatible status, the last
check time, and the reported Borg UI version. Incompatible backends cannot be
selected because frontend and backend API contracts may differ.

## Switch Targets

Use **Use** on a compatible remote client, or open the backend target control
near the account menu and select a target. After switching, frontend API
requests use that backend's API base. The local backend remains available as the
fallback target in the same control.

Authentication tokens are stored per backend target in the browser. If the
remote backend requires login, Borg UI sends you through that backend's normal
login flow without replacing the local backend token.

## DNS and Reverse Proxy Notes

For public or shared deployments, give each Borg UI machine a stable HTTPS
origin such as `https://nas.example.com`. Configure the reverse proxy on that
machine so the frontend origin and API paths stay together:

```text
https://nas.example.com/
https://nas.example.com/api/
```

Forward `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and
`X-Forwarded-For` as described in the [Reverse Proxy](reverse-proxy) guide. If
the deployment uses a sub-path, include that sub-path when registering the
remote client URL.
