import requests
import time

print("API Scanner iniciat", flush=True)

previous_odds = {}

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

MATCHUPS_URL = (
    "https://guest.api.arcadia.pinnacle.com"
    "/0.1/sports/29/matchups/highlighted"
)


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
            "Obtenint matchup IDs...",
            flush=True
        )

        response = requests.get(
            MATCHUPS_URL,
            headers=HEADERS,
            timeout=30
        )

        print(
            f"STATUS MATCHUPS: "
            f"{response.status_code}",
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

        matchups = response.json()

        matchup_ids = []

        for matchup in matchups:

            matchup_id = matchup.get("id")

            if matchup_id:

                matchup_ids.append(matchup_id)

        print(
            f"Matchups trobats: "
            f"{len(matchup_ids)}",
            flush=True
        )

        # ITERAR MATCHUPS
        for matchup_id in matchup_ids:

            try:

                market_url = (
                    "https://guest.api.arcadia.pinnacle.com"
                    f"/0.1/matchups/"
                    f"{matchup_id}"
                    "/markets/related/straight"
                )

                response = requests.get(
                    market_url,
                    headers=HEADERS,
                    timeout=30
                )

                if response.status_code != 200:
                    continue

                markets = response.json()

                for market in markets:

                    try:

                        market_type = market.get(
                            "type"
                        )

                        prices = market.get(
                            "prices",
                            []
                        )

                        for price_data in prices:

                            side = price_data.get(
                                "designation"
                            )

                            american_price = (
                                price_data.get(
                                    "price"
                                )
                            )

                            if (
                                american_price
                                is None
                            ):
                                continue

                            decimal_odd = (
                                american_to_decimal(
                                    american_price
                                )
                            )

                            # IMPORTANT:
                            # diferenciar línies
                            points = price_data.get(
                                "points",
                                "NA"
                            )

                            key = (
                                f"{matchup_id}-"
                                f"{market_type}-"
                                f"{side}-"
                                f"{points}"
                            )

                            # DETECTAR MOVIMENT
                            if (
                                key
                                in previous_odds
                            ):

                                old_odd = (
                                    previous_odds[key]
                                )

                                movement = (
                                    (
                                        old_odd
                                        - decimal_odd
                                    ) / old_odd
                                ) * 100

                                # FILTRAR SOROLL
                                if (
                                    abs(movement)
                                    >= 0.5
                                ):

                                    print(
                                        f"\n🔥 "
                                        f"STEAM "
                                        f"DETECTAT "
                                        f"🔥\n"
                                        f"{key}\n"
                                        f"{old_odd} "
                                        f"-> "
                                        f"{decimal_odd}\n"
                                        f"{movement:.2f}%\n",
                                        flush=True
                                    )

                            previous_odds[key] = (
                                decimal_odd
                            )

                    except Exception as e:

                        print(
                            f"ERROR MARKET: "
                            f"{e}",
                            flush=True
                        )

            except Exception as e:

                print(
                    f"ERROR MATCHUP: "
                    f"{e}",
                    flush=True
                )

    except Exception as e:

        print(
            f"ERROR API: {e}",
            flush=True
        )

    time.sleep(30)