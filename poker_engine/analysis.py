"""Анализ руки и диапазонов относительно борда.

- classify(): класс руки (сет, топ-пара, оверпара, ...) — то, как о руке говорят игроки;
- find_draws(): флеш-дро, стрит-дро (OESD/гатшот), бэкдоры, оверкарты;
- analyze_hand(): полный разбор руки игрока (комбинация, дро, ауты, вероятности, сила);
- count_outs(): ауты против конкретной руки или диапазона оппонента;
- range_breakdown(): из чего состоит диапазон на данном борде (готовые руки/дро/воздух),
  сколько комбинаций бьёт руку игрока и какие комбинации блокирует рука игрока.
"""
from __future__ import annotations

from itertools import combinations
from math import comb

from .cards import RANKS, cards_str, check_disjoint, rank_of, suit_of
from .evaluator import (FLUSH, FULL_HOUSE, QUADS, STRAIGHT, STRAIGHT_FLUSH, STRAIGHT_HIGH, TRIPS, TWO_PAIR,
                        best_five, evaluate, hand_name, score_ranks)
from .ranges import TOTAL_COMBOS, Range, combo_key, hand_label

STREETS = {0: "префлоп", 3: "флоп", 4: "терн", 5: "ривер"}

# Классы рук от сильных к слабым.
MADE_CLASSES = {
    "straight_flush": "Стрит-флеш",
    "quads": "Каре",
    "full_house": "Фулл-хаус",
    "flush": "Флеш",
    "straight": "Стрит",
    "set": "Сет",
    "trips": "Трипс",
    "two_pair": "Две пары",
    "overpair": "Оверпара",
    "top_pair": "Топ-пара",
    "second_pair": "Вторая пара",
    "weak_pair": "Слабая пара",
    "board": "Играет борд",
    "no_pair": "Без пары",
}
CLASS_STRENGTH = {key: len(MADE_CLASSES) - i for i, key in enumerate(MADE_CLASSES)}
CLASS_STRENGTH["board"] = 0  # карта, после которой герой «играет борд», — не улучшение

# Как делим «без пары» на флопе/терне.
DRAW_BUCKETS = {
    "combo_draw": "Комбо-дро (флеш + стрит)",
    "flush_draw": "Флеш-дро",
    "oesd": "Двустороннее стрит-дро (8 аутов)",
    "gutshot": "Гатшот (4 аута)",
    "overcards": "Две оверкарты",
    "air": "Воздух",
}
BUCKET_LABELS = {**MADE_CLASSES, **DRAW_BUCKETS}
BUCKET_ORDER = [k for k in MADE_CLASSES if k != "no_pair"] + list(DRAW_BUCKETS)

GROUPS = {
    "strong": ("Сильные (две пары и лучше)",
               {"straight_flush", "quads", "full_house", "flush", "straight", "set", "trips", "two_pair"}),
    "medium": ("Средние (оверпара, топ-пара)", {"overpair", "top_pair"}),
    "weak": ("Слабые готовые (вторая/слабая пара, играет борд)", {"second_pair", "weak_pair", "board"}),
    "draws": ("Дро без пары", {"combo_draw", "flush_draw", "oesd", "gutshot"}),
    "air": ("Воздух (оверкарты без дро и хуже)", {"overcards", "air"}),
}

DRAW_LABELS = {
    "nut_flush_draw": "Натсовое флеш-дро",
    "flush_draw": "Флеш-дро",
    "oesd": "Двустороннее стрит-дро (OESD / double gutshot)",
    "gutshot": "Гатшот",
    "backdoor_flush_draw": "Бэкдорное флеш-дро",
    "backdoor_straight_draw": "Бэкдорное стрит-дро",
    "two_overcards": "Две оверкарты",
    "one_overcard": "Одна оверкарта",
}


def _mask(cards) -> int:
    m = 0
    for c in cards:
        m |= 1 << rank_of(c)
    return m


