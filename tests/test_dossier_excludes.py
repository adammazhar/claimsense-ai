"""Access metadata and fraud details never reach a model (D-034, D-038).

claim_line only scopes access, and an SIU referral would hand the model the ROUTE answer. Both are
in the CMS record; neither may appear in any stage's input. Checked on the captured model inputs, as a
supervisor (who may see the referral) on the one referred claim, and as the BI adjuster on a BI claim.
"""

from __future__ import annotations

import pytest

from claimsense import mock_brain
from claimsense.mock_brain import MockBrain
from claimsense.pipeline import DOSSIER_EXCLUDES_CLAIM, DOSSIER_EXCLUDES_POLICY
from conftest import ADJ_BI, FLAG_CLAIM, SIU_CLAIM, SUPERVISOR, Stack

FORBIDDEN = ["claim_line", "siu_referral", "siu_referred", "physical_damage", "bodily_injury", "legacy_rule",
             "referral threshold", "status_field"]


@pytest.mark.parametrize(("claim_id", "seat"), [(SIU_CLAIM, SUPERVISOR), (FLAG_CLAIM, ADJ_BI)])
def test_no_stage_sees_access_metadata_or_fraud_details(run, monkeypatch, claim_id, seat) -> None:
    seen: list[str] = []
    original = mock_brain.MockModel.get_response

    async def capture(self, system_instructions, input, *args, **kwargs):
        seen.append(f"{system_instructions}\n{input}")
        return await original(self, system_instructions, input, *args, **kwargs)

    monkeypatch.setattr(mock_brain.MockModel, "get_response", capture)
    response = run(Stack(MockBrain()).recommend(claim_id, seat))
    assert response.status_code == 200
    assert len(seen) >= 4
    for text in seen:
        for word in FORBIDDEN:
            assert word not in text, word


def test_the_exclusions_are_the_ones_documented() -> None:
    assert DOSSIER_EXCLUDES_CLAIM == {"claim_line", "siu_referral"}
    assert DOSSIER_EXCLUDES_POLICY == {"status_field"}
