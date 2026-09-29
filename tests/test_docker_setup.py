"""The 30-minute clean deployment (criterion C4a) — pinned, because it is tested literally.

Measured 2026-09-29 from a fresh clone with nothing cached: `docker compose up -d --build` to a
healthy app in 13 minutes. Each check below is a way that number, or the app inside the
container, silently broke before.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_torch_comes_from_the_cpu_index():
    """From PyPI, the x86_64 wheel pulls several GB of CUDA libraries the image never uses."""
    assert "download.pytorch.org/whl/cpu" in DOCKERFILE


def test_the_image_carries_the_browser_for_javascript_challenge_portals():
    """Without Chromium, Indonesia's portal (Cloudflare challenge) returns nothing in Docker."""
    assert "playwright install --with-deps chromium" in DOCKERFILE


def test_paddle_is_optional_so_a_first_build_stays_fast():
    assert "ARG INSTALL_PADDLE=0" in DOCKERFILE


def test_compose_runs_the_app_with_persistent_data():
    c = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    svc = c["services"]["veritrade"]
    assert "8501:8501" in svc["ports"]
    mounts = {v.split(":", 1)[1] for v in svc["volumes"]}
    # results + accounts DB, downloaded laws (the second pass re-reads them), models
    assert {"/app/outputs", "/app/data/cache", "/root/.cache/huggingface"} <= mounts
    # the app must start before a key is added, so .env is optional
    assert svc["env_file"][0]["required"] is False


def test_line_endings_stay_unix_on_windows_checkouts():
    attrs = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    for pattern in ("Dockerfile", "docker-compose.yml", "*.sh"):
        assert any(line.split()[:1] == [pattern] and "eol=lf" in line
                   for line in attrs.splitlines()), pattern


def test_secrets_and_private_archives_never_enter_the_build_context():
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").split()
    assert ".env" in ignore and "*.zip" in ignore
