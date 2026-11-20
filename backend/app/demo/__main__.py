"""`python -m app.demo`: run the whole product on your machine with one command.

Starts a private PostgreSQL (bundled with the `demo` extra, no Docker and no installation), applies
the migrations, seeds a demo organisation, and serves the API and the console on one port. Readers
and the face matcher are simulated and everything on screen is synthetic.

    pip install -e "backend[demo]"
    python -m app.demo                 # http://127.0.0.1:8000
    python -m app.demo --fresh         # wipe the demo data and start again
    python -m app.demo --database-url postgresql+psycopg://...   # use your own PostgreSQL
"""

import argparse
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent


def _stale(dist: Path, front: Path) -> bool:
    """True when something the console is built from is newer than the build, so a `git pull` is not
    followed by the old screens."""
    built = (dist / "index.html").stat().st_mtime
    watched = [front / "index.html", front / "package.json", front / "package-lock.json"]
    src = front / "src"
    if src.is_dir():
        watched += [p for p in src.rglob("*") if p.is_file()]
    return any(p.stat().st_mtime > built for p in watched if p.exists())


def _dist() -> Path | None:
    front = REPO / "frontend"
    dist = front / "dist"
    built = (dist / "index.html").exists()
    if built and not _stale(dist, front):
        return dist
    npm = shutil.which("npm")
    if npm and (front / "package.json").exists():
        why = "the source changed" if built else "first run"
        print(f"Building the console ({why})...", flush=True)
        try:
            if not (front / "node_modules").exists():
                subprocess.run([npm, "ci", "--silent"], cwd=front, check=True)  # noqa: S603
            subprocess.run([npm, "run", "build", "--silent"], cwd=front, check=True)  # noqa: S603
        except (subprocess.CalledProcessError, OSError) as exc:
            if built:
                print(
                    f"Could not rebuild the console ({exc}). Serving the older build.", flush=True
                )
                return dist
            print(f"Could not build the console ({exc}). Starting API-only.", flush=True)
            return None
        return dist if (dist / "index.html").exists() else None
    if built:
        print(
            "The console source changed but npm was not found. Serving the older build.", flush=True
        )
        return dist
    print("The console is not built and npm was not found. Starting API-only.", flush=True)
    return None


def _check_data_dir(data: Path) -> None:
    """When run as root, the bundled PostgreSQL drops to its own user, which must be able to reach
    the data directory. A root-only parent (mode 700) makes it crash minutes later."""
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        return
    paths = [data.resolve()]
    try:
        import pixeltable_pgserver

        paths.append(Path(pixeltable_pgserver.__file__).resolve().parent)  # its binaries and libs
    except ImportError:
        pass
    for path in paths:
        for parent in [path, *path.parents]:
            if parent.exists() and not parent.stat().st_mode & 0o001:
                sys.exit(
                    f"{parent} is not accessible to other users, and the embedded PostgreSQL runs as a\n"
                    "separate user when started by root, so it could not read its own files or your\n"
                    "data. Run the demo as a regular user, or keep the data directory and the Python\n"
                    "environment under normal world-readable paths."
                )


def _embedded_postgres(data: Path) -> str:
    try:
        import pixeltable_pgserver as pgserver
    except ImportError:
        sys.exit(
            "The embedded database is not installed.\n"
            '  pip install -e "backend[demo]"\n'
            "or point at your own PostgreSQL with --database-url."
        )
    data.mkdir(parents=True, exist_ok=True)
    server = pgserver.get_server(str(data / "pg"), cleanup_mode="stop")
    return server.get_uri().replace("postgresql://", "postgresql+psycopg://", 1)


def _migrate() -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    command.upgrade(cfg, "head")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m app.demo", description=__doc__.split("\n\n")[0])
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument(
        "--data-dir", default=str(REPO / "var" / "demo"), help="database and uploaded images"
    )
    ap.add_argument("--fresh", action="store_true", help="delete the demo data first")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--database-url", help="use this PostgreSQL instead of the embedded one")
    args = ap.parse_args()

    data = Path(args.data_dir)
    if args.fresh and data.exists():
        shutil.rmtree(data)
    data.mkdir(parents=True, exist_ok=True)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "WARNING: the demo has no login and can wipe its data. Keep it on localhost.",
            flush=True,
        )

    if not (args.database_url or os.environ.get("POPS_DATABASE_URL")):
        _check_data_dir(data)
    db = args.database_url or os.environ.get("POPS_DATABASE_URL") or _embedded_postgres(data)
    os.environ.update(
        POPS_ENV="dev",
        POPS_DEMO="true",
        POPS_DATABASE_URL=db,
        POPS_PIPELINE_MODE="inline",
        POPS_VLM_BACKEND="fake",
        POPS_KYC_FACE_BACKEND="demo",
        POPS_OCR_BACKEND="none",
        POPS_STORAGE_BACKEND="local",
        POPS_STORAGE_LOCAL_DIR=str(data / "evidence"),
        POPS_LOG_JSON="false",
        POPS_FX_ENABLED="true",  # the cross-currency story reads a (manually entered) rate
        POPS_CORS_ORIGINS='["http://localhost:5173"]',
    )
    os.environ.pop("POPS_CLAMAV_HOST", None)
    import logging

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("app.core.ratelimit").setLevel(logging.ERROR)  # no Redis here: memory is fine
    sys.path.insert(0, str(BACKEND))

    _migrate()
    dist = _dist()

    import uvicorn
    from fastapi.testclient import TestClient

    from app.core.db import get_sessionmaker
    from app.demo import server, service

    root = server.build(dist)
    with get_sessionmaker()() as s:
        empty = service.is_empty(s)
    if empty:
        print("Seeding demo data (about 20 seconds)...", flush=True)
        from app.main import app as api

        started = time.time()
        ran = service.seed(service.api_for(TestClient(api, base_url="http://demo.local")))
        print(f"Seeded {sum(ran.values())} stories in {time.time() - started:.0f}s.", flush=True)

    url = f"http://{'localhost' if args.host in ('127.0.0.1', '::1') else args.host}:{args.port}"
    print(
        f"\n  Validate demo is running at {url}\n  (API docs at {url}/api/docs). Ctrl+C to stop.\n",
        flush=True,
    )
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run(root, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
