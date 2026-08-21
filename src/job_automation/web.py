from __future__ import annotations

import html
import logging
from contextlib import asynccontextmanager
from threading import Thread

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .config import load_settings
from .pipeline import Pipeline

LOGGER = logging.getLogger(__name__)
settings = load_settings()
pipeline = Pipeline(settings)


def scheduled_run() -> None:
    try:
        pipeline.run_once()
    except Exception:
        LOGGER.exception("Scheduled pipeline run failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = BackgroundScheduler(timezone=settings.timezone)
    hour, minute = (int(part) for part in settings.run_at.split(":", 1))
    scheduler.add_job(scheduled_run, "cron", hour=hour, minute=minute, id="daily-pipeline")
    scheduler.start()
    app.state.scheduler = scheduler
    yield
    scheduler.shutdown(wait=False)


app = FastAPI(title="Job Automation", lifespan=lifespan)


def _cell(value) -> str:
    return html.escape(str(value or ""))


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    data = pipeline.db.dashboard()
    cards = "".join(
        f'<div class="card"><strong>{_cell(label.title())}</strong><span>{value}</span></div>'
        for label, value in data["counts"].items()
    )
    job_rows = "".join(
        "<tr>"
        f"<td>{_cell(row['company'])}</td><td>{_cell(row['title'])}</td>"
        f"<td>{row['score']}</td><td>{_cell(row['track'])}</td>"
        f"<td>{_cell(row['status'])}</td><td><a href=\"{_cell(row['url'])}\" target=\"_blank\">Open</a></td>"
        "</tr>"
        for row in data["jobs"]
    )
    outreach_rows = "".join(
        "<tr>"
        f"<td>{_cell(row['company'])}</td><td>{_cell(row['email'])}</td>"
        f"<td>{row['attempt']}</td><td>{_cell(row['status'])}</td>"
        f"<td><details><summary>Preview</summary><pre>{_cell(row['body'])}</pre></details></td>"
        "</tr>"
        for row in data["outreach"]
    )
    mode = "DRY RUN — nothing will be sent" if settings.dry_run else "LIVE — automatic sending enabled"
    return f"""<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Job Automation</title><style>
body{{font-family:Inter,Arial,sans-serif;margin:0;background:#f4f7fb;color:#172033}}
header{{background:#17324d;color:white;padding:24px 5%}} main{{padding:24px 5%}}
.mode{{background:{'#fff1d6' if settings.dry_run else '#dff5e9'};padding:12px;border-radius:8px;margin-bottom:18px}}
.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px}}
.card{{background:white;border-radius:10px;padding:18px;box-shadow:0 2px 10px #0001}}
.card span{{display:block;font-size:28px;color:#2563eb;margin-top:8px}}
button{{background:#2563eb;color:white;border:0;border-radius:7px;padding:11px 18px;cursor:pointer}}
table{{width:100%;border-collapse:collapse;background:white;margin:14px 0 28px}}
th,td{{padding:10px;border-bottom:1px solid #dce3ec;text-align:left;vertical-align:top}}
th{{background:#eaf2ff}} pre{{white-space:pre-wrap;max-width:700px}}
</style></head><body><header><h1>Job Automation</h1><p>Local job discovery and recruiter email outreach</p></header>
<main><div class="mode"><strong>{mode}</strong></div>
<form method="post" action="/run"><button type="submit">Run pipeline now</button></form>
<h2>Pipeline</h2><div class="cards">{cards}</div>
<h2>Jobs</h2><table><tr><th>Company</th><th>Role</th><th>Score</th><th>Track</th><th>Status</th><th>Link</th></tr>{job_rows}</table>
<h2>Outreach</h2><table><tr><th>Company</th><th>Recipient</th><th>Attempt</th><th>Status</th><th>Draft</th></tr>{outreach_rows}</table>
</main></body></html>"""


@app.post("/run")
def run_pipeline():
    Thread(target=scheduled_run, daemon=True).start()
    return RedirectResponse(url="/", status_code=303)


@app.get("/api/status")
def api_status():
    return JSONResponse(
        {
            "mode": "dry-run" if settings.dry_run else "live",
            "schedule": settings.run_at,
            "timezone": settings.timezone,
            **pipeline.db.dashboard()["counts"],
        }
    )


@app.get("/health")
def health():
    return {"status": "ok"}