def classify(hole: list[int], board: list[int], score: int | None = None) -> str:
    """Класс руки относительно борда (ключ из MADE_CLASSES)."""
    if score is None:
        score = evaluate(hole + board)
    cat = score >> 20
    if len(board) == 5 and score == evaluate(board):
        return "board"
    h1, h2 = rank_of(hole[0]), rank_of(hole[1])
    ranks = score_ranks(score)
    if cat == STRAIGHT_FLUSH:
        return "straight_flush"
    if cat == QUADS and ranks[0] in (h1, h2):
        return "quads"
    if cat == FULL_HOUSE and (h1 in ranks[:2] or h2 in ranks[:2]):
        return "full_house"
    if cat == FLUSH:
        return "flush"
    if cat == STRAIGHT:
        return "straight"
    if cat == TRIPS:
        n_hole = (h1 == ranks[0]) + (h2 == ranks[0])
        if n_hole == 2:
            return "set"
        if n_hole == 1:
            return "trips"

    board_ranks = {rank_of(c) for c in board}
    distinct = sorted(board_ranks, reverse=True)
    top = distinct[0] if distinct else -1
    second = distinct[1] if len(distinct) > 1 else -1
    if h1 == h2:
        if h1 > top:
            return "overpair"
        return "second_pair" if h1 > second else "weak_pair"
    paired = sorted((r for r in (h1, h2) if r in board_ranks), reverse=True)
    if len(paired) == 2 and cat == TWO_PAIR and set(ranks[:2]) == set(paired):
        return "two_pair"
    if paired:
        if paired[0] == top:
            return "top_pair"
        return "second_pair" if paired[0] == second else "weak_pair"
    return "no_pair"


def find_draws(hole: list[int], board: list[int], score: int | None = None,
               backdoors: bool = True) -> list[str]:
    """Дро руки на флопе/терне (ключи из DRAW_LABELS)."""
    if len(board) not in (3, 4):
        return []
    if score is None:
        score = evaluate(hole + board)
    cat = score >> 20
    draws: list[str] = []
    if cat >= FLUSH:
        return draws
    cards = hole + board

    has_fd = False
    for s in range(4):
        total = sum(1 for c in cards if suit_of(c) == s)
        in_hole = [rank_of(c) for c in hole if suit_of(c) == s]
        if not in_hole:
            continue
        if total == 4:
            on_board = {rank_of(c) for c in board if suit_of(c) == s}
            nut = max(r for r in range(13) if r not in on_board)
            draws.append("nut_flush_draw" if nut in in_hole else "flush_draw")
            has_fd = True
        elif total == 3 and len(board) == 3 and backdoors:
            draws.append("backdoor_flush_draw")
    if has_fd and "backdoor_flush_draw" in draws:
        draws.remove("backdoor_flush_draw")

    if cat < STRAIGHT:
        hero_mask, board_mask = _mask(cards), _mask(board)
        out_ranks = [r for r in range(13) if not hero_mask >> r & 1
                     and STRAIGHT_HIGH[hero_mask | 1 << r] > STRAIGHT_HIGH[board_mask | 1 << r]]
        if len(out_ranks) >= 2:
            draws.append("oesd")
        elif len(out_ranks) == 1:
            draws.append("gutshot")
        elif len(board) == 3 and backdoors:
            for r1, r2 in combinations([r for r in range(13) if not hero_mask >> r & 1], 2):
                extra = (1 << r1) | (1 << r2)
                if STRAIGHT_HIGH[hero_mask | extra] > STRAIGHT_HIGH[board_mask | extra]:
                    draws.append("backdoor_straight_draw")
                    break

    if classify(hole, board, score) == "no_pair":
        top = max(rank_of(c) for c in board)
        over = sum(1 for c in hole if rank_of(c) > top)
        if over == 2:
            draws.append("two_overcards")
        elif over == 1:
            draws.append("one_overcard")
    return draws


def _bucket(hole: list[int], board: list[int], score: int) -> str:
    cls = classify(hole, board, score)
    if cls != "no_pair":
        return cls
    if len(board) == 5:
        return "air"
    draws = find_draws(hole, board, score, backdoors=False)
    fd = "flush_draw" in draws or "nut_flush_draw" in draws
    sd = "oesd" in draws or "gutshot" in draws
    if fd and sd:
        return "combo_draw"
    if fd:
        return "flush_draw"
    if "oesd" in draws:
        return "oesd"
    if "gutshot" in draws:
        return "gutshot"
    if "two_overcards" in draws:
        return "overcards"
    return "air"


