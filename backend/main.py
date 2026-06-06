from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Start the AI Novel to Script backend.")
    parser.add_argument("-p", "--port", type=int, default=int(os.getenv("BACKEND_PORT", "8000")), help="Backend port.")
    parser.add_argument("--host", default=os.getenv("BACKEND_HOST", "127.0.0.1"), help="Backend host.")
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=None,
        help="Frontend dev server port allowed by backend CORS.",
    )
    parser.add_argument("--reload", action="store_true", help="Restart the backend when files change.")

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.frontend_port is not None:
        os.environ["FRONTEND_PORT"] = str(args.frontend_port)
    elif not os.getenv("FRONTEND_PORT"):
        os.environ["FRONTEND_PORT"] = "5173"

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
