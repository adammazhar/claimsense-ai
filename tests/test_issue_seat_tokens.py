"""The seat-token issuer: hashes only in the registry, only its own lines in .env, never a token printed."""

from __future__ import annotations

import json

import issue_seat_tokens as tool
from claimsense.contracts import SeatRegistry
from claimsense.door import SeatStore

ROSTER = [{"user_id": "adj-001", "role": "adjuster_pd"}, {"user_id": "adj-004", "role": "adjuster_bi"}]
ORIGINAL_ENV = "# my settings\nOPENAI_API_KEY=sk-keep-me\nOTHER=1\nSEAT_TOKEN_ADJ_001=old\nSEAT_TOKEN_GONE_009=stale\n"


def _run(tmp_path, *extra):
    roster = tmp_path / "roster.json"
    roster.write_text(json.dumps(ROSTER), encoding="utf-8")
    return tool.main(["--roster", str(roster), "--registry", str(tmp_path / "runtime" / "seats.json"),
                      "--env", str(tmp_path / ".env"), "--backups", str(tmp_path / "backups"), *extra])


def _env(tmp_path) -> dict[str, str]:
    lines = (tmp_path / ".env").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if "=" in line and not line.startswith("#"))


def test_only_seat_lines_change_and_env_is_backed_up(tmp_path) -> None:
    (tmp_path / ".env").write_text(ORIGINAL_ENV, encoding="utf-8")
    assert _run(tmp_path) == 0
    env = _env(tmp_path)
    assert env["OPENAI_API_KEY"] == "sk-keep-me" and env["OTHER"] == "1"
    assert env["SEAT_TOKEN_ADJ_001"] != "old" and env["SEAT_TOKEN_ADJ_004"].startswith("csk_")
    assert env["SEAT_TOKEN_GONE_009"] == "stale", "a line the tool did not write this time is left alone"
    assert (tmp_path / ".env").read_text(encoding="utf-8").startswith("# my settings\nOPENAI_API_KEY=sk-keep-me\n")
    backups = list((tmp_path / "backups").glob(".env.bak-*"))
    assert len(backups) == 1 and backups[0].read_text(encoding="utf-8") == ORIGINAL_ENV


def test_a_missing_env_is_created_without_a_backup(tmp_path) -> None:
    assert _run(tmp_path) == 0
    assert set(_env(tmp_path)) == {"SEAT_TOKEN_ADJ_001", "SEAT_TOKEN_ADJ_004"}
    assert not (tmp_path / "backups").exists()


def test_the_registry_holds_hashes_the_door_accepts(tmp_path) -> None:
    _run(tmp_path)
    path = tmp_path / "runtime" / "seats.json"
    text = path.read_text(encoding="utf-8")
    SeatRegistry.model_validate_json(text)
    store = SeatStore(path=path)
    for user, token in ((k, v) for k, v in _env(tmp_path).items()):
        assert token not in text
        assert store.resolve(token).user_id == {"SEAT_TOKEN_ADJ_001": "adj-001", "SEAT_TOKEN_ADJ_004": "adj-004"}[user]


def test_revoke_takes_the_seat_out(tmp_path) -> None:
    _run(tmp_path)
    token = _env(tmp_path)["SEAT_TOKEN_ADJ_004"]
    assert _run(tmp_path, "--revoke", "adj-004") == 0
    assert "SEAT_TOKEN_ADJ_004" not in _env(tmp_path)
    assert SeatStore(path=tmp_path / "runtime" / "seats.json").resolve(token) is None


def test_nothing_printed_is_a_token(tmp_path, capsys) -> None:
    _run(tmp_path)
    out = capsys.readouterr().out
    assert "adj-004" in out and "sha256" in out
    for token in _env(tmp_path).values():
        assert token not in out
