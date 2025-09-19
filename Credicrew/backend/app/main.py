from fastapi import FastAPI
from app.routers.health import router as health_router
from app.routers.roles import router as roles_router
from app.routers.candidates import router as candidates_router
from app.db.base import Base
from app.db.session import engine
import app.models  # noqa

app = FastAPI(title="Credicrew API", version="0.2.0")

@app.on_event("startup")
def create_tables():
    Base.metadata.create_all(bind=engine)

app.include_router(health_router)
app.include_router(roles_router)
app.include_router(candidates_router)

@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Welcome to Credicrew API", "health": "/health"}
