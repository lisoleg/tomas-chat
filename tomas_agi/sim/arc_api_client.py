# -*- coding: utf-8 -*-
"""
ARC-AGI-3 API Client for TOMAS
==============================

**UPDATED v2.0**: Now delegates to the official arc-agi Python package.
The old REST API endpoints (arcprize.org/api/games/{id}/start) are deprecated.

For building static datasets, use: arc_agi3_dataset_builder.py
For evaluation, use: arc_agi3_eval.py

Usage:
    python arc_api_client.py --list-games
    python arc_api_client.py --game ls20 --output data/arc_agi3_ls20.json

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

logger = logging.getLogger(__name__)

# ============================================================
# Constants
# ============================================================

DEFAULT_ARC_BASE_URL = "https://arcprize.org"
GRID_SIZE = 64
NUM_COLORS = 16


# ============================================================
# ARC API Client
# ============================================================

class ARCAPIClient:
    """Client for the Arc Prize API to fetch ARC-AGI-3 environments."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: str = DEFAULT_ARC_BASE_URL,
        timeout: int = 30,
    ):
        self.api_key = api_key if api_key is not None else os.environ.get("ARC_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session = None

        if not self.api_key:
            logger.warning(
                "No ARC_API_KEY set. Set it via environment variable or --api-key. "
                "Get your key from https://arcprize.org/"
            )

    @property
    def session(self):
        """Lazy-init requests session."""
        if self._session is None:
            try:
                import requests
            except ImportError:
                raise ImportError(
                    "requests package required. Install with: pip install requests"
                )
            self._session = requests.Session()
            self._session.headers.update({
                "X-API-Key": self.api_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            })
        return self._session

    def list_games(self) -> List[str]:
        """List all available ARC-AGI-3 game IDs."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/games",
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            games = []
            for game in data:
                if isinstance(game, dict) and "game_id" in game:
                    games.append(str(game["game_id"]))
                elif isinstance(game, str):
                    games.append(game)
            logger.info(f"Found {len(games)} ARC-AGI-3 games: {games}")
            return games
        except Exception as e:
            logger.error(f"Failed to list games: {e}")
            return []

    def start_game(self, game_id: str) -> Dict[str, Any]:
        """Start a game and get the initial frame."""
        try:
            resp = self.session.post(
                f"{self.base_url}/api/games/{game_id}/start",
                json={},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to start game {game_id}: {e}")
            return {}

    def step_game(
        self,
        game_id: str,
        action: str,
        x: Optional[int] = None,
        y: Optional[int] = None,
        reasoning: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit an action to a game and get the next frame."""
        action_data: Dict[str, Any] = {"action": action}
        if x is not None and y is not None:
            action_data["x"] = x
            action_data["y"] = y
        if reasoning:
            action_data["reasoning"] = reasoning

        try:
            resp = self.session.post(
                f"{self.base_url}/api/games/{game_id}/step",
                json=action_data,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to step game {game_id}: {e}")
            return {}

    def get_game_info(self, game_id: str) -> Dict[str, Any]:
        """Get metadata for a specific game."""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/games/{game_id}",
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to get game info {game_id}: {e}")
            return {}

    def close(self):
        """Close the session."""
        if self._session:
            self._session.close()
            self._session = None


# ============================================================
# Dataset Builder
# ============================================================

def fetch_environment_snapshot(
    client: ARCAPIClient,
    game_id: str,
) -> Dict[str, Any]:
    """
    Fetch an environment snapshot from the ARC API.

    This captures the initial frame and game metadata.
    For full interactive evaluation, use the live API stepping.
    """
    logger.info(f"Fetching environment snapshot for game: {game_id}")

    # Get game info
    game_info = client.get_game_info(game_id)

    # Start game to get initial frame
    start_data = client.start_game(game_id)

    # Extract initial frame (64x64 grid)
    initial_frame = None
    if start_data:
        # Frame may be in different locations depending on API version
        frame_data = (
            start_data.get("frame")
            or start_data.get("observation")
            or start_data.get("grid")
            or {}
        )
        if isinstance(frame_data, dict) and "grid" in frame_data:
            initial_frame = frame_data["grid"]
        elif isinstance(frame_data, list):
            initial_frame = frame_data
        elif "grid" in start_data:
            initial_frame = start_data["grid"]

    # Build environment entry
    env = {
        "env_id": game_id,
        "source": "arc_prize_api",
        "game_info": {
            "title": game_info.get("title", game_id),
            "description": game_info.get("description", ""),
            "num_levels": game_info.get("num_levels", 5),
            "baseline_actions": game_info.get("baseline_actions", []),
            "tags": game_info.get("tags", []),
        },
        "levels": [
            {
                "level_id": 0,
                "initial_frame": initial_frame or [[0] * GRID_SIZE] * GRID_SIZE,
                "human_baseline": game_info.get("baseline_actions", [50])[0]
                if game_info.get("baseline_actions")
                else 50,
                "valid_actions": [
                    "key_up", "key_down", "key_left",
                    "key_right", "key_space", "undo", "cell_select",
                ],
                "api_metadata": {
                    "game_id": game_id,
                    "session_id": start_data.get("session_id", ""),
                    "state": start_data.get("state", "playing"),
                    "levels_completed": start_data.get("levels_completed", 0),
                },
            }
        ],
        "raw_start_response": start_data,
    }

    return env


def build_dataset_from_api(
    api_key: Optional[str] = None,
    game_ids: Optional[List[str]] = None,
    base_url: str = DEFAULT_ARC_BASE_URL,
) -> Dict[str, Any]:
    """
    Build a complete ARC-AGI-3 dataset from the API.

    Args:
        api_key: ARC API key (or from env ARC_API_KEY)
        game_ids: Specific game IDs to fetch (None = all)
        base_url: ARC API base URL

    Returns:
        Dataset dict with environments list
    """
    client = ARCAPIClient(api_key=api_key, base_url=base_url)

    # List games if not specified
    if game_ids is None:
        game_ids = client.list_games()
        if not game_ids:
            logger.error("No games available or API key invalid")
            return {"environments": [], "error": "No games available"}

    logger.info(f"Fetching {len(game_ids)} environments...")

    environments = []
    for i, game_id in enumerate(game_ids):
        logger.info(f"[{i+1}/{len(game_ids)}] Processing {game_id}...")
        try:
            env = fetch_environment_snapshot(client, game_id)
            environments.append(env)
        except Exception as e:
            logger.error(f"Failed to fetch {game_id}: {e}")
            environments.append({
                "env_id": game_id,
                "error": str(e),
                "source": "arc_prize_api",
            })

        # Rate limit: be nice to the API
        time.sleep(0.5)

    client.close()

    dataset = {
        "source": "arc_prize_api",
        "total_environments": len(environments),
        "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environments": environments,
    }

    logger.info(f"Dataset built: {len(environments)} environments")
    return dataset


# ============================================================
# CLI Entry Point
# ============================================================

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="ARC-AGI-3 API Client for TOMAS"
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="ARC API key (or set ARC_API_KEY env var)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=DEFAULT_ARC_BASE_URL,
        help="ARC API base URL",
    )
    parser.add_argument(
        "--list-games",
        action="store_true",
        help="List available game IDs and exit",
    )
    parser.add_argument(
        "--game",
        type=str,
        default=None,
        help="Specific game ID to fetch",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/arc_agi3_public.json",
        help="Output dataset JSON path",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=True,
    )

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
        )

    # Check API key
    api_key = args.api_key if args.api_key is not None else os.environ.get("ARC_API_KEY", "")
    if not api_key:
        print("=" * 60)
        print("ERROR: No ARC_API_KEY found!")
        print("=" * 60)
        print()
        print("To use this tool, you need an API key from arcprize.org")
        print()
        print("1. Visit https://arcprize.org/")
        print("2. Create an account / log in")
        print("3. Get your API key from the dashboard")
        print("4. Set it as an environment variable:")
        print()
        print("   export ARC_API_KEY=your_key_here")
        print()
        print("   Or pass it directly:")
        print("   python arc_api_client.py --api-key YOUR_KEY")
        print()
        print("=" * 60)
        sys.exit(1)

    # List games mode
    if args.list_games:
        client = ARCAPIClient(api_key=args.api_key, base_url=args.base_url)
        games = client.list_games()
        client.close()
        if games:
            print(f"\nFound {len(games)} ARC-AGI-3 games:")
            for i, g in enumerate(games, 1):
                print(f"  {i:2d}. {g}")
        else:
            print("No games found or API key invalid")
        return

    # Fetch specific game or all
    game_ids = [args.game] if args.game else None

    print(f"Fetching ARC-AGI-3 environments from {args.base_url}...")
    dataset = build_dataset_from_api(
        api_key=args.api_key,
        game_ids=game_ids,
        base_url=args.base_url,
    )

    # Save dataset
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(dataset, f, indent=2, ensure_ascii=False)

    print(f"\nDataset saved to: {args.output}")
    print(f"Total environments: {dataset['total_environments']}")

    # Print summary
    for env in dataset["environments"]:
        status = "OK" if "error" not in env else f"ERROR: {env['error']}"
        print(f"  {env['env_id']:20s}  {status}")


if __name__ == "__main__":
    main()
