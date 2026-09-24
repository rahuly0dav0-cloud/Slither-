import pandas as pd
import pytest

from config.settings import QCConfig
from src.qc.comparison import cell_comparison_frame
from src.qc.engine import run_dataset_qc
from src.qc.result import Status
from src.reporting.excel_report import (
    SHEET_CELL,
    SHEET_PY,
    SHEET_SAS,
    SHEET_SUMMARY,
    write_report,
)


def _base_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ID": [1, 2, 3, 4],
            "AGE": [42, 37, 55, 29],
            "BALANCE": [100.0, 250.5, 99.99, 0.0],
            "NAME": ["ann", "bob", "cara", "dan"],
        }
    )


def test_identical_frames_pass():
    df = _base_frame()
    result = run_dataset_qc("customers", df.copy(), df.copy(), key_columns=["ID"])
    assert result.status is Status.PASS
    assert result.cell.mismatched == 0
    assert result.summary.status is Status.PASS


def test_single_cell_diff_fails_and_is_captured():
    sas = _base_frame()
    py = _base_frame()
    py.loc[1, "AGE"] = 38  # off by one
    result = run_dataset_qc("customers", sas, py, key_columns=["ID"])
    assert result.status is Status.FAIL
    assert result.cell.mismatched == 1
    mm = result.cell.mismatches[0]
    assert mm.column == "AGE"
    assert mm.row_key == "2"  # ID of the changed row


def test_key_alignment_handles_shuffled_rows():
    sas = _base_frame()
    py = _base_frame().sample(frac=1, random_state=1).reset_index(drop=True)
    result = run_dataset_qc("customers", sas, py, key_columns=["ID"])
    assert result.status is Status.PASS


def test_fallback_sort_alignment_without_keys():
    sas = _base_frame()
    py = _base_frame().sample(frac=1, random_state=2).reset_index(drop=True)
    result = run_dataset_qc("customers", sas, py)  # no keys -> sort-positional
    assert result.cell.alignment == "sorted-positional"
    assert result.status is Status.PASS


def test_case_insensitive_column_alignment():
    sas = _base_frame()
    py = _base_frame().rename(columns={"AGE": "age", "BALANCE": "Balance"})
    result = run_dataset_qc("customers", sas, py, key_columns=["ID"])
    assert result.status is Status.PASS
    assert not result.summary.columns_only_in_sas


def test_numeric_tolerance():
    sas = _base_frame()
    py = _base_frame()
    py.loc[0, "BALANCE"] = 100.0 + 1e-9  # within default tolerance
    result = run_dataset_qc("customers", sas, py, key_columns=["ID"])
    assert result.status is Status.PASS

    tight = QCConfig(abs_tol=1e-12, rel_tol=1e-12)
    result2 = run_dataset_qc("customers", sas, py, key_columns=["ID"], config=tight)
    assert result2.status is Status.FAIL


def test_row_count_mismatch_flagged():
    sas = _base_frame()
    py = _base_frame().iloc[:3]
    result = run_dataset_qc("customers", sas, py, key_columns=["ID"])
    assert result.summary.row_count.status is Status.FAIL
    assert result.status is Status.FAIL


def test_missing_column_detected():
    sas = _base_frame()
    py = _base_frame().drop(columns=["NAME"])
    result = run_dataset_qc("customers", sas, py, key_columns=["ID"])
    assert "NAME" in result.summary.columns_only_in_sas
    assert result.status is Status.FAIL


def test_write_report_creates_four_sheets(tmp_path):
    sas = _base_frame()
    py = _base_frame()
    py.loc[2, "BALANCE"] = 12345.0
    result = run_dataset_qc("customers", sas, py, key_columns=["ID"])

    out = tmp_path / "qc_customers.xlsx"
    write_report(result, out)
    assert out.exists()

    xls = pd.ExcelFile(out)
    assert set(xls.sheet_names) == {SHEET_SAS, SHEET_PY, SHEET_SUMMARY, SHEET_CELL}


def test_both_nan_matches():
    sas = pd.DataFrame({"ID": [1, 2], "X": [1.0, None]})
    py = pd.DataFrame({"ID": [1, 2], "X": [1.0, None]})
    result = run_dataset_qc("d", sas, py, key_columns=["ID"])
    assert result.status is Status.PASS


def test_cell_comparison_frame_includes_matches_and_lists_fails_first():
    sas = _base_frame()
    py = _base_frame()
    py.loc[2, "BALANCE"] = 12345.0  # one mismatch
    frame = cell_comparison_frame(sas, py, key_columns=["ID"])

    # Every compared (non-key) cell is present, not just the mismatch.
    assert len(frame) == len(sas) * 3  # AGE, BALANCE, NAME
    assert (frame["status"] == "PASS").sum() == len(sas) * 3 - 1
    # The single FAIL row is at the top with a real value comparison.
    top = frame.iloc[0]
    assert top["status"] == "FAIL"
    assert top["column"] == "BALANCE"
    assert top["sas_value"] == 99.99 and top["python_value"] == 12345.0

