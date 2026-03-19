"""FastAPI application — minimal scaffold for Phase 0."""

from fastapi import FastAPI

app = FastAPI(
    title="CT CGA File Copy Intelligence Agent",
    version="0.1.0",
    description="Legislative monitoring and alerting system for CT General Assembly file copies.",
)


@app.get("/health")
def health_check():
    return {"status": "ok"}
