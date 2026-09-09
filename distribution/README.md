# Distribution

Packaging for platforms that install Borg UI from a catalogue rather than a
Compose file. Each directory holds the file the platform consumes, at the path
the platform fetches it from, so keep the paths stable.

| Directory | Platform | Consumed at |
| --- | --- | --- |
| `unraid/` | Unraid Community Applications | `https://raw.githubusercontent.com/karanhudia/borg-ui/main/distribution/unraid/borg-ui.xml` |
| `portainer/` | Portainer App Templates (v3) | `https://raw.githubusercontent.com/karanhudia/borg-ui/main/distribution/portainer/templates.json` |

Defaults are the same as the Compose files in [docs/installation.md](../docs/installation.md):
non-privileged container, `REDIS_HOST=disabled` unless a Redis is supplied,
FUSE opt-in. When an environment variable is renamed in the app, update these
files in the same PR.
