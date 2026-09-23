from typing import Optional
from urllib.parse import urlsplit


def safe_url(url: Optional[str]) -> Optional[str]:
    """A URL for logs: the credentials replaced by `***`.

    `user:secret@host` becomes `user:***@host`. A userinfo without a
    password is masked whole (`token@host` becomes `***@host`): a REST
    store takes it as the Basic-auth credential, so it is the secret.

    Never raises and never keeps a credential fragment: this runs while a
    failure is being logged. The userinfo is cut at the last `@` (a
    password may contain `@`), the host:port text is kept as written
    without validating the port, and a URL that does not even parse
    becomes a fixed placeholder rather than its own text."""
    if not url:
        return url
    try:
        parts = urlsplit(url)
        if parts.username is None and not parts.password:
            return url
        userinfo, _, hostport = parts.netloc.rpartition("@")
        if parts.password:
            redacted = f"{userinfo.split(':', 1)[0]}:***"
        else:
            redacted = "***"
        return parts._replace(netloc=f"{redacted}@{hostport}").geturl()
    except ValueError:
        return "<unparseable url>"
