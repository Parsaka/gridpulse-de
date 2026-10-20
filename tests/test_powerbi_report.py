"""Offline checks for the generated PBIR report: every field a visual binds exists in the model."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
REPORT = REPO / "powerbi/GridPulse.Report/definition"
TABLES = REPO / "powerbi/GridPulse.SemanticModel/definition/tables"


def _model() -> dict[str, dict[str, set[str]]]:
    out = {}
    for p in TABLES.glob("*.tmdl"):
        text = p.read_text(encoding="utf-8")
        out[p.stem] = {
            "columns": set(re.findall(r"^\tcolumn (\w+)", text, re.M)),
            "measures": set(re.findall(r"^\tmeasure '([^']+)'", text, re.M)),
        }
    return out


def _fields(node):
    """Yield (kind, entity, property) for every Column/Measure reference in a JSON tree."""
    if isinstance(node, dict):
        for kind in ("Column", "Measure"):
            if kind in node and "Property" in node[kind]:
                yield kind, node[kind]["Expression"]["SourceRef"]["Entity"], node[kind]["Property"]
        for v in node.values():
            yield from _fields(v)
    elif isinstance(node, list):
        for v in node:
            yield from _fields(v)


def test_visuals_bind_only_existing_fields():
    model = _model()
    visuals = list(REPORT.glob("pages/*/visuals/*/visual.json"))
    assert len(visuals) >= 25
    for path in visuals:
        for kind, entity, prop in _fields(json.loads(path.read_text(encoding="utf-8"))):
            assert entity in model, f"{path.parent.name}: unknown table {entity}"
            pool = model[entity]["columns" if kind == "Column" else "measures"]
            assert prop in pool, f"{path.parent.name}: {entity}[{prop}] is not a {kind.lower()}"


def test_pages_and_visual_names_are_unique_and_listed():
    pages = json.loads((REPORT / "pages/pages.json").read_text(encoding="utf-8"))
    assert len(set(pages["pageOrder"])) == len(pages["pageOrder"]) == 5
    for pid in pages["pageOrder"]:
        names = [
            json.loads(p.read_text(encoding="utf-8"))["name"]
            for p in (REPORT / "pages" / pid / "visuals").glob("*/visual.json")
        ]
        assert names and len(set(names)) == len(names)


def test_visuals_stay_inside_the_page():
    for path in REPORT.glob("pages/*/visuals/*/visual.json"):
        pos = json.loads(path.read_text(encoding="utf-8"))["position"]
        assert pos["x"] >= 0 and pos["y"] >= 0
        assert pos["x"] + pos["width"] <= 1280 and pos["y"] + pos["height"] <= 720, path.parent.name


def test_generated_report_is_in_sync_with_generator(tmp_path):
    shutil.copy(REPO / "scripts/gen_pbir.py", tmp_path / "gen_pbir.py")
    subprocess.run([sys.executable, "gen_pbir.py"], cwd=tmp_path, check=True, capture_output=True)
    for generated in (tmp_path / "powerbi").rglob("*.json"):
        committed = REPO / generated.relative_to(tmp_path)
        assert committed.read_text(encoding="utf-8") == generated.read_text(encoding="utf-8"), (
            f"{committed} differs from generator output; rerun scripts/gen_pbir.py"
        )
