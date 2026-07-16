"""HTTP-level tests for the operational resources: employees, maintenance,
runways, cargo, checkpoints and airline staff — roles, validation and the cargo
lifecycle."""

from tests.conftest import auth_headers

# --------------------------------------------------------------------------- employees


async def test_ops_cannot_create_employee(client, security_user):
    """Employee records are HR data (salaries), so writes are admin-only."""
    resp = await client.post(
        "/api/v1/employees",
        json={"name": "X", "role": "engineer", "department": "eng", "salary": "50000.00"},
        headers=auth_headers(security_user),
    )
    assert resp.status_code == 403


async def test_admin_creates_and_updates_employee(client, admin_headers):
    created = await client.post(
        "/api/v1/employees",
        json={
            "name": "Ada Eng",
            "role": "engineer",
            "department": "maintenance",
            "salary": "72000.00",
        },
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    eid = created.json()["id"]

    patched = await client.patch(
        f"/api/v1/employees/{eid}",
        json={"salary": "80000.00"},
        headers=admin_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["salary"] == "80000.00"
    assert patched.json()["name"] == "Ada Eng"  # untouched fields survive


async def test_employee_update_rejects_empty_body(client, admin_headers):
    created = await client.post(
        "/api/v1/employees",
        json={"name": "Temp", "role": "r", "department": "d", "salary": "1.00"},
        headers=admin_headers,
    )
    eid = created.json()["id"]
    resp = await client.patch(f"/api/v1/employees/{eid}", json={}, headers=admin_headers)
    assert resp.status_code == 422


async def test_list_employees_filters_by_department(client, admin_headers):
    for dept in ("ramp", "ramp", "catering"):
        await client.post(
            "/api/v1/employees",
            json={"name": f"P-{dept}", "role": "r", "department": dept, "salary": "1.00"},
            headers=admin_headers,
        )
    resp = await client.get("/api/v1/employees?department=ramp", headers=admin_headers)
    assert resp.status_code == 200
    assert resp.json()["total"] == 2


# --------------------------------------------------------------------------- maintenance


async def test_ops_schedules_maintenance(client, admin_headers):
    resp = await client.post(
        "/api/v1/maintenance",
        json={"type": "runway", "scheduled_date": "2027-01-01", "description": "resurface 09L"},
        headers=admin_headers,
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["type"] == "runway"


async def test_maintenance_with_unknown_employee_is_404(client, admin_headers):
    resp = await client.post(
        "/api/v1/maintenance",
        json={"type": "aircraft", "scheduled_date": "2027-01-01", "employee_id": 999999},
        headers=admin_headers,
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- runways


async def test_runway_create_and_status(client, admin_headers):
    created = await client.post(
        "/api/v1/runways", json={"runway_number": "09L"}, headers=admin_headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "available"
    rid = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/runways/{rid}/status", json={"status": "maintenance"}, headers=admin_headers
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "maintenance"


async def test_duplicate_runway_number_is_409(client, admin_headers):
    await client.post("/api/v1/runways", json={"runway_number": "27R"}, headers=admin_headers)
    dup = await client.post("/api/v1/runways", json={"runway_number": "27R"}, headers=admin_headers)
    assert dup.status_code == 409


# --------------------------------------------------------------------------- cargo


async def test_cargo_lifecycle_is_enforced(client, admin_headers, flight):
    created = await client.post(
        "/api/v1/cargo",
        json={"flight_id": flight.id, "weight_kg": "1200.00"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]
    assert created.json()["status"] == "loaded"

    # loaded -> in_transit is legal
    ok = await client.patch(
        f"/api/v1/cargo/{cid}/status", json={"status": "in_transit"}, headers=admin_headers
    )
    assert ok.status_code == 200

    # in_transit -> loaded is not; the error lists what is legal
    bad = await client.patch(
        f"/api/v1/cargo/{cid}/status", json={"status": "loaded"}, headers=admin_headers
    )
    assert bad.status_code == 409
    assert bad.json()["code"] == "illegal_state_transition"
    assert "unloaded" in bad.json()["details"]["allowed"]


async def test_cargo_on_unknown_flight_is_404(client, admin_headers):
    resp = await client.post(
        "/api/v1/cargo", json={"flight_id": 999999, "weight_kg": "10.00"}, headers=admin_headers
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- checkpoints


async def test_checkpoint_create_and_status(client, admin_headers):
    created = await client.post(
        "/api/v1/checkpoints", json={"location": "Concourse B"}, headers=admin_headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "active"
    cid = created.json()["id"]

    updated = await client.patch(
        f"/api/v1/checkpoints/{cid}/status", json={"status": "inactive"}, headers=admin_headers
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "inactive"


# --------------------------------------------------------------------------- airline staff


async def test_airline_staff_scoped_to_airline(client, admin_headers, airline):
    created = await client.post(
        f"/api/v1/airlines/{airline.id}/staff",
        json={"name": "Gate Agent", "role": "ground"},
        headers=admin_headers,
    )
    assert created.status_code == 201, created.text
    assert created.json()["airline_id"] == airline.id

    listed = await client.get(f"/api/v1/airlines/{airline.id}/staff", headers=admin_headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1


async def test_airline_staff_on_unknown_airline_is_404(client, admin_headers):
    resp = await client.post(
        "/api/v1/airlines/999999/staff",
        json={"name": "Nobody", "role": "ground"},
        headers=admin_headers,
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------- auth surface


async def test_operational_endpoints_require_authentication(client):
    for path in ("/api/v1/employees", "/api/v1/runways", "/api/v1/cargo", "/api/v1/maintenance"):
        resp = await client.get(path)
        assert resp.status_code == 401, path
