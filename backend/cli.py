"""VeriTrade CLI (Typer).

    python -m backend.cli run-pipeline --economy SG --pillar 7 --use-samples
    python -m backend.cli discover --economy AU --pillar 6
    python -m backend.cli review --queue
    python -m backend.cli review --approve map-abc123 --note "verified"
    python -m backend.cli export --run run-xxxx --format csv
"""
from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .config import settings
from .export import export_csv, export_json
from .pipeline import discovery as discovery_mod
from .pipeline.orchestrator import run_pipeline
from .review import workflow
from .schemas import Economy, RunResult
from .storage import db

app = typer.Typer(add_completion=False, help="VeriTrade — auditable legal evidence extraction")
console = Console()


def _econ(value: str) -> Economy:
    from .schemas import resolve_economy
    try:
        return resolve_economy(value)   # codes, UN names, or mis-spellings
    except ValueError as e:
        raise typer.BadParameter(str(e))


@app.command()
def discover(economy: str = typer.Option(...), pillar: Optional[int] = None,
             use_samples: bool = typer.Option(True, "--use-samples/--live")):
    """Zone 1 only: list candidate legal documents."""
    docs = discovery_mod.discover(_econ(economy), pillar, use_samples=use_samples)
    table = Table("relevance", "tag", "format", "title", "amended")
    for d in docs:
        table.add_row(f"{d.relevance_score:.2f}", d.discovery_tag.value, d.fmt.value,
                      d.title[:60], d.amendment_date or "-")
    console.print(table)
    console.print(f"[bold]{len(docs)}[/bold] documents")


@app.command()
def zone1(economy: str = typer.Option(...), pillar: Optional[int] = None,
          use_samples: bool = typer.Option(True, "--use-samples/--live"),
          top_k: int = 5, ocr: Optional[str] = typer.Option(None)):
    """Zone 1 deliverable: ranked list of relevant provisions per indicator
    (discover → fetch → extract → hybrid retrieve), WITHOUT the Zone-2 LLM mapping."""
    from .pipeline.zone1 import find_provisions
    res = find_provisions(_econ(economy), pillar, use_samples=use_samples, top_k=top_k,
                          ocr_provider=ocr, log=lambda m: console.print(f"[dim]{m}[/dim]"))
    table = Table("score", "indicator", "econ", "article", "law", "source")
    for rp in res.ranked[:60]:
        p = rp.provision
        table.add_row(f"{rp.score:.2f}", rp.indicator_id, p.economy.value,
                      p.article_section[:18], p.law_name[:34], p.source_url[:42])
    console.print(table)
    console.print(f"[bold]{len(res.docs)}[/bold] docs · [bold]{len(res.provisions)}[/bold] provisions · "
                  f"[bold]{len(res.ranked)}[/bold] ranked pairs")


@app.command("run-pipeline")
def run_pipeline_cmd(
    economy: str = typer.Option(...),
    pillar: Optional[list[int]] = typer.Option(None, help="repeatable; default 6 and 7"),
    use_samples: bool = typer.Option(True, "--use-samples/--live"),
    top_k: int = 5,
    ocr: Optional[str] = typer.Option(None, help="OCR provider: mock|tesseract|paddle|azure"),
    llm: Optional[str] = typer.Option(None, help="LLM provider: mock|anthropic|openai"),
    llm_model: Optional[str] = typer.Option(None, help="override LLM model name"),
    export: bool = typer.Option(True, help="write CSV+JSON"),
):
    """Run the full pipeline and export CSV + JSON."""
    pillars = pillar or [6, 7]
    result: RunResult = run_pipeline(_econ(economy), pillars, use_samples=use_samples, top_k=top_k,
                                     log=lambda m: console.print(f"[dim]{m}[/dim]"),
                                     ocr_provider=ocr, llm_provider=llm, llm_model=llm_model)
    _print_mappings(result.mappings)
    if export:
        csv_path = export_csv(result.mappings, result.meta.run_id)
        json_path = export_json(result)
        console.print(f"\n[green]CSV[/green]  {csv_path}")
        console.print(f"[green]JSON[/green] {json_path}")
        if any(m.raw_score is not None for m in result.mappings):
            from .export import export_scored_csv
            console.print(f"[green]SCORED[/green] {export_scored_csv(result.mappings, result.meta.run_id)}")
    console.print(f"\nrun_id = [bold cyan]{result.meta.run_id}[/bold cyan]  "
                  f"({result.meta.processing_time_seconds}s, providers: "
                  f"OCR={result.meta.ocr_provider} / LLM={result.meta.llm_provider})")


@app.command()
def review(
    queue: bool = typer.Option(False, "--queue", help="show pending-review items"),
    run: Optional[str] = None,
    approve: Optional[str] = None,
    reject: Optional[str] = None,
    note: str = "",
    reviewer: str = "cli",
):
    """Human-in-the-loop review actions."""
    if approve:
        m = workflow.approve(approve, reviewer, note)
        console.print(f"approved {approve}" if m else "[red]not found[/red]")
        return
    if reject:
        m = workflow.reject(reject, reviewer, note)
        console.print(f"rejected {reject}" if m else "[red]not found[/red]")
        return
    items = workflow.queue(run) if (queue or True) else []
    _print_mappings(items, title="Pending review")
    console.print(workflow.summary(run))


@app.command()
def runs():
    """List previous runs."""
    table = Table("run_id", "economy", "pillars", "started", "finished")
    for r in db.list_runs():
        table.add_row(r["run_id"], r["economy"], r["pillars"], r["started_at"], r["finished_at"] or "-")
    console.print(table)


@app.command("export")
def export_cmd(run: str = typer.Option(...), fmt: str = typer.Option("both", "--format")):
    """Re-export a finished run."""
    meta = db.get_run(run)
    if meta is None:
        raise typer.BadParameter(f"run {run} not found")
    mappings = db.list_mappings(run_id=run)
    if fmt in ("csv", "both"):
        console.print(f"CSV  {export_csv(mappings, run)}")
    if fmt in ("json", "both"):
        console.print(f"JSON {export_json(RunResult(meta=meta, mappings=mappings))}")


def _print_mappings(mappings, title: str = "Mappings"):
    table = Table("conf", "status", "indicator", "economy", "article", "law", title=title)
    for m in mappings[:50]:
        flag = " (!)" if m.scope_flag else ""
        table.add_row(f"{m.confidence_score:.2f}", m.review_status.value, m.indicator_id + flag,
                      m.economy.value, m.article_section[:18], m.law_name[:40])
    console.print(table)


if __name__ == "__main__":
    app()