def hit_probability(outs: int, unseen: int, cards_to_come: int) -> float:
    """Вероятность получить хотя бы один аут за cards_to_come карт."""
    if outs <= 0:
        return 0.0
    if cards_to_come == 1:
        return outs / unseen
    return 1 - comb(unseen - outs, 2) / comb(unseen, 2)


def _odds_block(outs: int, unseen: int, board_len: int) -> dict:
    block = {"outs": outs, "next_card_pct": round(100 * hit_probability(outs, unseen, 1), 1)}
    if board_len == 3:
        block["by_river_pct"] = round(100 * hit_probability(outs, unseen, 2), 1)
        # «Правило 4 и 2»: на флопе ауты×4 до ривера (с поправкой при >8 аутов), ауты×2 на одну карту.
        block["rule_of_4_estimate_pct"] = min(100, outs * 4 - max(0, outs - 8))
    block["rule_of_2_estimate_pct"] = min(100, outs * 2)
    return block


def _pct(x: float, total: float) -> float:
    return round(100 * x / total, 1) if total else 0.0


def preflop_info(hole: list[int]) -> dict:
    from .preflop_table import PREFLOP_RANKING

    label = hand_label(combo_key(hole[0], hole[1]))
    cumulative = 0
    for i, (lab, equity) in enumerate(PREFLOP_RANKING):
        cumulative += 6 if len(lab) == 2 else (4 if lab[2] == "s" else 12)
        if lab == label:
            break
    r1, r2 = RANKS.index(label[0]), RANKS.index(label[1])
    features = []
    if r1 == r2:
        features.append("карманная пара")
    else:
        features.append("одномастная" if label[2] == "s" else "разномастная")
        gap = r1 - r2 - 1 if not (r1 == 12 and r2 <= 3) else r2  # A2-A5 — коннекторы через туз
        features.append("коннектор" if gap == 0 else f"гэп {gap}" if gap <= 3 else "несвязанная")
        if r2 >= 8:
            features.append("две бродвей-карты")
    return {
        "street": "префлоп",
        "hand": cards_str(hole),
        "hand_class": label,
        "features": features,
        "rank_of_169": i + 1,
        "top_percent": round(100 * cumulative / TOTAL_COMBOS, 1),
        "equity_vs_random_hand_pct": equity,
        "note": "Рейтинг по эквити all-in против случайной руки; реальные диапазоны открытия "
                "зависят от позиции и игроков — используй чарты/солвер.",
    }


def hand_strength(hole: list[int], board: list[int], score: int | None = None) -> dict:
    """Сила руки на текущем борде против всех возможных рук оппонента (без будущих карт)."""
    if score is None:
        score = evaluate(hole + board)
    known = set(hole) | set(board)
    unseen = [c for c in range(52) if c not in known]
    beats = ties = loses = 0
    beaten_by: dict[str, int] = {}
    for v in combinations(unseen, 2):
        vs = evaluate(list(v) + board)
        if vs < score:
            beats += 1
        elif vs == score:
            ties += 1
        else:
            loses += 1
            key = classify(list(v), board, vs)
            beaten_by[key] = beaten_by.get(key, 0) + 1
    total = beats + ties + loses
    return {
        "beats_pct": _pct(beats, total),
        "ties_pct": _pct(ties, total),
        "loses_pct": _pct(loses, total),
        "combos_that_beat_you": loses,
        "beaten_by": {MADE_CLASSES[k]: n for k, n in sorted(beaten_by.items(), key=lambda kv: -kv[1])},
        "is_nuts": loses == 0,
    }


