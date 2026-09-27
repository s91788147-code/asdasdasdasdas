import pytest

from poker_engine.cards import parse_cards
from poker_engine.ranges import Range, hand_label, parse_hand_or_range, top_percent_labels


@pytest.mark.parametrize("text, combos", [
    ("AA", 6), ("AKs", 4), ("AKo", 12), ("AK", 16), ("22+", 78), ("A2s+", 48), ("KTo+", 36),
    ("A5s-A2s", 16), ("99-66", 24), ("JTs-54s", 28), ("any", 1326), ("AhKh", 1), ("A10s", 4),
    ("QQ+, AKs, AKo", 34), ("aks, qq+", 22),
])
def test_combo_counts(text, combos):
    assert Range.parse(text).total() == combos


def test_weights_and_override():
    r = Range.parse("QQ+, AKs:0.5")
    assert r.total() == 20
    r = Range.parse("AA, AA:0.25")
    assert r.total() == 1.5


def test_top_percent():
    labels = top_percent_labels(10)
    assert labels[:3] == ["AA", "KK", "QQ"]
    assert abs(Range.parse("top10%").total() - 132.6) < 8
    assert Range.parse("top 100%").total() == 1326


def test_labels_and_blockers():
    a, b = parse_cards("AhKh")
    assert hand_label((a, b)) == "AKs"
    r = Range.parse("AA").without(parse_cards("Ah"))
    assert r.total() == 3


def test_parse_hand_or_range():
    assert parse_hand_or_range("AhKh").is_single()
    assert parse_hand_or_range("AK").total() == 16


@pytest.mark.parametrize("bad", ["", "XYZ", "AA:2", "AKs-Q9o", "AAs"])
def test_bad_input(bad):
    with pytest.raises(ValueError):
        Range.parse(bad)
