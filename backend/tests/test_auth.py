import pytest

from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import create_token, decode_token
from app.models.enums import StaffRole
from app.schemas.auth import StaffUserCreate
from app.services import auth as auth_service
from tests.conftest import auth_headers


async def test_login_returns_tokens(client, admin_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@airport.example.com", "password": "correct-horse-battery-staple"},
    )
    assert resp.status_code == 200, resp.text

    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] and body["refresh_token"]
    assert body["expires_in"] > 0


async def test_login_rejects_wrong_password(client, admin_user):
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@airport.example.com", "password": "not-the-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "authentication_failed"


async def test_login_does_not_reveal_whether_email_exists(client, admin_user):
    """Both failures must be indistinguishable, or the endpoint enumerates accounts."""
    wrong_pw = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@airport.example.com", "password": "not-the-password"},
    )
    no_such_user = await client.post(
        "/api/v1/auth/login",
        json={"email": "ghost@airport.example.com", "password": "not-the-password"},
    )
    assert wrong_pw.status_code == no_such_user.status_code == 401
    assert wrong_pw.json() == no_such_user.json()


async def test_password_is_never_stored_in_plaintext(session, admin_user):
    assert admin_user.password_hash != "correct-horse-battery-staple"
    assert admin_user.password_hash.startswith("$argon2")


async def test_protected_route_requires_token(client):
    resp = await client.get("/api/v1/flights")
    assert resp.status_code == 401


async def test_protected_route_rejects_garbage_token(client):
    resp = await client.get("/api/v1/flights", headers={"Authorization": "Bearer not-a-real-token"})
    assert resp.status_code == 401


async def test_refresh_token_is_not_accepted_as_access_token(client, admin_user):
    """A refresh token must not unlock the API; only /auth/refresh may consume it."""
    refresh = create_token(subject=str(admin_user.id), token_type="refresh")
    resp = await client.get("/api/v1/flights", headers={"Authorization": f"Bearer {refresh}"})
    assert resp.status_code == 401


async def test_refresh_endpoint_issues_new_access_token(client, admin_user):
    tokens = auth_service.issue_tokens(admin_user)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens.refresh_token})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


async def test_access_token_is_not_accepted_as_refresh_token(client, admin_user):
    tokens = auth_service.issue_tokens(admin_user)
    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens.access_token})
    assert resp.status_code == 401


async def test_token_signed_with_another_secret_is_rejected():
    import jwt  # noqa: PLC0415

    forged = jwt.encode(
        {"sub": "1", "type": "access", "exp": 9999999999},
        "an-attacker-secret-long-enough-to-avoid-a-key-length-warning",
        algorithm="HS256",
    )
    with pytest.raises(AuthenticationError):
        decode_token(forged, expected_type="access")


