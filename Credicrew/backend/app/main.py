from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers.health import router as health_router
from app.routers.candidates import router as candidates_router
from app.routers.roles import router as roles_router
from app.routers.match import router as match_router
from app.routers.outreach import router as outreach_router
from app.routers.interview import router as interview_router
from app.routers.decision import router as decision_router
from app.routers.offer import router as offer_router
from app.routers.peer_parity import router as peer_parity_router
from app.routers.portfolio import router as portfolio_router
from app.routers.calibration import router as calibration_router
from app.routers.sources import router as sources_router
from app.routers.forecast import router as forecast_router
from app.routers.cadence import router as cadence_router
from app.routers.crosswind import router as crosswind_router
from app.routers.revive import router as revive_router

app = FastAPI(title="Credicrew API", version="0.14.0")

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
app.include_router(interview_router)
app.include_router(decision_router)
app.include_router(offer_router)
app.include_router(peer_parity_router)
app.include_router(portfolio_router)
app.include_router(calibration_router)
app.include_router(sources_router)
app.include_router(forecast_router)
app.include_router(cadence_router)
app.include_router(crosswind_router)
app.include_router(revive_router)


@app.get("/")
async def root() -> dict[str, str]:
    return {
        "message": "Welcome to Credicrew API",
        "health": "/health",
        "match": "POST /match",
        "outreach": "POST /outreach",
        "interview_plan": "POST /interview/plan",
        "interview_score": "POST /interview/score",
        "interview_ics": "POST /interview/ics",
        "decision_summary": "POST /decision/summary",
        "decision_debrief": "POST /decision/debrief",
        "offer_benchmark": "POST /offer/benchmark",
        "offer_simulate": "POST /offer/simulate",
        "offer_compose": "POST /offer/compose",
        "offer_full": "POST /offer/full",
        "peer_parity_check": "POST /peer-parity/check",
        "peer_parity_peers": "GET/POST /peer-parity/peers?team=ID",
        "portfolio_summary": "POST /portfolio/summary",
        "calibration_summary": "POST /calibration/summary",
        "sources_summary": "POST /sources/summary",
        "sources_brief": "POST /sources/brief",
        "forecast_run": "POST /forecast/run",
        "forecast_defaults": "GET /forecast/defaults",
        "cadence_summary": "POST /cadence/summary",
        "cadence_brief": "POST /cadence/brief",
        "cadence_defaults": "GET /cadence/defaults",
        "crosswind_summary": "POST /crosswind/summary",
        "crosswind_brief": "POST /crosswind/brief",
        "crosswind_defaults": "GET /crosswind/defaults",
        "revive_summary": "POST /revive/summary",
        "revive_brief": "POST /revive/brief",
        "revive_defaults": "GET /revive/defaults",
        "docs": "/docs",
    }
