from fastapi import APIRouter

from app.api.v1 import (
    airlines,
    airside,
    auth,
    baggage,
    flights,
    gates,
    immigration,
    passengers,
    personnel,
    tickets,
)

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(airlines.router)
api_router.include_router(flights.router)
api_router.include_router(passengers.router)
api_router.include_router(tickets.router)
api_router.include_router(gates.router)
api_router.include_router(baggage.router)
api_router.include_router(immigration.router)
api_router.include_router(personnel.router)
api_router.include_router(airside.router)
