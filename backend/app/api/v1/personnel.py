"""Employees, maintenance scheduling and crew rostering.

Employee writes are admin-only — it is HR data, salaries included. Maintenance
and crew are operational, so ops may manage them.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import CurrentUser, RequireAdmin, RequireOps, SessionDep
from app.api.v1._pagination import paginate
from app.core.errors import NotFoundError
from app.models.operations import Employee, MaintenanceSchedule
from app.schemas.common import Page
from app.schemas.operations import (
    CrewAssignmentCreate,
    CrewAssignmentOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeUpdate,
    MaintenanceCreate,
    MaintenanceOut,
)
from app.services import crew as crew_service

router = APIRouter()


# --------------------------------------------------------------------------- employees


@router.get(
    "/employees", response_model=Page[EmployeeOut], summary="List employees", tags=["employees"]
)
async def list_employees(
    session: SessionDep,
    _: CurrentUser,
    department: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[EmployeeOut]:
    stmt = select(Employee)
    if department is not None:
        stmt = stmt.where(Employee.department == department)
    return await paginate(
        session, stmt, schema=EmployeeOut, limit=limit, offset=offset, order_by=Employee.name
    )


@router.post(
    "/employees",
    response_model=EmployeeOut,
    status_code=status.HTTP_201_CREATED,
    summary="Add an employee",
    tags=["employees"],
)
async def create_employee(
    payload: EmployeeCreate, session: SessionDep, _: RequireAdmin
) -> EmployeeOut:
    employee = Employee(**payload.model_dump())
    session.add(employee)
    await session.commit()
    await session.refresh(employee)
    return EmployeeOut.model_validate(employee)


@router.get(
    "/employees/{employee_id}",
    response_model=EmployeeOut,
    summary="Fetch one employee",
    tags=["employees"],
)
async def get_employee(employee_id: int, session: SessionDep, _: CurrentUser) -> EmployeeOut:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError(f"Employee {employee_id} not found.")
    return EmployeeOut.model_validate(employee)


@router.patch(
    "/employees/{employee_id}",
    response_model=EmployeeOut,
    summary="Update an employee",
    tags=["employees"],
)
async def update_employee(
    employee_id: int, payload: EmployeeUpdate, session: SessionDep, _: RequireAdmin
) -> EmployeeOut:
    employee = await session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError(f"Employee {employee_id} not found.")

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(employee, field, value)
    await session.commit()
    await session.refresh(employee)
    return EmployeeOut.model_validate(employee)


# --------------------------------------------------------------------------- maintenance


@router.get(
    "/maintenance",
    response_model=Page[MaintenanceOut],
    summary="List maintenance tasks",
    tags=["maintenance"],
)
async def list_maintenance(
    session: SessionDep,
    _: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[MaintenanceOut]:
    return await paginate(
        session,
        select(MaintenanceSchedule),
        schema=MaintenanceOut,
        limit=limit,
        offset=offset,
        order_by=MaintenanceSchedule.scheduled_date,
    )


@router.post(
    "/maintenance",
    response_model=MaintenanceOut,
    status_code=status.HTTP_201_CREATED,
    summary="Schedule a maintenance task",
    tags=["maintenance"],
)
async def create_maintenance(
    payload: MaintenanceCreate, session: SessionDep, _: RequireOps
) -> MaintenanceOut:
    if payload.employee_id is not None and await session.get(Employee, payload.employee_id) is None:
        raise NotFoundError(f"Employee {payload.employee_id} not found.")

    task = MaintenanceSchedule(**payload.model_dump())
    session.add(task)
    await session.commit()
    await session.refresh(task)
    return MaintenanceOut.model_validate(task)


@router.get(
    "/maintenance/{task_id}",
    response_model=MaintenanceOut,
    summary="Fetch one maintenance task",
    tags=["maintenance"],
)
async def get_maintenance(task_id: int, session: SessionDep, _: CurrentUser) -> MaintenanceOut:
    task = await session.get(MaintenanceSchedule, task_id)
    if task is None:
        raise NotFoundError(f"Maintenance task {task_id} not found.")
    return MaintenanceOut.model_validate(task)


# --------------------------------------------------------------------------- crew scheduling


@router.post(
    "/crew-assignments",
    response_model=CrewAssignmentOut,
    status_code=status.HTTP_201_CREATED,
    summary="Roster a crew member onto a flight",
    description=(
        "Returns 409 if the crew member already has a live assignment on any "
        "flight whose window overlaps this one. Enforced by a PostgreSQL "
        "exclusion constraint, so it holds under concurrency."
    ),
    tags=["crew"],
)
async def assign_crew(
    payload: CrewAssignmentCreate, session: SessionDep, _: RequireOps
) -> CrewAssignmentOut:
    assignment = await crew_service.assign_crew(session, payload)
    return CrewAssignmentOut.model_validate(assignment)


@router.post(
    "/crew-assignments/{assignment_id}/release",
    response_model=CrewAssignmentOut,
    summary="Release a crew assignment",
    tags=["crew"],
)
async def release_crew(assignment_id: int, session: SessionDep, _: RequireOps) -> CrewAssignmentOut:
    assignment = await crew_service.release_crew(session, assignment_id)
    return CrewAssignmentOut.model_validate(assignment)


@router.get(
    "/flights/{flight_id}/crew",
    response_model=list[CrewAssignmentOut],
    summary="Who is rostered on this flight",
    tags=["crew"],
)
async def flight_roster(
    flight_id: int,
    session: SessionDep,
    _: CurrentUser,
    include_released: Annotated[bool, Query()] = False,
) -> list[CrewAssignmentOut]:
    rows = await crew_service.flight_roster(session, flight_id, include_released=include_released)
    return [CrewAssignmentOut.model_validate(r) for r in rows]