def analyze_hand(hole: list[int], board: list[int]) -> dict:
    if len(hole) != 2:
        raise ValueError("Рука должна состоять из двух карт")
    if len(board) not in STREETS:
        raise ValueError("На борде должно быть 0, 3, 4 или 5 карт")
    check_disjoint(hole, board)
    if not board:
        return preflop_info(hole)

    score = evaluate(hole + board)
    cls = classify(hole, board, score)
    result: dict = {
        "street": STREETS[len(board)],
        "hand": cards_str(hole),
        "board": cards_str(board),
        "made_hand": hand_name(score),
        "best_five": cards_str(best_five(hole + board)),
        "hand_class": MADE_CLASSES[cls],
    }
    if len(board) < 5:
        draws = find_draws(hole, board, score)
        result["draws"] = [DRAW_LABELS[d] for d in draws]

        known = set(hole) | set(board)
        unseen = [c for c in range(52) if c not in known]
        improve: dict[str, list[int]] = {}
        for c in unseen:
            new_cls = classify(hole, board + [c])
            if CLASS_STRENGTH[new_cls] > CLASS_STRENGTH[cls]:
                improve.setdefault(new_cls, []).append(c)
        draw_outs = [c for k in ("straight", "flush", "straight_flush") for c in improve.get(k, [])]
        all_outs = [c for cards in improve.values() for c in cards]
        result["outs_to_improve"] = {
            MADE_CLASSES[k]: cards_str(sorted(v, reverse=True))
            for k, v in sorted(improve.items(), key=lambda kv: -CLASS_STRENGTH[kv[0]])
        }
        result["unseen_cards"] = len(unseen)
        if draw_outs:
            result["draw_completion"] = _odds_block(len(draw_outs), len(unseen), len(board))
        result["any_improvement"] = _odds_block(len(all_outs), len(unseen), len(board))
        result["note"] = ("Ауты — карты, улучшающие класс руки. Не все они гарантируют победу: "
                          "оппонент тоже может улучшиться. Для точного эквити используй calculate_equity.")
    result["hand_strength_vs_random"] = hand_strength(hole, board, score)
    return result


def showdown_share(hole: list[int], villain: Range, board: list[int]) -> float:
    """Доля банка против диапазона, если бы раздача закончилась прямо сейчас."""
    hero_score = evaluate(hole + board)
    total = won = 0.0
    for combo, w in villain.combos.items():
        vs = evaluate(list(combo) + board)
        total += w
        won += w if hero_score > vs else w / 2 if hero_score == vs else 0.0
    if total == 0:
        raise ValueError("Диапазон оппонента пуст после удаления известных карт")
    return won / total


def count_outs(hole: list[int], villain: Range, board: list[int]) -> dict:
    """Ауты на следующую карту против конкретной руки или диапазона оппонента."""
    if len(board) not in (3, 4):
        raise ValueError("Ауты считаются на флопе (3 карты) или терне (4 карты)")
    check_disjoint(hole, board)
    live = villain.without(hole + board)
    if not live.combos:
        raise ValueError("Диапазон оппонента пуст: все его руки заблокированы картами игрока/борда")
    known = set(hole) | set(board)
    if live.is_single():
        known |= set(next(iter(live.combos)))
    unseen = [c for c in range(52) if c not in known]

    now = showdown_share(hole, live, board)
    per_card = []
    for c in unseen:
        rest = live.without([c])
        if rest.combos:
            per_card.append((c, showdown_share(hole, rest, board + [c])))

    ahead = now > 0.5
    result: dict = {
        "street": STREETS[len(board)],
        "hand": cards_str(hole),
        "board": cards_str(board),
        "villain": str(live),
        "showdown_share_now_pct": round(100 * now, 1),
        "hero_ahead_now": ahead,
        "unseen_cards": len(unseen),
    }
    if not ahead:
        outs = sorted((c for c, s in per_card if s > 0.5), reverse=True)
        splits = sorted((c for c, s in per_card if s == 0.5), reverse=True)
        result["outs"] = {"cards": cards_str(outs), **_odds_block(len(outs), len(unseen), len(board))}
        if splits:
            result["split_outs"] = cards_str(splits)
    else:
        danger = sorted((c for c, s in per_card if s < 0.5), reverse=True)
        result["danger_cards"] = {"cards": cards_str(danger), **_odds_block(len(danger), len(unseen), len(board))}
    result["note"] = ("Аут — карта, после которой рука игрока впереди (против диапазона — выигрывает больше "
                      "половины банка на вскрытии). Вероятность «к риверу» предполагает, что набор аутов не "
                      "меняется; точное значение с учётом раннер-раннер даёт calculate_equity.")
    return result


