from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.health import router as health_router
from app.routers.candidates import router as candidates_router
from app.routers.roles import router as roles_router
from app.routers.match import router as match_router
from app.routers.outreach import router as outreach_router

app = FastAPI(title="Credicrew API", version="0.3.0")

# Allow local dev UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(candidates_router)
app.include_router(roles_router)
app.include_router(match_router)
app.include_router(outreach_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "Welcome to Credicrew API",
        "health": "/health",
        "match": "POST /match",
        "outreach": "POST /outreach",
        "docs": "/docs",
    }
