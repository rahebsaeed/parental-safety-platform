from __future__ import annotations

import argparse
import sys
import uvicorn

from backend.app.core.config import settings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parental Safety Platform — Backend API Server"
    )
    subparsers = parser.add_subparsers(dest="command", help="Subcommand")

    start_p = subparsers.add_parser("start", help="Start the FastAPI server")
    start_p.add_argument(
        "--host",
        default=settings.HOST,
        help=f"Host address to bind (default: {settings.HOST})",
    )
    start_p.add_argument(
        "--port",
        type=int,
        default=settings.PORT,
        help=f"Port to bind (default: {settings.PORT})",
    )
    start_p.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload on code changes (dev mode)",
    )

    migrate_p = subparsers.add_parser("migrate", help="Run database migrations to head")
    stamp_p = subparsers.add_parser("stamp", help="Stamp database at current head without running SQL")

    args = parser.parse_args()

    if args.command == "migrate":
        from backend.app.db.migrations import run_upgrade_head
        print("Running database migrations to head...")
        run_upgrade_head()
        print("✅ Database migrations up to date.")
    elif args.command == "stamp":
        from backend.app.db.migrations import run_stamp_head
        print("Stamping database at head...")
        run_stamp_head()
        print("✅ Database stamped at head.")
    elif args.command == "start" or args.command is None:
        host = getattr(args, "host", settings.HOST)
        port = getattr(args, "port", settings.PORT)
        reload = getattr(args, "reload", False)
        print(f"Starting Parental Safety API on http://{host}:{port} ...")
        print(f"Interactive documentation: http://{host}:{port}/docs")
        uvicorn.run(
            "backend.app.main:app",
            host=host,
            port=port,
            reload=reload,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
