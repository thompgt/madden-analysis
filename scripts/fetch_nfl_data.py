"""Pull real-world 2025 NFL data from the nflverse ecosystem via `nflreadpy`.

nflreadpy wraps the same open, community-maintained nflverse data releases
used by most public NFL analytics work (play-by-play, weekly/seasonal player
stats, rosters, and contracts sourced from Over The Cap). No auth needed.

Pulls four tables to data/raw/:
  nfl_player_stats_2025.csv   season-total per-player box score stats (reg season)
  nfl_players.csv             player bio/ID crosswalk (gsis_id, dob, college, position)
  nfl_contracts.csv           active contracts (value, APY, guarantees) via OTC
  nfl_teams.csv               team abbreviation <-> full name <-> nickname crosswalk

These share `gsis_id` (stats/players) or team nickname (contracts) as join
keys, which `build_dataset.py` uses to assemble one real-world player table
before fuzzy-matching it to the Madden ratings.
"""

import os

import nflreadpy as nfl

SEASON = 2025
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")


def main():
    os.makedirs(RAW_DIR, exist_ok=True)

    stats = nfl.load_player_stats(seasons=[SEASON], summary_level="reg")
    stats_path = os.path.join(RAW_DIR, "nfl_player_stats_2025.csv")
    stats.write_csv(stats_path)
    print(f"wrote {stats_path} ({stats.shape[0]} rows)")

    players = nfl.load_players()
    players_path = os.path.join(RAW_DIR, "nfl_players.csv")
    players.write_csv(players_path)
    print(f"wrote {players_path} ({players.shape[0]} rows)")

    contracts = nfl.load_contracts()
    # `cols` is a nested/list column (raw OTC column bookkeeping) that CSV can't represent
    contracts = contracts.drop("cols")
    contracts_path = os.path.join(RAW_DIR, "nfl_contracts.csv")
    contracts.write_csv(contracts_path)
    print(f"wrote {contracts_path} ({contracts.shape[0]} rows)")

    teams = nfl.load_teams()
    teams_path = os.path.join(RAW_DIR, "nfl_teams.csv")
    teams.write_csv(teams_path)
    print(f"wrote {teams_path} ({teams.shape[0]} rows)")


if __name__ == "__main__":
    main()
