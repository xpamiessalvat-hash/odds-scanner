from dataclasses import dataclass
from typing import List


@dataclass
class MarketSide:

    designation: str

    points: float

    old_decimal: float

    new_decimal: float

    movement: float


@dataclass
class MarketSnapshot:

    matchup_id: int

    match: str

    league: str

    market: str

    period: int

    points: float

    sides: List[MarketSide]


@dataclass
class MarketSignal:

    state: str

    winner: MarketSide | None

    loser: MarketSide | None

    movement: float

    dominance: float

    steam_score: float

    strength: str

    value_limit: float | None

    confidence: float