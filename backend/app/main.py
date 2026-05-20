from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .db import init_graph
from .otlp_receiver import router as otlp_router
from .routes import router as api_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agent Discovery Pipeline")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(otlp_router)
app.include_router(api_router)


@app.on_event("startup")
async def startup():
    logger.info("Initializing graph database…")
    init_graph()
    logger.info("Graph database ready.")


@app.get("/health")
def health():
    return {"status": "ok"}
