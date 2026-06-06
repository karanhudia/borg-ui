---
title: Remote Clients
nav_order: 6
description: "Switch this browser between this Borg UI server and remote clients"
---

# Remote Clients

Remote Clients let one Borg UI browser session use another Borg UI server. This is
useful when you run Borg UI on several machines and want one browser session to
inspect or operate on a different machine without changing environment files or
opening another deployment URL.

Open Remote Clients from the Infrastructure navigation group. The global
server target control near the account menu shows whether the browser is using
this server or a registered remote client.

## Add a Remote Client

In Remote Clients, choose **Add remote client** and enter:

- client name: a short label such as `Studio NAS`
- server URL: the Borg UI URL for the other machine

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
- the remote Borg UI version reported by that server

The client row shows online, offline, unknown, or incompatible status, the last
check time, and the reported Borg UI version. Incompatible clients cannot be
selected because frontend and server API contracts may differ.

## Switch Targets

Use **Use** on this server or on a compatible remote client, or open the server
target control near the account menu and select a target. After switching,
frontend API requests use that server's API base. This server remains available
as the local fallback in the same control.

Authentication tokens are stored per server target in the browser. If the
remote client requires login, Borg UI sends you through that server's normal
login flow without replacing this server's token.

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
