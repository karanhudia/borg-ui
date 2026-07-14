# Fix OIDC Exchange 403 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for the code change and superpowers:verification-before-completion before claiming completion.

**Goal:** Allow a valid OIDC post-callback exchange to complete when Borg UI is served behind a TLS-terminating reverse proxy that forwards the public host to an HTTP backend.

**Architecture:** Keep the exchange endpoint's CSRF guard, but compare the request `Origin` or `Referer` against a small set of acceptable origins for the same browser-facing host. The only new accepted fallback is the HTTPS origin for the same host when the backend currently infers an HTTP origin, which covers common reverse-proxy TLS termination without trusting arbitrary forwarded hosts.

**Tech Stack:** FastAPI, SQLAlchemy test fixtures, pytest.

---

### Task 1: Regression Test

**Files:**
- Modify: `tests/unit/test_api_auth.py`

- [x] **Step 1: Add a failing reverse-proxy origin test**

Add this test next to the existing OIDC exchange origin tests:

```python
def test_oidc_exchange_accepts_https_origin_for_http_backend_host(
    self, test_client: TestClient, test_db
):
    test_db.add(
        SystemSettings(
            oidc_enabled=True,
            oidc_discovery_url="https://id.example.com/.well-known/openid-configuration",
            oidc_client_id="borg-ui",
            oidc_client_secret_encrypted=encrypt_secret("secret-value"),
        )
    )
    test_db.commit()

    create_test_oidc_exchange_grant(test_db)
    test_client.cookies.set("oidc_exchange_grant", "grant-123")

    response = test_client.post(
        "/api/auth/oidc/exchange", headers={"Origin": "https://testserver"}
    )

    assert response.status_code == 200
    assert response.json()["access_token"]
```

- [x] **Step 2: Verify RED**

Run:

```bash
pytest -q tests/unit/test_api_auth.py::TestOidcAuthentication::test_oidc_exchange_accepts_https_origin_for_http_backend_host
```

Expected before implementation: `403 != 200`, proving the current same-host HTTPS reverse-proxy origin is rejected before grant consumption.

### Task 2: Same-Host HTTPS Origin Guard

**Files:**
- Modify: `app/api/auth.py`

- [x] **Step 1: Add an origin extraction helper**

Add a helper near `_is_same_origin_request`:

```python
def _origin_from_url(value: str) -> Optional[str]:
    parsed = urlparse(value.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
```

- [x] **Step 2: Add accepted origin candidates**

Add a helper that keeps the existing expected origin and adds only the HTTPS upgrade for the same host when the backend sees HTTP:

```python
def _same_origin_candidates(request: Request) -> set[str]:
    expected_origin = build_external_base_url(request).rstrip("/")
    candidates = {expected_origin}
    parsed_expected = urlparse(expected_origin)
    if parsed_expected.scheme == "http" and parsed_expected.netloc:
        candidates.add(f"https://{parsed_expected.netloc}".rstrip("/"))
    return candidates
```

- [x] **Step 3: Update `_is_same_origin_request`**

Change `_is_same_origin_request` to parse the received origin and compare it to each candidate with `hmac.compare_digest`:

```python
def _is_same_origin_request(request: Request) -> bool:
    header_value = request.headers.get("origin") or request.headers.get("referer")
    if not header_value:
        return False

    received_origin = _origin_from_url(header_value)
    if received_origin is None:
        return False

    return any(
        hmac.compare_digest(received_origin, expected_origin)
        for expected_origin in _same_origin_candidates(request)
    )
```

### Task 3: Validate Behavior

**Files:**
- Test: `tests/unit/test_api_auth.py`

- [x] **Step 1: Verify GREEN for the new regression**

Run:

```bash
pytest -q tests/unit/test_api_auth.py::TestOidcAuthentication::test_oidc_exchange_accepts_https_origin_for_http_backend_host
```

Expected: PASS.

- [x] **Step 2: Verify unchanged rejection behavior**

Run:

```bash
pytest -q tests/unit/test_api_auth.py::TestOidcAuthentication::test_oidc_exchange_requires_same_origin_request tests/unit/test_api_auth.py::TestOidcAuthentication::test_oidc_exchange_grant_is_single_use
```

Expected: PASS, proving missing origin is still rejected and stale/consumed grants remain invalid.

- [x] **Step 3: Run required backend checks**

Run:

```bash
ruff check app tests
ruff format --check app tests
pytest -q tests/unit/test_api_auth.py::TestOidcAuthentication
```

Expected: all commands pass.
