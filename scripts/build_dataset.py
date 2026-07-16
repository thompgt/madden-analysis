"""Fuzzy-match Madden 26 ratings <-> real-world 2025 NFL stats/salary into one table.

There's no shared player ID between the Madden ratings (Kaggle/EA export) and
the nflverse tables (stats, contracts, bios), so matching is done by full
name similarity (rapidfuzz), blocked by team + broad position group to keep
the comparison space small and avoid false positives between different
players who share a name. NFL rosters are ~53 players/team, so team-blocked
name matching is far more constrained (and reliable) than fifa-analysis's
cross-league, age-blocked FC26<->Transfermarkt/Sofascore match.

The nflverse side is assembled first (stats + bios joined on `gsis_id`,
contracts joined on `gsis_id` where available), then that combined table is
fuzzy-matched to Madden.

Outputs:
  data/processed/madden_clean.csv     full Madden ratings dataset, lightly cleaned
  data/processed/players_merged.csv   Madden players matched to 2025 stats / salary
  data/processed/match_stats.json     match-rate diagnostics
"""

import json
import os
import unicodedata

import pandas as pd
from rapidfuzz import fuzz, process

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
PROC_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")

NAME_MATCH_THRESHOLD = 85

# Madden's granular position labels -> broad position group used for match blocking
# and for position-specific analysis in the notebooks.
MADDEN_POSITION_GROUP = {
    "Quarterback": "QB",
    "Halfback": "RB",
    "Fullback": "RB",
    "Wide Receiver": "WR",
    "Tight End": "TE",
    "Left Tackle": "OL",
    "Left Guard": "OL",
    "Center": "OL",
    "Right Guard": "OL",
    "Right Tackle": "OL",
    "Left Edge": "EDGE",
    "Right Edge": "EDGE",
    "Defensive Tackle": "DL",
    "Mike Backer": "LB",
    "Sam Backer": "LB",
    "Weak Backer": "LB",
    "Cornerback": "DB",
    "Free Safety": "DB",
    "Strong Safety": "DB",
    "Kicker": "ST",
    "Punter": "ST",
    "Long Snapper": "ST",
}

# nflverse (stats/contracts) position codes -> the same broad groups
NFLVERSE_POSITION_GROUP = {
    "QB": "QB",
    "RB": "RB",
    "FB": "RB",
    "WR": "WR",
    "TE": "TE",
    "OT": "OL",
    "OL": "OL",
    "G": "OL",
    "LG": "OL",
    "RG": "OL",
    "LT": "OL",
    "RT": "OL",
    "C": "OL",
    "DE": "EDGE",
    "ED": "EDGE",
    "OLB": "EDGE",
    "DT": "DL",
    "NT": "DL",
    "IDL": "DL",
    "DL": "DL",
    "LB": "LB",
    "ILB": "LB",
    "MLB": "LB",
    "CB": "DB",
    "DB": "DB",
    "S": "DB",
    "SAF": "DB",
    "FS": "DB",
    "K": "ST",
    "P": "ST",
    "LS": "ST",
}


def normalize_name(name):
    if pd.isna(name):
        return ""
    name = unicodedata.normalize("NFKD", str(name)).encode("ascii", "ignore").decode()
    name = name.lower().strip()
    for suffix in (" jr.", " jr", " sr.", " sr", " ii", " iii", " iv"):
        if name.endswith(suffix):
            name = name[: -len(suffix)].strip()
    return name


# Madden's roster export abbreviates the two New York teams ("NY Giants"/"NY Jets") while nflverse's
# team_name crosswalk uses the full name ("New York Giants"/"New York Jets"). Matching is blocked on exact
# team name, so without this fix those two teams' 132 players never match to any real stats/contracts at
# all (0%), not just at a lower rate -- a silent full-roster gap rather than ordinary match-rate noise.
MADDEN_TEAM_NAME_FIX = {
    "NY Giants": "New York Giants",
    "NY Jets": "New York Jets",
}


def load_madden():
    df = pd.read_csv(os.path.join(RAW_DIR, "Madden_26_Player_Ratings_Week-15.csv"))
    df["team"] = df["team"].replace(MADDEN_TEAM_NAME_FIX)
    df["position_group"] = df["position"].map(MADDEN_POSITION_GROUP).fillna("Other")
    df["name_norm"] = df["name"].map(normalize_name)
    return df


def load_teams():
    return pd.read_csv(os.path.join(RAW_DIR, "nfl_teams.csv"))


