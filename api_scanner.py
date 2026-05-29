import requests
import time

print("API Scanner iniciat", flush=True)

previous_odds = {}

URL = (
    "https://guest.api.arcadia.pinnacle.com"
    "/0.1/leagues/29/markets/straight"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/137.0.0.0 "
        "Safari/537.36"
    ),
    "Accept": "application/json",
    "Origin": "https://www.pinnacle.com",
    "Referer": "https://www.pinnacle.com/",
    "Connection": "keep-alive"
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

    print("\nLoop iniciat...\n", flush=True)

    try:

        print(
            "Fent request API...",
            flush=True
        )

        response = requests.get(
            URL,
            headers=HEADERS,
            timeout=30
        )

        print(
            f"STATUS: {response.status_code}",
            flush=True
        )

        if response.status_code != 200:

            print(
                f"Resposta incorrecta: "
                f"{response.text[:500]}",
                flush=True
            )

            time.sleep(30)

            continue

        data = response.json()

        print(
            f"Markets rebuts: {len(data)}",
            flush=True
        )

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

                    if american_price is None:
                        continue

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
                    f"ERROR MARKET: {e}",
                    flush=True
                )

    except Exception as e:

        print(
            f"ERROR API: {e}",
            flush=True
        )

    time.sleep(30)