import random
from itertools import combinations

import pytest

from poker_engine.cards import parse_card, parse_cards
from poker_engine.evaluator import (FLUSH, FULL_HOUSE, PAIR, STRAIGHT, STRAIGHT_FLUSH, TWO_PAIR, category, evaluate,
                                    hand_name)


def ev(text: str) -> int:
    return evaluate(parse_cards(text))


def test_parse_cards_formats():
    assert parse_cards("AhKh") == parse_cards("Ah Kh") == parse_cards("A♥,K♥")
    assert parse_cards("10h9h") == parse_cards("Th9h")
    assert parse_card("2s") == 0 and parse_card("Ac") == 51
    with pytest.raises(ValueError):
        parse_cards("AhAh")
    with pytest.raises(ValueError):
        parse_cards("Ax")


def test_category_order():
    hands = ["AhKd9s7c2h", "AhAd9s7c2h", "AhAd9s9c2h", "AhAdAs7c2h", "5h6d7s8c9h", "Ah9h7h4h2h",
             "AhAdAs2c2h", "AhAdAsAc2h", "5h6h7h8h9h"]
    scores = [ev(h) for h in hands]
    assert scores == sorted(scores)
    assert [category(s) for s in scores] == list(range(9))


def test_wheel_is_lowest_straight():
    assert ev("Ah2d3s4c5h") < ev("2h3d4s5c6h")
    assert category(ev("Ah2d3s4c5h")) == STRAIGHT


def test_kickers():
    assert ev("AhAdKs7c2h") > ev("AhAdQs7c2h")
    assert ev("AhAdKsQcJh") == ev("AsAcKdQhJd")  # масти не важны
    assert ev("KhKd7s7c2h") > ev("KhKd6s6cAh")


def test_seven_cards():
    # стрит-флеш должен находиться в масти флеша, даже если есть другой стрит
    assert category(ev("9h8h7h6h5h4d3c")) == STRAIGHT_FLUSH
    assert category(ev("AhKhQhJh2h9dTc")) == FLUSH
    assert category(ev("AhAdAsKcKdKh2c")) == FULL_HOUSE  # две тройки
    assert category(ev("AhAdKsKcQdQh2c")) == TWO_PAIR
    assert ev("AhAdKsKcQdQh2c") == ev("AhAdKsKcQdJh2c")  # третья пара — лишь кикер Q


def test_matches_best_of_21_subsets():
    rng = random.Random(0)
    for _ in range(3000):
        cards = rng.sample(range(52), 7)
        assert evaluate(cards) == max(evaluate(c) for c in combinations(cards, 5))


def test_all_2598960_five_card_hands():
    # Эталон: число рук каждой категории и ровно 7462 различных по силе класса.
    counts = [0] * 9
    distinct = set()
    for hand in combinations(range(52), 5):
        score = evaluate(hand)
        counts[category(score)] += 1
        distinct.add(score)
    assert counts == [1302540, 1098240, 123552, 54912, 10200, 5108, 3744, 624, 40]
    assert len(distinct) == 7462
    assert category(ev("2h2d4s5c7h")) == PAIR


def test_hand_name():
    assert hand_name(ev("AhAd8s8cKh")) == "Две пары: тузы и восьмёрки, кикер K"
    assert hand_name(ev("AhKhQhJhTh")) == "Роял-флеш"
    assert hand_name(ev("Ah2d3s4c5h")) == "Стрит до пятёрки"
