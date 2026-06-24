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