def range_breakdown(villain: Range, board: list[int], hero: list[int] | None = None) -> dict:
    """Состав диапазона на борде + сравнение с рукой игрока и эффект блокеров."""
    if len(board) not in STREETS:
        raise ValueError("На борде должно быть 0, 3, 4 или 5 карт")
    if hero:
        check_disjoint(hero, board)
    live = villain.without(board)
    total_before_hero = live.total()
    blocked: dict[str, float] = {}
    if hero:
        for combo, w in live.combos.items():
            if combo[0] in hero or combo[1] in hero:
                key = _bucket(list(combo), board, evaluate(list(combo) + board)) if board else hand_label(combo)
                blocked[key] = blocked.get(key, 0.0) + w
        live = live.without(hero)
    total = live.total()
    if total == 0:
        raise ValueError("Диапазон пуст после удаления карт борда и руки игрока")

    result: dict = {"street": STREETS[len(board)], "range_combos": round(total, 2)}
    if board:
        result["board"] = cards_str(board)
    if hero:
        blocked_total = sum(blocked.values())
        result["blocked_by_hero"] = {"combos": round(blocked_total, 2)}

    if not board:
        pairs = sum(w for c, w in live.combos.items() if rank_of(c[0]) == rank_of(c[1]))
        suited = sum(w for c, w in live.combos.items()
                     if rank_of(c[0]) != rank_of(c[1]) and suit_of(c[0]) == suit_of(c[1]))
        result.update({
            "percent_of_all_hands": _pct(total_before_hero, TOTAL_COMBOS),
            "pairs_pct": _pct(pairs, total),
            "suited_pct": _pct(suited, total),
            "offsuit_pct": _pct(total - pairs - suited, total),
            "hands": ", ".join(lab if w == _full(lab) else f"{lab}({w:g}/{_full(lab)})"
                               for lab, w in live.label_weights().items()),
        })
        if hero:
            result["blocked_by_hero"]["by_hand"] = {k: round(v, 2) for k, v in blocked.items()}
        return result

    buckets: dict[str, float] = {}
    draws = {"flush_draw": 0.0, "oesd": 0.0, "gutshot": 0.0}
    hero_score = evaluate(hero + board) if hero else None
    beats = ties = loses = 0.0
    for combo, w in live.combos.items():
        hole = list(combo)
        score = evaluate(hole + board)
        key = _bucket(hole, board, score)
        buckets[key] = buckets.get(key, 0.0) + w
        if len(board) < 5:
            d = find_draws(hole, board, score, backdoors=False)
            if "flush_draw" in d or "nut_flush_draw" in d:
                draws["flush_draw"] += w
            if "oesd" in d:
                draws["oesd"] += w
            if "gutshot" in d:
                draws["gutshot"] += w
        if hero_score is not None:
            if score > hero_score:
                beats += w
            elif score == hero_score:
                ties += w
            else:
                loses += w

    result["classes"] = [
        {"class": BUCKET_LABELS[k], "combos": round(buckets[k], 2), "pct": _pct(buckets[k], total)}
        for k in BUCKET_ORDER if buckets.get(k)
    ]
    result["groups_pct"] = {label: _pct(sum(buckets.get(k, 0.0) for k in keys), total)
                            for label, keys in GROUPS.values()}
    if len(board) < 5:
        result["draws_in_range_pct"] = {
            "Флеш-дро (включая с готовой рукой)": _pct(draws["flush_draw"], total),
            "OESD": _pct(draws["oesd"], total),
            "Гатшот": _pct(draws["gutshot"], total),
        }
    if hero:
        result["vs_hero"] = {
            "hero_hand": cards_str(hero),
            "combos_beating_hero": round(beats, 2),
            "combos_tying": round(ties, 2),
            "combos_losing_to_hero": round(loses, 2),
            "hero_showdown_equity_pct": _pct(loses + ties / 2, total),
            "note": "Сравнение на текущем борде, как если бы сейчас было вскрытие. "
                    "На ривере это и есть эквити колла; на флопе/терне используй calculate_equity.",
        }
        result["blocked_by_hero"]["by_class"] = {
            BUCKET_LABELS.get(k, k): round(v, 2) for k, v in sorted(blocked.items(), key=lambda kv: -kv[1])
        }
    return result


def _full(label: str) -> int:
    return 6 if len(label) == 2 else (4 if label[2] == "s" else 12)
