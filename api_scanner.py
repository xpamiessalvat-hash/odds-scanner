import requests
import time

previous_odds = {}

URL = (
    "https://guest.api.arcadia.pinnacle.com"
    "/0.1/leagues/29/markets/straight"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}


def american_to_decimal(price):

    if price > 0:

        return round(
            (price / 100) + 1,
            3
        )

    return round(
        (100 / abs(price)) + 1,
        3
    )


while True:

    print("\nLoop iniciat...\n")

    try:

        response = requests.get(
            URL,
            headers=HEADERS,
            timeout=30
        )

        data = response.json()

        for market in data:

            try:

                market_type = market.get("type")

                if market_type != "moneyline":
                    continue

                matchup_id = market.get(
                    "matchupId"
                )

                prices = market.get(
                    "prices",
                    []
                )

                for price_data in prices:

                    side = price_data.get(
                        "designation"
                    )

                    american_price = price_data.get(
                        "price"
                    )

                    decimal_odd = (
                        american_to_decimal(
                            american_price
                        )
                    )

                    key = (
                        f"{matchup_id}-"
                        f"{side}"
                    )

                    # DEBUG
                    print(
                        f"{key} | "
                        f"{decimal_odd}",
                        flush=True
                    )

                    # DETECTAR MOVIMENT
                    if key in previous_odds:

                        old_odd = previous_odds[key]

                        movement = (
                            (
                                old_odd
                                - decimal_odd
                            ) / old_odd
                        ) * 100

                        if abs(movement) >= 0.5:

                            print(
                                f"\n🔥 STEAM DETECTAT 🔥\n"
                                f"{key}\n"
                                f"{old_odd} -> "
                                f"{decimal_odd}\n"
                                f"{movement:.2f}%\n",
                                flush=True
                            )

                    previous_odds[key] = decimal_odd

            except Exception as e:

                print(
                    f"ERROR MARKET: {e}"
                )

    except Exception as e:

        print(f"ERROR API: {e}")

    time.sleep(30)