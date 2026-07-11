from dataclasses import dataclass
from typing import List, Optional


@dataclass
class MarketSide:

    designation: str

    points: float | str

    old_american: int

    new_american: int

    old_decimal: float

    new_decimal: float


@dataclass
class MarketSnapshot:

    matchup_id: int

    match: str

    league: str

    market: str

    period: int

    points: float | str

    sides: List[MarketSide]


@dataclass
class MarketSignal:

    state: str

    direction: str

    match: str

    league: str

    market: str

    selection: str

    winner: Optional[MarketSide]

    loser: Optional[MarketSide]

    value_limit: Optional[float]

    movement: float

    dominance: float

    steam_score: float

    strength: str

    confidence: float