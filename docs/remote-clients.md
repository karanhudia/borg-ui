---
title: Remote Clients
nav_order: 6
description: "Route this Borg UI server between local work and remote clients"
---

# Remote Clients

Remote Clients let one Borg UI server act as a gateway to another Borg UI
server. This is useful when you run Borg UI on several machines and want to
inspect or operate on a different machine without changing environment files or
opening another deployment URL.

Open Remote Clients from the Infrastructure navigation group. The global
server target control near the account menu shows whether requests are using
this server directly or routing through it to a registered remote client.

Remote Clients require an admin account and a Pro or Enterprise plan. Community
installations and non-admin users keep using this server locally, but cannot
add remote clients or route requests to a remote Borg UI server.

Saved remote clients are stored in the Borg UI database so admins can use the
same saved list from another browser or device after signing in. Authentication
tokens remain browser-local and are stored separately for each server target.

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

Use **Check** on a remote client before switching. The current Borg UI server
checks:

- the remote web health endpoint
- the remote `/api/system/info` endpoint
- the remote Borg UI version reported by that server

The client row shows online, offline, unknown, or incompatible status, the last
check time, and the reported Borg UI version. Incompatible clients cannot be
selected because frontend and server API contracts may differ.

## Switch Targets

Use **Use** on this server or on a compatible remote client, or open the server
target control near the account menu and select a target. After switching, the
browser still talks to the current Borg UI server. That server forwards selected
API requests to the remote client's API base, so the remote client only needs to
be reachable from the current Borg UI server. This server remains available as
the local fallback in the same control.

Authentication tokens are stored per server target in the browser. The current
server token authenticates the gateway request; the selected remote token is
forwarded only to that remote client. If the remote client requires login, Borg
UI sends you through that server's normal login flow without replacing this
server's token. Non-admin users cannot switch to saved remote clients, even if
the browser still has an old remote target reference.

## DNS and Reverse Proxy Notes

For public or shared deployments, give each Borg UI machine a stable HTTPS
origin such as `https://nas.example.com`. Configure the reverse proxy on that
machine so the API path is reachable from the Borg UI server that will register
it:

```text
https://nas.example.com/
https://nas.example.com/api/
```

Forward `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and
`X-Forwarded-For` as described in the [Reverse Proxy](reverse-proxy) guide. If
the deployment uses a sub-path, include that sub-path when registering the
remote client URL.
