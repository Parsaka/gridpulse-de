"""Static checks for the Power BI semantic model (TMDL), no Power BI needed."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DEF = REPO / "powerbi/GridPulse.SemanticModel/definition"
TABLES = sorted((DEF / "tables").glob("*.tmdl"))
GOLD_SQL = REPO / "dbt/models/marts"


def test_model_references_every_table_file():
    model = (DEF / "model.tmdl").read_text(encoding="utf-8")
    refs = set(re.findall(r"^ref table (\w+)", model, re.M))
    assert refs == {p.stem for p in TABLES}


@pytest.mark.parametrize("path", TABLES, ids=lambda p: p.stem)
def test_every_measure_has_format_and_description(path):
    """TMDL has no `description:` property for measures; the description is a `///` comment
    directly above (Power BI's own parser rejects the property form)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    for i, line in enumerate(lines):
        if line.startswith("	measure "):
            assert i > 0 and lines[i - 1].startswith("	/// "), f"missing /// description: {line}"
            body = []
            for nxt in lines[i + 1 :]:
                if nxt.startswith("		"):
                    body.append(nxt)
                else:
                    break
            assert any(b.strip().startswith("formatString:") for b in body), f"no format: {line}"
    assert "description:" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("path", TABLES, ids=lambda p: p.stem)
def test_table_has_postgres_import_partition(path):
    text = path.read_text(encoding="utf-8")
    assert "PostgreSQL.Database(PgServer, PgDatabase)" in text
    assert f'Item="{path.stem}"' in text
    assert "mode: import" in text


def test_relationships_point_at_existing_columns():
    cols = {
        p.stem: set(re.findall(r"^\tcolumn (\w+)", p.read_text(encoding="utf-8"), re.M))
        for p in TABLES
    }
    rels = (DEF / "relationships.tmdl").read_text(encoding="utf-8")
    pairs = re.findall(r"fromColumn: (\w+)\.(\w+)\n\s+toColumn: (\w+)\.(\w+)", rels)
    assert len(pairs) == 4
    for t1, c1, t2, c2 in pairs:
        assert c1 in cols[t1], f"{t1}.{c1}"
        assert c2 in cols[t2], f"{t2}.{c2}"


def test_dax_measures_only_reference_declared_columns():
    cols = {
        p.stem: set(re.findall(r"^\tcolumn (\w+)", p.read_text(encoding="utf-8"), re.M))
        for p in TABLES
    }
    for path in TABLES:
        for table, col in re.findall(r"\b(\w+)\[(\w+)\]", path.read_text(encoding="utf-8")):
            if table in cols:  # skip measure references like [MAE Naive 24h]
                assert col in cols[table], f"{path.stem}: {table}[{col}] is not a column"


def test_dim_and_fact_columns_exist_in_dbt_models():
    """Cheap guard against drift between TMDL columns and the dbt gold models."""
    for name in ["dim_datetime", "dim_location", "fct_weather_hourly"]:
        sql = (GOLD_SQL / f"{name}.sql").read_text(encoding="utf-8")
        tmdl = (DEF / "tables" / f"{name}.tmdl").read_text(encoding="utf-8")
        for col in re.findall(r"^\tcolumn (\w+)", tmdl, re.M):
            if name == "dim_location" and col == "location_key":
                assert "location_key" in sql
            elif name == "fct_weather_hourly" or name == "dim_datetime":
                assert re.search(rf"\b{col}\b", sql), f"{name}: {col} not in dbt model"


def test_generated_files_are_in_sync_with_generator(tmp_path):
    shutil.copy(REPO / "scripts/gen_tmdl.py", tmp_path / "gen_tmdl.py")
    subprocess.run([sys.executable, "gen_tmdl.py"], cwd=tmp_path, check=True, capture_output=True)
    for generated in (tmp_path / "powerbi").rglob("*"):
        if generated.is_file():
            committed = REPO / generated.relative_to(tmp_path)
            assert committed.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8"), (
                f"{committed} differs from generator output; rerun scripts/gen_tmdl.py"
            )


def test_pbip_and_report_skeleton_are_valid_json():
    for rel in [
        "powerbi/GridPulse.pbip",
        "powerbi/GridPulse.SemanticModel/definition.pbism",
        "powerbi/GridPulse.Report/definition.pbir",
        "powerbi/GridPulse.Report/definition/report.json",
        "powerbi/GridPulse.Report/definition/pages/pages.json",
    ]:
        json.loads((REPO / rel).read_text(encoding="utf-8"))
    pages = json.loads(
        (REPO / "powerbi/GridPulse.Report/definition/pages/pages.json").read_text(encoding="utf-8")
    )
    for name in pages["pageOrder"]:
        assert (REPO / f"powerbi/GridPulse.Report/definition/pages/{name}/page.json").exists()
