from __future__ import annotations

from pathlib import Path

from evidence.adapters.oracles import ORACLES, normalise_result


REPOSITORY = Path(__file__).resolve().parents[2]


def test_closed_oracle_catalog_covers_project_gates_and_existing_sources() -> None:
    expected = {
        "difftest", "transpilediff", "stdcall_audit", "winediff", "winehash",
        "ehdiff", "gnuehdiff", "funcdiff", "cpudiff",
    }
    assert expected <= set(ORACLES)
    for name in expected:
        script = ORACLES[name].script
        assert script is not None
        assert (REPOSITORY / script).is_file(), name
    assert ORACLES["cpudiff"].command == ("cargo", "test", "--release", "--features", "unpack", "cpudiff")


def test_new_oracle_success_signatures_are_explicit_and_non_empty() -> None:
    cases = {
        "transpilediff": "transpile-pipeline equivalence: 4/4 opt-levels (12 functions, ref 19acad982194bf07)",
        "stdcall_audit": "stdcall-pop audit: PASS",
        "ehdiff": "MSVC EH differential: 6/6 fixtures",
        "gnuehdiff": "GNU/Itanium C++ EH differential: 3/3 fixtures",
        "cpudiff": "test result: ok. 5 passed; 0 failed",
    }
    for name, output in cases.items():
        assert normalise_result(ORACLES[name], 0, output, "", [], False) == "PASS"
        assert normalise_result(ORACLES[name], 0, output.replace("4/4", "0/4").replace("6/6", "0/6").replace("3/3", "0/3"), "", [], False) != "PASS" or name in {"stdcall_audit", "cpudiff"}


def test_missing_dependency_remains_skipped_for_new_oracle() -> None:
    assert normalise_result(ORACLES["ehdiff"], None, "", "", ["wine"], False) == "SKIPPED"
