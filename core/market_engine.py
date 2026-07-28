from dataclasses import dataclass
from core.models import (
    MarketSnapshot,
    MarketSignal,
    MarketSide
)


class MarketEngine:

    def __init__(self):
        self.min_movement = 3.0
        self.min_dominance = 70.0
        self.debug = True

    def _debug(
        self,
        message
    ):

        if self.debug:

            print(
                message,
                flush=True
            )

    def _calculate_movement(
        self,
        old_decimal,
        new_decimal
    ):
        ...

        return round(
            (
                old_decimal - new_decimal
            )
            / old_decimal
            * 100,
            2
        )

    def _calculate_confidence(
        self,
        movement,
        dominance
    ):

        confidence = (
            movement * 10
            + dominance
        ) / 2

        return round(
            min(confidence, 100),
            1
        )
def analyze(
    self,
    snapshot: MarketSnapshot
) -> MarketSignal | None:

    if len(snapshot.sides) != 2:
        self._debug(
            f"DESCARTAT: sides={len(snapshot.sides)} | "
            f"{snapshot.match} | {snapshot.market}"
        )
        return None

    movements = []

    for side in snapshot.sides:

        movement = self._calculate_movement(
            side.old_decimal,
            side.new_decimal
        )

        movements.append(
            (
                side,
                movement
            )
        )

    # Només considerem moviments favorables (quota baixant)
    positive = [
        (side, movement)
        for side, movement in movements
        if movement > 0
    ]

    if not positive:
        self._debug(
            f"DESCARTAT: no hi ha moviments positius | "
            f"{snapshot.match} | {snapshot.market}"
        )
        return None

    winner, winner_move = max(
        positive,
        key=lambda x: x[1]
    )

    loser = next(
        side
        for side in snapshot.sides
        if side != winner
    )

    loser_move = self._calculate_movement(
        loser.old_decimal,
        loser.new_decimal
    )

    total = winner_move + max(
        loser_move,
        0
    )

    if total <= 0:
        self._debug(
            f"DESCARTAT: total={total:.2f} | "
            f"{snapshot.match}"
        )
        return None

    dominance = round(
        winner_move
        / total
        * 100,
        1
    )

    difference = round(
        winner_move - max(
            loser_move,
            0
        ),
        2
    )

    if difference < 2:
        self._debug(
            f"DESCARTAT: difference={difference:.2f}% | "
            f"{snapshot.match} | "
            f"Move={winner_move:.2f}% | "
            f"Loser={max(loser_move,0):.2f}%"
        )
        return None

    if winner_move < self.min_movement:

        self._debug(
            f"DESCARTAT: movement={winner_move:.2f}% "
            f"(mínim {self.min_movement}%) | "
            f"{snapshot.match}"
        )

        if winner_move >= 2.0:
            self._debug(
                f"NEAR STEAM | "
                f"{snapshot.league} | "
                f"{snapshot.match} | "
                f"Movement={winner_move:.2f}% "
                f"(mínim {self.min_movement}%)"
            )

        return None

    if dominance < self.min_dominance:

        self._debug(
            f"DESCARTAT: dominance={dominance:.1f}% "
            f"(mínim {self.min_dominance}%) | "
            f"{snapshot.match}"
        )

        if dominance >= 60:
            self._debug(
                f"NEAR STEAM | "
                f"{snapshot.league} | "
                f"{snapshot.match} | "
                f"Dominance={dominance:.1f}% "
                f"(mínim {self.min_dominance}%)"
            )

        return None

    confidence = self._calculate_confidence(
        winner_move,
        dominance
    )

    if winner.designation.lower() in (
        "over",
        "under",
        "home",
        "away"
    ):

        direction = winner.designation.lower()

    else:

        direction = winner.designation

    self._debug(
        f"STEAM ACCEPTAT | "
        f"{snapshot.league} | "
        f"{snapshot.match} | "
        f"{winner.designation} | "
        f"Move={winner_move:.2f}% | "
        f"Dom={dominance:.1f}%"
    )

    return MarketSignal(

        state="CLEAR_STEAM",

        direction=direction,

        match=snapshot.match,

        league=snapshot.league,

        market=snapshot.market,

        selection=winner.designation,

        winner=winner,

        loser=loser,

        value_limit=None,

        movement=winner_move,

        dominance=dominance,

        steam_score=round(
            confidence
        ),

        strength="PENDING",

        confidence=confidence

    )
@dataclass
class MarketAnalysis:

    winner: MarketSide

    loser: MarketSide

    movement: float

    dominance: float

    confidence: float

    direction: str