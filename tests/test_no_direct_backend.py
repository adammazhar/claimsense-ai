"""No agent tool, and no co-pilot code, calls a client system directly: only the MCP door does (D-031).

Checked on the source: the co-pilot's modules may not import the client adapters or the mock systems,
nor name a backend URL. Compose adds the network boundary (the copilot isn't on the backend network).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src" / "claimsense"
COPILOT = ["api.py", "pipeline.py", "agent_defs.py", "door_client.py", "mock_brain.py", "guardrails.py",
           "deterministic.py"]
BACKEND_MODULES = {"clients", "mock_services", "door.server"}


def _imports(path: Path) -> set[str]:
    found = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            module = (node.module or "").lstrip(".")
            found.add(module.removeprefix("claimsense."))
            found |= {f"{module}.{a.name}".strip(".") for a in node.names}
        elif isinstance(node, ast.Import):
            found |= {a.name.removeprefix("claimsense.") for a in node.names}
    return found


@pytest.mark.parametrize("name", COPILOT)
def test_copilot_code_does_not_import_a_backend(name) -> None:
    imported = _imports(SRC / name)
    assert not {m for m in imported for b in BACKEND_MODULES if m == b or m.startswith(f"{b}.")}, name


@pytest.mark.parametrize("name", COPILOT)
def test_copilot_code_names_no_backend_url(name) -> None:
    text = (SRC / name).read_text(encoding="utf-8")
    for marker in ("CMS_URL", "PAS_URL", "DOCS_URL", ":8001", ":8002", ":8003"):
        assert marker not in text, (name, marker)


def test_the_compose_copilot_cannot_reach_the_backends() -> None:
    import yaml
    compose = yaml.safe_load((SRC.parent.parent / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]
    copilot_nets = set(services["copilot"]["networks"])
    for backend in ("cms", "pas", "documents"):
        assert not copilot_nets & set(services[backend]["networks"]), backend
        assert "ports" not in services[backend]
    assert set(services["door"]["networks"]) >= {"backend", "frontend"}
    assert not {k for k in services["copilot"].get("environment", {}) if k in ("CMS_URL", "PAS_URL", "DOCS_URL")}