def load_nflverse_real(teams):
    abbr_to_name = dict(zip(teams["team_abbr"], teams["team_name"]))
    nick_to_name = dict(zip(teams["team_nick"], teams["team_name"]))

    stats = pd.read_csv(os.path.join(RAW_DIR, "nfl_player_stats_2025.csv"), low_memory=False)
    stats["team_name"] = stats["recent_team"].map(abbr_to_name)
    stats["position_group"] = stats["position"].map(NFLVERSE_POSITION_GROUP).fillna("Other")
    stats = stats.rename(columns={"player_id": "gsis_id"})

    players = pd.read_csv(os.path.join(RAW_DIR, "nfl_players.csv"), low_memory=False)
    bio_cols = ["gsis_id", "birth_date", "college_name", "height", "weight", "draft_year", "draft_round", "draft_pick"]
    players = players[bio_cols].rename(
        columns={"height": "height_in_bio", "weight": "weight_bio", "college_name": "college_bio"}
    )

    real = stats.merge(players, on="gsis_id", how="left")

    contracts = pd.read_csv(os.path.join(RAW_DIR, "nfl_contracts.csv"), low_memory=False)
    contracts = contracts[contracts["is_active"] == True].copy()  # noqa: E712
    contracts["team_name"] = contracts["team"].map(nick_to_name)
    contracts = contracts.sort_values("apy", ascending=False).drop_duplicates("gsis_id")
    contract_cols = ["gsis_id", "year_signed", "years", "value", "apy", "guaranteed", "apy_cap_pct"]
    contracts = contracts[contract_cols].rename(
        columns={"value": "contract_value", "years": "contract_years", "guaranteed": "contract_guaranteed"}
    )

    real = real.merge(contracts, on="gsis_id", how="left")
    real["name_norm"] = real["player_display_name"].map(normalize_name)
    return real


def fuzzy_match(left, right, left_block_cols, right_block_cols, right_name_col="name_norm"):
    """For each row in `left`, find the best-matching row index in `right`,
    restricted to candidates sharing the same value(s) of the blocking columns
    (`left_block_cols` on `left`, `right_block_cols` on `right`).
    Returns a Series of matched right-index (or NaN) aligned to left.index.
    """
    right_groups = {key: sub for key, sub in right.groupby(right_block_cols)}

    matched_idx = pd.Series(index=left.index, dtype="float64")
    scores = pd.Series(index=left.index, dtype="float64")

    for key, sub_left in left.groupby(left_block_cols):
        candidates = right_groups.get(key)
        if candidates is None or candidates.empty:
            continue
        choices = candidates[right_name_col].tolist()
        choice_idx = candidates.index.tolist()

        for i, name in sub_left["name_norm"].items():
            if not name:
                continue
            best = process.extractOne(name, choices, scorer=fuzz.token_sort_ratio)
            if best and best[1] >= NAME_MATCH_THRESHOLD:
                matched_idx.loc[i] = choice_idx[best[2]]
                scores.loc[i] = best[1]

    return matched_idx, scores


def main():
    os.makedirs(PROC_DIR, exist_ok=True)

    madden = load_madden()
    teams = load_teams()
    real = load_nflverse_real(teams)

    madden.to_csv(os.path.join(PROC_DIR, "madden_clean.csv"), index=False)

    match_idx, match_score = fuzzy_match(
        madden, real, ["team", "position_group"], ["team_name", "position_group"]
    )

    merged = madden.copy()
    merged["real_match_idx"] = match_idx
    merged["real_match_score"] = match_score

    real_cols = [c for c in real.columns if c not in ("team_name", "position_group", "name_norm")]
    real_lookup = real[real_cols].copy()
    real_lookup.columns = [f"real_{c}" if c != "gsis_id" else c for c in real_lookup.columns]
    merged = merged.join(real_lookup, on="real_match_idx")
    merged = merged.drop(columns=["real_match_idx"])

    merged.to_csv(os.path.join(PROC_DIR, "players_merged.csv"), index=False)

    stats = {
        "madden_players": int(len(madden)),
        "nflverse_real_players": int(len(real)),
        "nflverse_players_with_games_played": int((real["games"] > 0).sum()) if "games" in real.columns else None,
        "nflverse_players_with_contract": int(real["apy"].notna().sum()),
        "matched_to_real": int(merged["real_match_score"].notna().sum()),
        "matched_with_stats": int(merged["real_games"].notna().sum()) if "real_games" in merged.columns else None,
        "matched_with_contract": int(merged["real_apy"].notna().sum()) if "real_apy" in merged.columns else None,
    }
    stats["match_rate_pct"] = round(100 * stats["matched_to_real"] / stats["madden_players"], 2)
    with open(os.path.join(PROC_DIR, "match_stats.json"), "w") as f:
        json.dump(stats, f, indent=2)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
