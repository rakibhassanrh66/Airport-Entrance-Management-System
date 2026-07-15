"""The routes that are not part of the API surface but that humans hit first.

None of this was covered before, which is exactly how the deployment shipped
answering `{"detail":"Not Found"}` at its own URL.
"""

import pytest
from httpx import ASGITransport, AsyncClient


async def test_health_does_not_require_the_database(client: AsyncClient):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_ready_reports_the_database(client: AsyncClient):
    r = await client.get("/ready")
    assert r.status_code == 200
    assert r.json()["database"] == "ok"


async def test_root_redirects_to_docs_when_docs_are_served(client: AsyncClient):
    """A bare GET / must not 404. It is the first thing anyone opens."""
    r = await client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/docs"


async def test_root_follows_through_to_something_real(client: AsyncClient):
    r = await client.get("/", follow_redirects=True)
    assert r.status_code == 200


@pytest.mark.parametrize("path", ["/health", "/ready", "/"])
async def test_public_routes_need_no_token(client: AsyncClient, path: str):
    """These must stay reachable unauthenticated: probes and a landing page."""
    r = await client.get(path, follow_redirects=False)
    assert r.status_code != 401, f"{path} unexpectedly requires auth"


async def test_root_serves_an_index_in_production_rather_than_a_dead_redirect():
    """With docs disabled, redirecting to /docs would swap one 404 for another."""
    from app.core.config import Settings
    from app.main import create_app

    settings = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://u:p@localhost:5432/db",
        jwt_secret="x" * 40,
    )

    import app.main as main_module

    original = main_module.get_settings
    main_module.get_settings = lambda: settings
    try:
        prod_app = create_app()
        assert prod_app.docs_url is None, "precondition: docs are off in production"

        transport = ASGITransport(app=prod_app)
        async with AsyncClient(transport=transport, base_url="http://test") as c:
            r = await c.get("/", follow_redirects=False)
    finally:
        main_module.get_settings = original

    assert r.status_code == 200
    body = r.json()
    assert body["endpoints"]["api"] == "/api/v1"
    assert body["docs"] == "disabled in production"
