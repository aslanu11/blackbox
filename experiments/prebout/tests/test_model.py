from __future__ import annotations

import csv

from experiments.prebout import backtest, model as M


def test_predict_is_read_only():
    m = M.PreboutModel()
    p1 = m.predict("A", "B")
    p2 = m.predict("A", "B")
    assert p1 == p2 == 0.5  # no ratings, no matchup data -> a coin flip


def test_update_moves_winner_rating_up():
    m = M.PreboutModel()
    before = m.predict("A", "B")
    m.update("A", "B", winner="A")
    after = m.predict("A", "B")
    assert after > before
    assert m.ratings["a"] > m.ratings["b"]


def test_unknown_bot_defaults_to_even_odds():
    m = M.PreboutModel(ratings={"veteran": 1800.0})
    p = m.predict("veteran", "rookie")
    assert 0.5 < p < 1.0


def test_matchup_table_needs_repeated_pairs_to_move_much():
    m = M.PreboutModel(weapon_class={"a": "drum", "b": "flipper"})
    p_before = m.predict("a", "b")
    m.update("a", "b", winner="a")
    p_after_one = m.predict("a", "b")
    # one result should nudge it, but not swing it to near-certainty
    assert p_before < p_after_one < 0.75


def test_case_insensitive_lookup():
    m = M.PreboutModel()
    m.update("Sawblaze", "Huge", winner="Sawblaze")
    assert m.predict("sawblaze", "HUGE") == m.predict("Sawblaze", "Huge")


def test_load_roster_missing_file_is_empty(tmp_path):
    assert M.load_roster(tmp_path / "nope.csv") == {}


def test_load_roster_parses_weapon_class(tmp_path):
    path = tmp_path / "bots.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["name", "weapon_class", "weapon_text", "team"])
        w.writeheader()
        w.writerow({"name": "Bloodsport", "weapon_class": "hammer", "weapon_text": "hammersaw", "team": ""})
    roster = M.load_roster(path)
    assert roster == {"bloodsport": "hammer"}


def test_load_history_missing_dir_is_empty(tmp_path):
    assert M.load_history(tmp_path / "nope") == {}


def test_load_history_aggregates_wins(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    path = wiki_dir / "huge_history.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bot", "season", "opponent", "won", "method", "result_text", "time"])
        w.writeheader()
        w.writerow({"bot": "HUGE", "season": "1", "opponent": "X", "won": "True", "method": "ko", "result_text": "W", "time": ""})
        w.writerow({"bot": "HUGE", "season": "1", "opponent": "Y", "won": "False", "method": "jd", "result_text": "L", "time": ""})
    history = M.load_history(wiki_dir)
    assert history == {"huge": (1, 2)}


def test_load_history_ignores_unplayed_fixtures(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    path = wiki_dir / "bot_history.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bot", "season", "opponent", "won", "method", "result_text"])
        w.writeheader()
        w.writerow({"bot": "Bot", "season": "S", "opponent": "Played", "won": "True", "method": "ko", "result_text": "Won (KO)"})
        # Round-robin schedule row for a match that hasn't happened yet:
        # fandom's own text still fails startswith("w"), so `won` reads False.
        w.writerow({"bot": "Bot", "season": "S", "opponent": "Upcoming", "won": "False", "method": "", "result_text": "TBD"})
    history = M.load_history(wiki_dir)
    assert history == {"bot": (1, 1)}  # the TBD row must not count as a loss


def test_load_history_excludes_the_target_fight(tmp_path):
    wiki_dir = tmp_path / "wiki"
    wiki_dir.mkdir()
    path = wiki_dir / "bot_history.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["bot", "season", "opponent", "won", "method", "result_text"])
        w.writeheader()
        w.writerow({"bot": "Bot", "season": "S", "opponent": "Rival", "won": "True", "method": "ko", "result_text": "Won (KO)"})
    leaked = M.load_history(wiki_dir)
    assert leaked == {"bot": (1, 1)}
    clean = M.load_history(wiki_dir, exclude_pairs={frozenset({"bot", "rival"})})
    assert clean == {}  # the only recorded fight IS the one we're about to predict


def test_seeded_history_prior_favours_higher_win_rate():
    history = {"strong": (9, 10), "weak": (1, 10)}
    m = M.PreboutModel.seeded(history=history)
    assert m.ratings["strong"] > M.RATING_DEFAULT > m.ratings["weak"]


def test_comparison_rows_picks_and_scores_correctness():
    rows = [
        {
            "fight_id": "f1",
            "bots": ["A", "B"],
            "winner": "A",
            "prebout_p": 0.7,
            "outcome": 1,
            "momentum_earliest_p": None,
            "momentum_final_p": None,
        },
        {
            "fight_id": "f2",
            "bots": ["C", "D"],
            "winner": "D",
            "prebout_p": 0.6,
            "outcome": 0,
            "momentum_earliest_p": 0.3,
            "momentum_final_p": 0.9,
        },
    ]
    comp = backtest.comparison_rows(rows)
    assert comp[0]["generic_pick"] == "A"
    assert comp[0]["generic_correct"] is True
    assert comp[0]["main_pick"] is None
    assert comp[0]["main_correct"] is None
    assert comp[1]["generic_pick"] == "C"
    assert comp[1]["generic_correct"] is False
    assert comp[1]["main_pick"] == "D"
    assert comp[1]["main_correct"] is True


def test_backtest_writes_comparison_files(tmp_path):
    backtest.run(out_dir=tmp_path)
    assert (tmp_path / "comparison.json").exists()
    assert (tmp_path / "comparison.csv").exists()
    assert (tmp_path / "comparison.md").exists()


def test_backtest_runs_against_the_real_fixture(tmp_path):
    """Integration check: with no wiki/bots.csv data (the common case right
    now), this must still produce a report from fixture-001's real
    meta.json + telemetry.json, not raise."""
    report = backtest.run(out_dir=tmp_path)
    assert report["n_fights_with_result"] >= 1
    assert "prebout" in report
    assert 0.0 <= report["prebout"]["brier"] <= 1.0
    assert (tmp_path / "predictions.json").exists()
    assert (tmp_path / "backtest_report.json").exists()
