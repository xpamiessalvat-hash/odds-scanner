def american_to_decimal(odd):

    if odd > 0:
        return 1 + (odd / 100)

    return 1 + (100 / abs(odd))


def decimal_to_american(decimal):

    if decimal >= 2:
        return round((decimal - 1) * 100)

    return round(-100 / (decimal - 1))


def american_to_probability(odd):

    if odd > 0:
        return 100 / (odd + 100)

    return abs(odd) / (abs(odd) + 100)


def probability_to_decimal(probability):

    return 1 / probability
def calculate_edge(pinnacle_odd, bet365_odd):

    pinnacle_prob = american_to_probability(
        pinnacle_odd
    )

    bet365_prob = american_to_probability(
        bet365_odd
    )

    edge = (
        pinnacle_prob - bet365_prob
    ) * 100

    return round(edge, 2)