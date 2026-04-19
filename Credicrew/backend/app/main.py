from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.health import router as health_router
from app.routers.match import router as match_router

app = FastAPI(
    title="Credicrew API",
    version="0.2.0",
    description="Talent discovery + explainable JD ↔ candidate matching.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(match_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "Credicrew API",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
        "match": "/match",
    }
