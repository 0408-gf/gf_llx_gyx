import pytest

from core.betting import Selection, expected_value, generate_combinations, kelly_fraction
from core.odds import implied_probabilities, market_analysis
from core.prediction import predict


def test_implied_and_normalized_probabilities():
    assert implied_probabilities(2, 4, 4) == (0.5, 0.25, 0.25)
    analysis = market_analysis(2, 3, 4)
    assert sum(analysis["normalized"]) == pytest.approx(1)
    assert analysis["margin"] == pytest.approx(1 / 2 + 1 / 3 + 1 / 4 - 1)


def test_ev_and_kelly():
    assert expected_value(.6, 2) == pytest.approx(.2)
    assert kelly_fraction(.6, 2, 1, 1) == pytest.approx(.2)
    assert kelly_fraction(.6, 2, .25, .03) == pytest.approx(.03)
    assert kelly_fraction(.4, 2) == 0


@pytest.mark.parametrize("odds", [0, 1, -2])
def test_invalid_odds(odds):
    with pytest.raises(ValueError): market_analysis(odds, 3, 3)
    with pytest.raises(ValueError): expected_value(.5, odds)


def test_prediction_sums_to_one():
    result = predict((.4, .3, .3), home_form=1, away_form=-1)
    assert result.home + result.draw + result.away == pytest.approx(1)


def test_accumulator_generation():
    items = [Selection(i, "主胜", .5, 2.1, .05, .6) for i in range(4)]
    assert len(generate_combinations(items, 2)) == 6
    assert len(generate_combinations(items, 3)) == 4
    assert len(generate_combinations(items, 4)) == 1
