def american_to_decimal(odd):

	if odd > 0:
		return 1 + (odd / 100)

	return 1 + (100 / abs(odd))


def get_steam_level(movement_pct):

	if movement_pct >= 12:
		return "PLATINUM"

	if movement_pct >= 8:
		return "GOLD"

	if movement_pct >= 5:
		return "SILVER"

	return "BRONZE"

def calculate_value_limit(
    old_price,
    steam_price,
    movement
):

    if movement >= 20:

        retention = 0.65

    elif movement >= 15:

        retention = 0.55

    else:

        retention = 0.45

    value_limit = (
        steam_price
        + (
            old_price
            - steam_price
        ) * retention
    )

    return round(
        value_limit,
        3
    )


def calculate_baseball_steam_score(
    movement,
    market_type,
    hours_until_match
):

    movement_score = movement * 5

    market_weight = {
        "moneyline": 1.00,
        "spread": 1.15,
        "total": 1.10
    }.get(
        market_type,
        1
    )

    if hours_until_match <= 1:

        time_weight = 1.35

    elif hours_until_match <= 2:

        time_weight = 1.20

    else:

        time_weight = 1.00

    score = round(
        min(
            100,
            movement_score
            * market_weight
            * time_weight
        ),
        1
    )

    if score >= 85:

        strength = "ELITE"

    elif score >= 70:

        strength = "HIGH"

    elif score >= 55:

        strength = "MEDIUM"

    else:

        strength = "LOW"

    return score, strength
    return round(
        value_limit,
        3
    )