"""The routes that are not part of the API surface but that humans hit first,
plus the provider-URL normalisation every deploy depends on.

None of this was covered before, which is exactly how the deployment shipped
answering `{"detail":"Not Found"}` at its own URL.
"""

from urllib.parse import parse_qsl, urlsplit

import pytest
from httpx import ASGITransport, AsyncClient


def _settings(url: str):
    from app.core.config import Settings

    return Settings(_env_file=None, database_url=url, jwt_secret="x" * 40)


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        # Render / Heroku hand out postgres://
        (
            "postgres://u:p@host.render.com:5432/db",
            "postgresql+psycopg://u:p@host.render.com:5432/db",
        ),
        # Neon hands out postgresql://
        (
            "postgresql://u:p@ep-x.neon.tech/db",
            "postgresql+psycopg://u:p@ep-x.neon.tech/db",
        ),
        # Already correct: must pass through untouched.
        (
            "postgresql+psycopg://u:p@localhost:5433/airport",
            "postgresql+psycopg://u:p@localhost:5433/airport",
        ),
    ],
)
def test_provider_urls_get_an_async_driver(given: str, expected: str):
    assert str(_settings(given).database_url) == expected


def test_supabase_pooled_url_drops_the_supa_marker_and_keeps_sslmode():
    """Supabase's pooled URL carries ?supa=base-pooler.x.

    libpq has no such option, so psycopg rejects the whole connection with
    `invalid connection option "supa"`. Only the *pooled* URL carries it, so
    migrations succeed against the session URL and just the serverless app
    breaks — which reads like an application bug.
    """
    url = str(
        _settings(
            "postgres://u:p@aws-0-us-east-1.pooler.supabase.com:6543/postgres"
            "?sslmode=require&supa=base-pooler.x"
        ).database_url
    )
    # Parse the query rather than substring-match: "supa" also appears inside
    # "supabase.com", so `"supa" not in url` fails on a correctly-cleaned URL.
    params = dict(parse_qsl(urlsplit(url).query))
    assert "supa" not in params, params
    assert params.get("sslmode") == "require", "sslmode is a real option and must survive"
    assert url.startswith("postgresql+psycopg://")
    assert "aws-0-us-east-1.pooler.supabase.com" in url, "host must be untouched"


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
