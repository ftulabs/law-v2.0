"""FastAPI surface for VeriTrade.

Thin HTTP layer over the same pipeline + review functions the CLI and Streamlit
app use. Endpoints:
  POST /pipeline/run        run the full pipeline, return RunResult + export paths
  GET  /runs                list runs
  GET  /mappings            list mappings (filter by run_id/status)
  GET  /review/queue        items awaiting human review
  POST /review/{id}/approve|reject|correct
  GET  /export/{run_id}     re-export CSV+JSON for a run
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .export import export_csv, export_json
from .pipeline.orchestrator import run_pipeline
from .review import workflow
from .schemas import Economy, RunResult
from .storage import db

app = FastAPI(title="VeriTrade", version="0.1.0", description="Auditable legal evidence extraction pipeline")


class RunRequest(BaseModel):
    economy: Economy
    pillars: list[int] = [6, 7]
    use_samples: bool = True
    top_k: int = 5


class CorrectRequest(BaseModel):
    fields: dict
    reviewer: str = "reviewer"
    note: str = ""


class DecisionRequest(BaseModel):
    reviewer: str = "reviewer"
    note: str = ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/pipeline/run")
def pipeline_run(req: RunRequest):
    result: RunResult = run_pipeline(req.economy, req.pillars, use_samples=req.use_samples, top_k=req.top_k, log=lambda *_: None)
    csv_path = export_csv(result.mappings, result.meta.run_id)
    json_path = export_json(result)
    return {
        "run": result.meta.model_dump(),
        "summary": workflow.summary(result.meta.run_id),
        "exports": {"csv": str(csv_path), "json": str(json_path)},
        "mappings": [m.model_dump() for m in result.mappings],
    }


@app.get("/runs")
def runs():
    return db.list_runs()


@app.get("/mappings")
def mappings(run_id: str | None = None, status: str | None = None):
    return [m.model_dump() for m in db.list_mappings(run_id=run_id, status=status)]


@app.get("/review/queue")
def review_queue(run_id: str | None = None):
    return [m.model_dump() for m in workflow.queue(run_id)]


@app.post("/review/{mapping_id}/approve")
def review_approve(mapping_id: str, req: DecisionRequest):
    m = workflow.approve(mapping_id, req.reviewer, req.note)
    if m is None:
        raise HTTPException(404, "mapping not found")
    return m.model_dump()


@app.post("/review/{mapping_id}/reject")
def review_reject(mapping_id: str, req: DecisionRequest):
    m = workflow.reject(mapping_id, req.reviewer, req.note)
    if m is None:
        raise HTTPException(404, "mapping not found")
    return m.model_dump()


@app.post("/review/{mapping_id}/correct")
def review_correct(mapping_id: str, req: CorrectRequest):
    m = workflow.correct(mapping_id, req.fields, req.reviewer, req.note)
    if m is None:
        raise HTTPException(404, "mapping not found")
    return m.model_dump()


@app.get("/export/{run_id}")
def export(run_id: str):
    meta = db.get_run(run_id)
    if meta is None:
        raise HTTPException(404, "run not found")
    mappings = db.list_mappings(run_id=run_id)
    result = RunResult(meta=meta, mappings=mappings)
    return {"csv": str(export_csv(mappings, run_id)), "json": str(export_json(result))}
