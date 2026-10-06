"""Reproducible real pilot: the initial URL is read from 利率链接.xlsx D67."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_rates.common import load, save, digest
from market_rates.xlsx_read import read_xlsx
from market_rates.model_adapter import preflight, extract
from market_rates.capture import capture_sources
from market_rates.pipeline import evidence_index, evaluate, check_evidence
from market_rates.store import Store


def configuration(links):
    book = read_xlsx(links)
    sheet, cells = next(iter(book.items()))
    url = cells["D67"]
    if cells.get("A65") != "SCB" or "www.sc.com/sg/save/time-deposits/singapore-dollar-time-deposit/" not in url:
        raise ValueError("原始链接文件D67已变化，请重新核实来源映射")
    config = load("config/project.local.json")
    # Retain the complete offer region plus both pages of linked promotion T&Cs.
    config["models"].update({"max_text_chars": 18000, "max_images": 3, "num_ctx": 32768})
    config["expected_banks"] = ["SCB"]
    config["products"] = [{"id": "scb-sgd-fresh-funds", "bank": "SCB", "name": "Singapore Dollar Time Deposit Fresh Funds Promotion",
                           "personal_status": "present", "expected": True, "expected_tenors": ["6M"]}]
    config["sources"] = [{"id": "scb-link-workbook-d67", "bank": "SCB", "enabled": True,
                          "domains": ["www.sc.com", "av.sc.com"], "urls": [url],
                          "max_pages": 2, "max_depth": 1, "expand_selectors": [],
                          "capture_selectors": ["#sc-lb-module-fee-and-rate"],
                          "link_pattern": r"sg-sc-singapore-dollar-time-deposit-tnc-v1\.pdf"}]
    config["pilot"] = {"scope": "SCB SGD Fresh Funds promotion page and linked campaign terms only",
                       "input_workbook": str(Path(links).resolve()), "sheet": sheet, "cell": "D67",
                       "workbook_sha256": hashlib.sha256(Path(links).read_bytes()).hexdigest(),
                       "no_publication": True}
    return config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--links", default="../利率链接.xlsx")
    parser.add_argument("--out", required=True)
    parser.add_argument("--capture-only", action="store_true")
    parser.add_argument("--resume", action="store_true", help="Use frozen evidence in an existing pilot folder")
    args = parser.parse_args()
    folder = Path(args.out)
    if not args.resume:
        if folder.exists():
            raise ValueError("请用新目录保留每次试点证据；继续同一证据使用--resume")
        config = configuration(args.links)
        status = preflight(config)
        folder.mkdir(parents=True)
        save(folder / "config.snapshot.json", config)
        print("Capturing URL from workbook D67 and its linked promotion PDF...", flush=True)
        pages, errors = capture_sources(config, folder / "evidence")
        empty = {"offers": [], "inventory": [], "coverage_complete": False, "unreadable": ["Extraction not run"]}
        run = {"id": "scb-pilot-" + datetime.now().strftime("%Y%m%d-%H%M%S"),
               "as_of": datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
               "demo": False, "pages": pages, "errors": errors, "metadata": [], "model_status": status,
               "created_at": datetime.now(timezone.utc).isoformat(), "evidence_hash": digest(pages),
               "llm": empty, "vlm": empty, "pilot": config["pilot"]}
        save(folder / "run.json", run)
        evidence_index(pages, folder / "evidence")
        print(json.dumps({"pages": len(pages), "text_chars": sum(len(p["text"]) for p in pages),
                          "images": sum(len(p["images"]) for p in pages), "errors": errors}, ensure_ascii=False), flush=True)
    else:
        run = load(folder / "run.json")
        config = load(folder / "config.snapshot.json")
        check_evidence(run, folder / "evidence")
    if args.capture_only:
        return
    for lane in ("llm", "vlm"):
        rawfile = folder / f"model-{lane}.json"
        if rawfile.exists():
            saved = load(rawfile)
            run[lane] = saved["result"]
            continue
        started = datetime.now(timezone.utc)
        print(f"Running {lane} using local model, independent input...", flush=True)
        try:
            result, metadata = extract(lane, run["pages"], folder / "evidence", config, run["as_of"])
            metadata["elapsed_seconds"] = (datetime.now(timezone.utc) - started).total_seconds()
            save(rawfile, {"result": result, "metadata": metadata})
            run[lane] = result
            run["metadata"].append(metadata)
            run["errors"].extend(item for item in metadata.get("review_required", []) if item not in run["errors"])
            print(json.dumps({"lane": lane, "offers": len(result["offers"]), "coverage_complete": result["coverage_complete"],
                              "unreadable": result["unreadable"], "elapsed_seconds": metadata["elapsed_seconds"],
                              "contract": metadata.get("extraction_contract"), "review_required": metadata.get("review_required", [])}, ensure_ascii=False), flush=True)
        except Exception as exc:
            error = f"{lane}: {type(exc).__name__}: {exc}"
            run["errors"].append(error)
            run[lane] = {"offers": [], "inventory": [], "coverage_complete": False, "unreadable": [error]}
            save(folder / f"failure-{lane}-{started.strftime('%Y%m%dT%H%M%S')}.json",
                 {"lane": lane, "error": error, "elapsed_seconds": (datetime.now(timezone.utc) - started).total_seconds(),
                  "evidence_hash": run["evidence_hash"], "started_at": started.isoformat()})
            print(error, flush=True)
        save(folder / "run.json", run)
    store = Store(folder / "pilot.sqlite3")
    try:
        result = evaluate(folder, store)
        print(json.dumps({"pending": result["pending"], "approved_groups": len(result["groups"]),
                          "review": str(folder / "review.html")}, ensure_ascii=False), flush=True)
    finally:
        store.close()


if __name__ == "__main__":
    main()
