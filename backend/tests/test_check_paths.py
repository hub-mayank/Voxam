"""scripts/check_paths.py: the file-ownership guard for teammates' branches."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_paths", ROOT / "scripts" / "check_paths.py")
check_paths = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_paths)
RULES = json.loads((ROOT / "docs" / "ownership.json").read_text())


def test_parth_may_change_the_faculty_screens_and_nothing_else():
    ok = ["frontend/src/faculty/pages/SessionList.tsx", "frontend/src/faculty/index.ts", "docs/CREDITS.md"]
    bad = ["frontend/src/student/Join.tsx", "backend/app/api/main.py", "frontend/package.json", "docs/openapi.json"]
    assert check_paths.violations("parth", ok, RULES) == []
    assert check_paths.violations("parth", ok + bad, RULES) == bad


def test_bhavesh_owns_the_student_screens_but_not_the_voice_sdk_or_session_hook():
    assert check_paths.violations("bhavesh", ["frontend/src/student/screens/Join.tsx"], RULES) == []
    sdk = ["frontend/src/student/voice/useVoiceSession.ts", "frontend/src/student/session/useStudentSession.ts"]
    assert check_paths.violations("bhavesh", sdk, RULES) == sdk


def test_tejas_owns_evidence_and_data_files():
    ok = ["config/question_bank.webdev.json", "evidence/wer/refs.csv", "scripts/wer.py", "docs/consent/register.csv", "docs/PRIVACY.md"]
    assert check_paths.violations("tejas", ok, RULES) == []
    assert check_paths.violations("tejas", ["backend/app/scorer.py"], RULES) == ["backend/app/scorer.py"]


def test_unknown_owner_is_an_error_not_a_pass():
    with pytest.raises(KeyError):
        check_paths.violations("nobody", ["README.md"], RULES)
