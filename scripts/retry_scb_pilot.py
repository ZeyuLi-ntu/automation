"""Repeat a pilot using identical frozen evidence and an isolated result folder."""
from __future__ import annotations

import argparse
import copy
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from market_rates.common import load, save
from market_rates.model_adapter import preflight
from market_rates.ollama_adapter import request_json
from market_rates.pipeline import check_evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source, target = Path(args.source_run).resolve(), Path(args.out).resolve()
    original = load(source / "run.json")
    if not (original.get("pilot") or {}).get("no_publication"):
        raise ValueError("This helper accepts non-publishing pilots only")
    check_evidence(original, source / "evidence")
    config = load(source / "config.snapshot.json")
    model_status = preflight(config)
    version = request_json(config, "/api/version")
    target.mkdir(parents=True, exist_ok=False)
    shutil.copytree(source / "evidence", target / "evidence")
    run = copy.deepcopy(original)
    empty = {"offers": [], "inventory": [], "coverage_complete": False, "unreadable": ["Extraction not run"]}
    run.update(id="scb-retry-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
               created_at=datetime.now(timezone.utc).isoformat(), retry_of=str(source),
               model_status=model_status, ollama_version=version, metadata=[],
               errors=load(source / "evidence/capture.json")["errors"],
               llm=copy.deepcopy(empty), vlm=copy.deepcopy(empty))
    save(target / "run.json", run)
    save(target / "config.snapshot.json", config)
    check_evidence(run, target / "evidence")
    print(f"Frozen evidence date: {run['as_of']}; service version: {version}", flush=True)
    subprocess.run([sys.executable, "-X", "utf8", "-m", "scripts.run_scb_pilot", "--out", str(target), "--resume"], check=True)


if __name__ == "__main__":
    main()
