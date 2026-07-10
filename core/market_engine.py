from core.models import (
    MarketSnapshot,
    MarketSignal,
    MarketSide
)


class MarketEngine:

    def __init__(self):

        self.min_movement = 3.0
        self.min_dominance = 70.0

    def analyze(
        self,
        snapshot: MarketSnapshot
    ) -> MarketSignal:

        if len(snapshot.sides) != 2:
            return None

        side1 = snapshot.sides[0]
        side2 = snapshot.sides[1]

        winner = (
            side1
            if side1.movement >= side2.movement
            else side2
        )

        loser = (
            side2
            if winner is side1
            else side1
        )

        total = (
            winner.movement
            + loser.movement
        )

        if total == 0:
            return None

        dominance = round(
            winner.movement
            / total
            * 100,
            1
        )

        return None