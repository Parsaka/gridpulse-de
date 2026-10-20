"""Validate the PBIR report files against Microsoft's published JSON schemas (needs network).

Usage: python scripts/validate_pbir.py   (pip install jsonschema)
Schemas are cached in .cache/pbir-schemas. Offline structure checks live in tests/.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

CACHE = Path(".cache/pbir-schemas")
CACHE.mkdir(parents=True, exist_ok=True)


def fetch(uri: str) -> Resource:
    uri = uri.split("#")[0]
    f = CACHE / (hashlib.md5(uri.encode()).hexdigest() + ".json")
    if not f.exists():
        subprocess.run(["curl", "-s", "-f", "-o", str(f), uri], check=True)
    return Resource.from_contents(
        json.loads(f.read_text(encoding="utf-8")), default_specification=DRAFT7
    )


def main() -> int:
    registry = Registry(retrieve=fetch)
    files = [p for p in Path("powerbi/GridPulse.Report/definition").rglob("*.json")]
    bad = 0
    for p in files:
        doc = json.loads(p.read_text(encoding="utf-8"))
        validator = jsonschema.Draft7Validator(fetch(doc["$schema"]).contents, registry=registry)
        for e in sorted(validator.iter_errors(doc), key=lambda e: list(e.path))[:5]:
            bad += 1
            print(p, list(e.path), e.message[:300])
    print(f"checked {len(files)} files; errors: {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
