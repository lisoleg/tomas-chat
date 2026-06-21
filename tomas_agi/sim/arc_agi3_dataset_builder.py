# -*- coding: utf-8 -*-
"""
ARC-AGI-3 Dataset Builder (v2 with arc-agi package)
===================================================

Uses the official arc-agi Python package to build a static dataset
for TOMAS offline evaluation.

Usage:
    python arc_agi3_dataset_builder.py --output data/arc_agi3_public.json
    python arc_agi3_dataset_builder.py --game ls20 --output data/arc_agi3_ls20.json

Author: TOMAS Team
Version: v2.0
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional

# Load .env first
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(env_path):
    with open(env_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, _, val = line.partition('=')
                key = key.strip()
                val = val.strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = val

logger = logging.getLogger(__name__)


def _silent_renderer(steps: int, frame_data) -> None:
    """No-op renderer to suppress stdout output."""
    pass


def _parse_action_name(action) -> str:
    """Convert GameAction enum to string name."""
    if hasattr(action, 'name'):
        return action.name
    # Integer action map
    action_map = {1: 'ACTION1', 2: 'ACTION2', 3: 'ACTION3', 4: 'ACTION4',
                  5: 'ACTION5', 6: 'ACTION6', 7: 'ACTION7', 8: 'ACTION8',
                  9: 'ACTION9', 10: 'ACTION10'}
    return action_map.get(int(action), f'ACTION{action}')


def build_dataset_from_arc_agi(
    game_ids: Optional[List[str]] = None,
    output_path: str = "data/arc_agi3_public.json",
) -> Dict[str, Any]:
    """
    Build a static dataset from the official arc-agi package.
    
    For each game, captures:
    - Game metadata (title, tags)
    - Initial frame (64x64 grid) from obs.frame[0]
    - Available actions (GameAction names)
    """
    try:
        import arc_agi
    except ImportError:
        logger.error("arc-agi package not installed. Run: pip install arc-agi")
        return {"environments": [], "error": "arc-agi not installed"}

    arc = arc_agi.Arcade(
        arc_api_key=os.environ.get("ARC_API_KEY", ""),
    )

    # List all environments
    envs = arc.get_environments()
    logger.info(f"Found {len(envs)} ARC-AGI-3 environments")

    if game_ids:
        envs = [e for e in envs if e.game_id.split("-")[0] in game_ids]
        logger.info(f"Filtered to {len(envs)} environments")

    environments = []
    for i, env_info in enumerate(envs):
        game_id = env_info.game_id
        logger.info(f"[{i+1}/{len(envs)}] Processing {game_id}...")

        try:
            # Create environment with silent renderer to suppress output
            env = arc.make(game_id, renderer=_silent_renderer)
            if env is None:
                logger.warning(f"  Could not create environment for {game_id}")
                environments.append({
                    "env_id": game_id,
                    "error": "env_creation_failed",
                    "source": "arc_prize_api",
                })
                continue

            # Get available actions
            actions = [_parse_action_name(a) for a in env.action_space] if hasattr(env, "action_space") else []
            
            # Get game info
            env_entry = {
                "env_id": game_id,
                "source": "arc_prize_api",
                "game_info": {
                    "title": env_info.title,
                    "description": getattr(env_info, "description", ""),
                    "tags": env_info.tags if hasattr(env_info, "tags") else [],
                },
                "action_space": actions,
                "levels": [],
            }

            # Capture initial observation via reset
            obs = env.reset()
            if obs and hasattr(obs, 'frame') and obs.frame:
                # obs.frame is a list of numpy arrays, one per level/index
                f_img = obs.frame[0]  # first level initial grid
                import numpy as np
                grid = f_img.tolist() if isinstance(f_img, np.ndarray) else _to_native(f_img)
                env_entry["levels"].append({
                    "level_id": 0,
                    "initial_frame": grid,
                    "human_baseline": 50,  # default
                    "valid_actions": actions,
                })
                logger.info(f"  Captured frame ({len(grid)}x{len(grid[0]) if grid else 0})")
            else:
                logger.warning(f"  No frame data for {game_id}")
                env_entry["levels"].append({
                    "level_id": 0,
                    "initial_frame": [[0] * 64] * 64,
                    "human_baseline": 50,
                    "valid_actions": actions,
                })

            # Close environment and scorecard
            try:
                arc.close_scorecard()
            except Exception:
                pass

            environments.append(env_entry)
            logger.info(f"  Done: {game_id}")

        except Exception as e:
            logger.error(f"  Failed to process {game_id}: {e}")
            try:
                arc.close_scorecard()
            except Exception:
                pass
            environments.append({
                "env_id": game_id,
                "error": str(e),
                "source": "arc_prize_api",
            })

        # Rate limit
        time.sleep(0.5)

    dataset = {
        "source": "arc_prize_api_v2",
        "total_environments": len(environments),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environments": environments,
    }

    # Save
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    logger.info(f"Dataset saved to {output_path}: {len(environments)} environments")
    return dataset


def _to_native(obj):
    """Convert numpy types to native Python types for JSON serialization."""
    import numpy as np
    if isinstance(obj, np.ndarray):
        return _to_native(obj.tolist())
    if isinstance(obj, list):
        return [_to_native(x) for x in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    return obj


def _extract_frame_data(obs) -> List[List[int]]:
    """Extract a 64x64 grid from an observation object."""
    # Try various attribute names
    for attr in ("frame", "grid", "observation", "frame_data", "frame_grid"):
        val = getattr(obs, attr, None)
        if val is not None:
            val = _to_native(val)
            if isinstance(val, list):
                if val and isinstance(val[0], list):
                    return val[:64]
                else:
                    # 1D flat array — reshape to 64x64
                    if len(val) >= 64*64:
                        return [val[i*64:(i+1)*64] for i in range(64)]
                    # Very short like 1 element? Just return as-is
                    return val
            return val if isinstance(val, list) else [val]  # type: ignore
    
    # Try __dict__
    if hasattr(obs, "__dict__"):
        d = {k: _to_native(v) for k, v in obs.__dict__.items()}
        for k, v in d.items():
            if isinstance(v, list) and v and isinstance(v[0], list):
                return v[:64]
            if isinstance(v, list) and v and isinstance(v[0], int) and len(v) >= 64*64:
                return [v[i*64:(i+1)*64] for i in range(64)]
    
    # Try to convert the observation itself
    val = _to_native(obs)
    if isinstance(val, list):
        if val and isinstance(val[0], list):
            return val[:64]
        if val and isinstance(val[0], int) and len(val) >= 64*64:
            return [val[i*64:(i+1)*64] for i in range(64)]
    
    return [[0] * 64] * 64


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="ARC-AGI-3 Dataset Builder v2")
    parser.add_argument("--output", type=str, default="data/arc_agi3_public.json")
    parser.add_argument("--game", type=str, default=None, help="Specific game ID")
    parser.add_argument("--verbose", action="store_true")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    
    api_key = os.environ.get("ARC_API_KEY", "")
    if not api_key:
        print("WARNING: No ARC_API_KEY set. Some games may not be available.")
    
    game_ids = [args.game] if args.game else None
    dataset = build_dataset_from_arc_agi(
        game_ids=game_ids,
        output_path=args.output,
    )
    
    # Summary
    ok = sum(1 for e in dataset["environments"] if "error" not in e)
    failed = sum(1 for e in dataset["environments"] if "error" in e)
    print(f"\nDataset: {ok} OK, {failed} failed, {len(dataset['environments'])} total")
    print(f"Saved to: {args.output}")


if __name__ == "__main__":
    main()
