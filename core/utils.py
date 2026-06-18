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

