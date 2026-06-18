#!/usr/bin/env python
"""
GAIA Dataset Fetcher for TOMAS
===============================

Downloads the GAIA benchmark dataset from HuggingFace and converts to
the JSON format expected by gaia_eval.py.

Requires:
  - HuggingFace token with access to gaia-benchmark/GAIA
  - Set via: export HF_TOKEN=your_token_here
  - Or: --token your_token_here

Usage:
    # Download and convert
    python gaia_fetcher.py --output data/gaia_real.json

    # Download specific split
    python gaia_fetcher.py --split validation --output data/gaia_val.json

    # Download with level filter
    python gaia_fetcher.py --level 1 --output data/gaia_level1.json

Author: TOMAS Team
Version: v1.0
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ============================================================
# Constants
# ============================================================

GAIA_HF_REPO = "gaia-benchmark/GAIA"
GAIA_CONFIG = "2023_all"
DEFAULT_OUTPUT = "data/gaia_real.json"

# ============================================================
# HuggingFace Download
# ============================================================


def download_via_datasets_library(
    token: str,
    split: str = "validation",
    cache_dir: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Download GAIA using the `datasets` library (preferred method)."""
    try:
        from datasets import load_dataset
    except ImportError:
        print("[GAIA] datasets library not installed. Trying pip install...")
        os.system(f"{sys.executable} -m pip install datasets")
        from datasets import load_dataset

    print(f"[GAIA] Downloading from HuggingFace (repo={GAIA_HF_REPO}, config={GAIA_CONFIG}, split={split})...")

    ds = load_dataset(
        GAIA_HF_REPO,
        GAIA_CONFIG,
        split=split,
        token=token,
        cache_dir=cache_dir,
        trust_remote_code=True,
    )

    instances = []
    for item in ds:
        instance = {
            "task_id": item.get("task_id", ""),
            "Question": item.get("Question", ""),
            "Answer": item.get("Answer", ""),
            "Level": item.get("Level", 1),
            "Annotator Metadata": item.get("Annotator Metadata", {}),
            "file_name": item.get("file_name", ""),
            "file_path": item.get("file_path", ""),
        }
        instances.append(instance)

    print(f"[GAIA] Downloaded {len(instances)} instances from {split} split")
    return instances


