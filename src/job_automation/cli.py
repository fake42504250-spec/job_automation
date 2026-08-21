from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import uvicorn
from apscheduler.schedulers.blocking import BlockingScheduler

from .config import initialize_project, load_settings
from .db import Database
from .pipeline import Pipeline


def project_root() -> Path:
    return Path.cwd()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local job outreach automation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init", help="Create local .env, profile, data folder and database")
    subparsers.add_parser("run", help="Run the complete pipeline once")
    subparsers.add_parser("status", help="Print pipeline counts")
    start = subparsers.add_parser("start", help="Start dashboard and daily scheduler")
    start.add_argument("--host", default="127.0.0.1")
    start.add_argument("--port", default=8000, type=int)
    subparsers.add_parser("scheduler", help="Run only the blocking daily scheduler")
    return parser


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    args = build_parser().parse_args()
    settings = load_settings(project_root())

    if args.command == "init":
        created = initialize_project(settings)
        Database(settings.database_file).initialize()
        print("Initialization complete.")
        for path in created:
            print(f"Created {path.relative_to(settings.root_dir)}")
        print("Next: edit config/profile.yaml and add config/gmail_credentials.json")
        return

    if args.command == "run":
        print(json.dumps(Pipeline(settings).run_once(), indent=2))
        return

    if args.command == "status":
        database = Database(settings.database_file)
        database.initialize()
        print(json.dumps(database.dashboard()["counts"], indent=2))
        return

    if args.command == "start":
        uvicorn.run("job_automation.web:app", host=args.host, port=args.port, reload=False)
        return

    if args.command == "scheduler":
        pipeline = Pipeline(settings)
        scheduler = BlockingScheduler(timezone=settings.timezone)
        hour, minute = (int(part) for part in settings.run_at.split(":", 1))
        scheduler.add_job(pipeline.run_once, "cron", hour=hour, minute=minute)
        print(f"Scheduler active: every day at {settings.run_at} {settings.timezone}")
        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            sys.exit(0)


if __name__ == "__main__":
    main()
