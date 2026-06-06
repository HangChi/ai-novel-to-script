import os

import main as backend_launcher


def test_backend_launcher_accepts_short_port_and_frontend_port() -> None:
    args = backend_launcher.build_parser().parse_args(["-p", "8010", "--frontend-port", "5174", "--reload"])

    assert args.port == 8010
    assert args.frontend_port == 5174
    assert args.reload


def test_backend_launcher_sets_frontend_port_before_starting(monkeypatch) -> None:
    call: dict[str, object] = {}

    def fake_run(app: str, **kwargs: object) -> None:
        call["app"] = app
        call["kwargs"] = kwargs
        call["frontend_port"] = os.getenv("FRONTEND_PORT")

    monkeypatch.delenv("FRONTEND_PORT", raising=False)
    monkeypatch.setattr(backend_launcher.uvicorn, "run", fake_run)

    backend_launcher.main(["-p", "8010", "--frontend-port", "5174"])

    assert call["app"] == "app.main:app"
    assert call["kwargs"] == {"host": "127.0.0.1", "port": 8010, "reload": False}
    assert call["frontend_port"] == "5174"


def test_backend_launcher_keeps_existing_frontend_port(monkeypatch) -> None:
    call: dict[str, object] = {}

    def fake_run(app: str, **kwargs: object) -> None:
        call["frontend_port"] = os.getenv("FRONTEND_PORT")

    monkeypatch.setenv("FRONTEND_PORT", "5179")
    monkeypatch.setattr(backend_launcher.uvicorn, "run", fake_run)

    backend_launcher.main(["-p", "8011"])

    assert call["frontend_port"] == "5179"