def download_via_hf_api(
    token: str,
    split: str = "validation",
) -> List[Dict[str, Any]]:
    """Download GAIA using HuggingFace Hub API directly (fallback)."""
    try:
        import urllib.request
        import tempfile
    except ImportError:
        pass

    # GAIA stores data as parquet files
    # Try to list files in the repo
    api_url = f"https://huggingface.co/api/datasets/{GAIA_HF_REPO}/tree/main"
    req = urllib.request.Request(api_url, headers={
        "Authorization": f"Bearer {token}",
        "User-Agent": "TOMAS-GAIA-Fetcher/1.0",
    })

    print(f"[GAIA] Listing files in {GAIA_HF_REPO}...")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        files = json.loads(resp.read().decode())
    except Exception as e:
        print(f"[GAIA] Failed to list files: {e}")
        print("[GAIA] The dataset may require accepting terms of use first.")
        print(f"[GAIA] Visit: https://huggingface.co/datasets/{GAIA_HF_REPO}")
        return []

    # Find parquet files for the requested split
    parquet_files = []
    for f in files:
        path = f.get("path", "")
        if path.endswith(".parquet") and split in path.lower():
            parquet_files.append(path)

    if not parquet_files:
        # Try looking in subdirectories
        for f in files:
            if f.get("type") == "directory":
                subdir = f["path"]
                sub_url = f"https://huggingface.co/api/datasets/{GAIA_HF_REPO}/tree/main/{subdir}"
                sub_req = urllib.request.Request(sub_url, headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "TOMAS-GAIA-Fetcher/1.0",
                })
                try:
                    sub_resp = urllib.request.urlopen(sub_req, timeout=30)
                    sub_files = json.loads(sub_resp.read().decode())
                    for sf in sub_files:
                        path = sf.get("path", "")
                        if path.endswith(".parquet") and split in path.lower():
                            parquet_files.append(path)
                except Exception:
                    pass

    if not parquet_files:
        print(f"[GAIA] No parquet files found for split '{split}'")
        print(f"[GAIA] Available files: {[f.get('path') for f in files]}")
        return []

    print(f"[GAIA] Found {len(parquet_files)} parquet file(s): {parquet_files}")

    # Download and convert each parquet file
    all_instances = []
    for pf in parquet_files:
        download_url = f"https://huggingface.co/datasets/{GAIA_HF_REPO}/resolve/main/{pf}"
        dl_req = urllib.request.Request(download_url, headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "TOMAS-GAIA-Fetcher/1.0",
        })

        print(f"[GAIA] Downloading {pf}...")
        try:
            dl_resp = urllib.request.urlopen(dl_req, timeout=120)
            content = dl_resp.read()

            # Save to temp file and read with pyarrow
            with tempfile.NamedTemporaryFile(suffix=".parquet", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                import pyarrow.parquet as pq
                table = pq.read_table(tmp_path)
                for row in table.to_pylist():
                    instance = {
                        "task_id": row.get("task_id", ""),
                        "Question": row.get("Question", ""),
                        "Answer": row.get("Answer", ""),
                        "Level": row.get("Level", 1),
                        "Annotator Metadata": row.get("Annotator Metadata", {}),
                        "file_name": row.get("file_name", ""),
                        "file_path": row.get("file_path", ""),
                    }
                    all_instances.append(instance)
            finally:
                os.unlink(tmp_path)

        except Exception as e:
            print(f"[GAIA] Failed to download {pf}: {e}")

    print(f"[GAIA] Total instances downloaded: {len(all_instances)}")
    return all_instances


# ============================================================
# Main
# ============================================================


def main():
    parser = argparse.ArgumentParser(description="GAIA Dataset Fetcher")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output JSON path")
    parser.add_argument("--split", default="validation", help="Dataset split (default: validation)")
    parser.add_argument("--level", type=int, default=0, help="Filter by level (0=all)")
    parser.add_argument("--token", default=None, help="HuggingFace token (or set HF_TOKEN env)")
    parser.add_argument("--method", choices=["datasets", "api"], default="datasets",
                        help="Download method (default: datasets)")
    parser.add_argument("--cache-dir", default=None, help="Cache directory for datasets library")

    args = parser.parse_args()

    # Get token
    token = args.token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    if not token:
        print("[GAIA] ERROR: No HuggingFace token provided!")
        print("[GAIA] Please set HF_TOKEN environment variable or use --token")
        print("[GAIA] Get your token from: https://huggingface.co/settings/tokens")
        print(f"[GAIA] Also accept terms at: https://huggingface.co/datasets/{GAIA_HF_REPO}")
        sys.exit(1)

    # Download
    if args.method == "datasets":
        instances = download_via_datasets_library(token, args.split, args.cache_dir)
    else:
        instances = download_via_hf_api(token, args.split)

    if not instances:
        print("[GAIA] No instances downloaded. Check token and dataset access.")
        sys.exit(1)

    # Filter by level
    if args.level > 0:
        instances = [i for i in instances if i.get("Level") == args.level]
        print(f"[GAIA] Filtered to Level {args.level}: {len(instances)} instances")

    # Save
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(instances, f, ensure_ascii=False, indent=2)

    print(f"\n[GAIA] Saved {len(instances)} instances to {output_path}")
    print(f"[GAIA] File size: {output_path.stat().st_size / 1024:.1f} KB")

    # Summary
    levels = {}
    for inst in instances:
        lv = inst.get("Level", 0)
        levels[lv] = levels.get(lv, 0) + 1
    print(f"[GAIA] Level distribution: {dict(sorted(levels.items()))}")


if __name__ == "__main__":
    main()
