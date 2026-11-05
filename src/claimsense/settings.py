"""Runtime settings: model routing, timeouts, prices and paths. All overridable by environment."""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("CLAIMSENSE_DATA_DIR", REPO_ROOT / "data" / "synthetic"))

# Pipeline stages, in order. Coverage Check and Claim Assessment run in parallel.
DOCUMENT_INTAKE = "document_intake"
COVERAGE_CHECK = "coverage_check"
CLAIM_ASSESSMENT = "claim_assessment"
DECISION_DRAFT = "decision_draft"

# Model routing (D-017): the cheap model reads, the strong model decides what the wording means.
MODEL_ROUTING = {
    DOCUMENT_INTAKE: "gpt-4o-mini",
    COVERAGE_CHECK: "gpt-4o",
    CLAIM_ASSESSMENT: "gpt-4o-mini",
    DECISION_DRAFT: "gpt-4o",
}

# USD per million tokens. From public trackers, because OpenAI's own page refused automated reads;
# re-check against the OpenAI price sheet before quoting. Cost reports ignore the cached-input
# discount, so they slightly overstate spend.
PRICE_PER_MILLION = {
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
}

TOTAL_LOSS_THRESHOLD = "0.75"  # share of actual cash value; charter open question 2
STAGE_TIMEOUT_SECONDS = float(os.environ.get("STAGE_TIMEOUT_SECONDS", "30"))
MAX_AGENT_TURNS = 5
RETRIEVAL_TOP_K = 5
SEED_TOP_K = 2


def load_dotenv(path: Path = REPO_ROOT / ".env") -> None:
    """Load KEY=VALUE lines into the environment without overriding it. Never logs a value."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))