async def test_me_returns_current_user(client, admin_user, admin_headers):
    resp = await client.get("/api/v1/auth/me", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@airport.example.com"
    assert "password_hash" not in resp.json()


async def test_non_admin_cannot_create_staff(client, security_user):
    resp = await client.post(
        "/api/v1/auth/staff",
        headers=auth_headers(security_user),
        json={
            "email": "new@airport.example.com",
            "full_name": "New Hire",
            "password": "another-long-password",
            "role": "ops",
        },
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "permission_denied"


async def test_admin_can_create_staff(client, admin_headers):
    resp = await client.post(
        "/api/v1/auth/staff",
        headers=admin_headers,
        json={
            "email": "ops@airport.example.com",
            "full_name": "Ops Person",
            "password": "another-long-password",
            "role": "ops",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["role"] == "ops"


async def test_duplicate_email_rejected(session, admin_user):
    from app.core.errors import ConflictError  # noqa: PLC0415

    with pytest.raises(ConflictError):
        await auth_service.create_staff_user(
            session,
            StaffUserCreate(
                email="admin@airport.example.com",
                full_name="Impostor",
                password="yet-another-long-password",
                role=StaffRole.OPS,
            ),
        )


async def test_disabled_account_cannot_log_in(session, admin_user):
    admin_user.is_active = False
    await session.commit()

    with pytest.raises(AuthenticationError):
        await auth_service.authenticate(
            session, "admin@airport.example.com", "correct-horse-battery-staple"
        )


async def test_admin_bypasses_role_checks(admin_user):
    """Admin is deliberately a superset of every other role."""
    auth_service.ensure_role(admin_user, {StaffRole.SECURITY})


async def test_role_check_rejects_mismatch(security_user):
    with pytest.raises(PermissionDeniedError):
        auth_service.ensure_role(security_user, {StaffRole.OPS})


# --------------------------------------------------------------------------- logout / revocation

PASSWORD = "correct-horse-battery-staple"
EMAIL = "admin@airport.example.com"


async def _login(client, password: str = PASSWORD, email: str = EMAIL):
    return await client.post("/api/v1/auth/login", json={"email": email, "password": password})


async def test_logout_stops_the_access_token_working(client, admin_user):
    """The point of the whole revocation table.

    The token stays perfectly valid cryptographically after logout; it is the
    server's refusal that ends the session.
    """
    tokens = (await _login(client)).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 200

    resp = await client.post("/api/v1/auth/logout", json={}, headers=headers)
    assert resp.status_code == 204, resp.text

    after = await client.get("/api/v1/auth/me", headers=headers)
    assert after.status_code == 401
    assert after.json()["message"] == "This token has been revoked."


async def test_logout_stops_the_refresh_token_minting_new_access_tokens(client, admin_user):
    """Revoking only the access token would be theatre: the refresh token
    outlives it by days and can mint a replacement immediately."""
    tokens = (await _login(client)).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
        headers=headers,
    )
    assert resp.status_code == 204, resp.text

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 401
    assert refreshed.json()["message"] == "This token has been revoked."


async def test_logout_without_refresh_token_leaves_it_usable(client, admin_user):
    """Documenting the sharp edge: the header token is all the server sees, so a
    caller that does not send its refresh token is not fully logged out."""
    tokens = (await _login(client)).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    await client.post("/api/v1/auth/logout", json={}, headers=headers)

    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert refreshed.status_code == 200


async def test_logout_is_idempotent(client, admin_user):
    tokens = (await _login(client)).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    first = await client.post("/api/v1/auth/logout", json={}, headers=headers)
    assert first.status_code == 204

    # The second call presents a now-revoked token, so it is rejected as such
    # rather than exploding on a duplicate primary key.
    second = await client.post("/api/v1/auth/logout", json={}, headers=headers)
    assert second.status_code == 401


async def test_logout_requires_a_token(client):
    assert (await client.post("/api/v1/auth/logout", json={})).status_code == 401


async def test_logout_tolerates_a_junk_refresh_token(client, admin_user):
    """The access token still gets revoked. Refusing to log out because the
    client sent a token that could not have worked anyway leaves it *more*
    logged in."""
    tokens = (await _login(client)).json()
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    resp = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": "not-a-jwt"}, headers=headers
    )
    assert resp.status_code == 204, resp.text
    assert (await client.get("/api/v1/auth/me", headers=headers)).status_code == 401


async def test_purge_only_removes_revocations_that_have_expired(session, admin_user):
    from datetime import UTC, datetime, timedelta  # noqa: PLC0415

    from app.models.operations import RevokedToken  # noqa: PLC0415

    now = datetime.now(UTC)
    session.add_all(
        [
            RevokedToken(
                jti="expired-jti",
                staff_user_id=admin_user.id,
                token_type="access",
                expires_at=now - timedelta(minutes=1),
            ),
            RevokedToken(
                jti="live-jti",
                staff_user_id=admin_user.id,
                token_type="refresh",
                expires_at=now + timedelta(days=1),
            ),
        ]
    )
    await session.commit()

    assert await auth_service.purge_expired_revocations(session) == 1
    assert await auth_service.is_revoked(session, "expired-jti") is False
    assert await auth_service.is_revoked(session, "live-jti") is True


# --------------------------------------------------------------------------- login rate limiting


async def test_repeated_failures_are_eventually_rate_limited(client, admin_user):
    for i in range(5):
        assert (await _login(client, password="wrong")).status_code == 401, f"attempt {i}"

    limited = await _login(client, password="wrong")
    assert limited.status_code == 429
    assert limited.headers["Retry-After"] == "900"
    assert limited.json()["code"] == "rate_limited"


async def test_rate_limit_holds_even_with_the_right_password(client, admin_user):
    """Otherwise the lockout is worthless: the attacker's winning guess is the
    one request it would wave through."""
    for _ in range(5):
        await _login(client, password="wrong")

    assert (await _login(client)).status_code == 429


async def test_rate_limit_applies_to_unknown_emails_too(client, admin_user):
    """A limit that only bites for real accounts is an enumeration oracle: 429
    would mean "this email exists" and 401 would mean it does not."""
    unknown = "nobody@airport.example.com"
    for _ in range(5):
        assert (await _login(client, password="wrong", email=unknown)).status_code == 401

    assert (await _login(client, password="wrong", email=unknown)).status_code == 429


async def test_a_successful_login_clears_the_failure_count(client, admin_user):
    """A user who fumbles the password then gets it right should not be left one
    typo away from locking themselves out."""
    for _ in range(4):
        await _login(client, password="wrong")

    assert (await _login(client)).status_code == 200

    # Without the reset, the fifth and sixth failures overall would trip the
    # limit here.
    assert (await _login(client, password="wrong")).status_code == 401
    assert (await _login(client, password="wrong")).status_code == 401
