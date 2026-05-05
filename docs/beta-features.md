# Beta Features

Beta features are admin-controlled switches under Settings > Advanced > Beta.

They are off by default. Enable them only when you need the behavior and are prepared to turn it off again.

## Current Beta Switches

| Setting | What it does | When to use it |
| --- | --- | --- |
| Bypass locks for info commands | Adds `--bypass-lock` to Borg `info` commands | When read-only info calls hit lock contention |
| Bypass locks for list commands | Adds `--bypass-lock` to Borg `list` commands | When archive/file listing hits lock contention |
| Fast Borg 2 archive browse | Uses a faster Borg 2 browsing mode with smaller payloads | Very large Borg 2 archives |
| MQTT integration | Shows MQTT settings and enables MQTT runtime configuration | Home Assistant or MQTT monitoring tests |

## Lock Bypass Warnings

Bypass-lock is for read-only operations. It can help when Borg UI is only trying to inspect a repository but another operation holds a lock.

Do not use bypass-lock as a fix for unsafe concurrent writes. If a backup, prune, compact, restore, or external Borg process is running, wait for it to finish.

## Borg 2 Fast Browse

Fast Borg 2 archive browsing reduces payload size and can make large archives more responsive.

Tradeoff: recursive folder sizes may be unavailable in this mode.

## MQTT Integration

When the MQTT beta flag is enabled, MQTT settings appear in Settings > System > MQTT.

The runtime supports broker URL, port, username/password, client ID, QoS, retained messages, and TLS certificate paths.

MQTT is still treated as beta. Validate topics and payloads against your own broker before relying on it for alerting.

## Reporting Issues

When reporting beta issues, include:

- Borg UI version
- which beta switch is enabled
- Borg version
- repository type
- relevant job logs
