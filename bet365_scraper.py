
from playwright.sync_api import sync_playwright
import time
import re


print("===================================")
print("🔥 BET365 VALUE SCRAPER 🔥")
print("===================================")


def normalize_team_name(name):

    name = name.lower()

    replacements = {
        "paris saint-germain": "psg",
        "psg": "psg",
        "manchester city": "man city",
        "manchester united": "man united",
        "internazionale": "inter",
        "fc barcelona": "barcelona",
        "real madrid cf": "real madrid",
        "sporting cp": "sporting",
        "atletico madrid": "atl madrid"
    }

    for old, new in replacements.items():

        name = name.replace(
            old,
            new
        )

    name = re.sub(
        r"[^a-z0-9 ]",
        "",
        name
    )

    return name.strip()


def extract_odds_from_text(text):

    text = text.replace(",", ".")

    odds = re.findall(
        r"\b\d\.\d{2}\b",
        text
    )

    return odds


def find_match_section(
    body_text,
    home_team,
    away_team
):

    lines = body_text.splitlines()

    normalized_home = normalize_team_name(
        home_team
    )

    normalized_away = normalize_team_name(
        away_team
    )

    possible_sections = []

    for i in range(len(lines)):

        line = normalize_team_name(
            lines[i]
        )

        if (
            normalized_home in line
            or normalized_away in line
        ):

            section = "\n".join(
                lines[i:i+400]
            )

            possible_sections.append(
                section
            )

    # PRIORITAT A MERCATS REALS
    for section in possible_sections:

        if (
            "Más de" in section
            or "Menos de" in section
            or "Hándicap" in section
            or "Asian" in section
        ):

            return section

    if possible_sections:

        return possible_sections[0]

    return None


def find_total_market(
    section_text,
    side,
    points
):

    lines = section_text.splitlines()

    points_str = str(points)

    if side == "over":

        targets = [
            f"Más de {points_str}",
            f"Over {points_str}",
            f"O {points_str}"
        ]

    else:

        targets = [
            f"Menos de {points_str}",
            f"Under {points_str}",
            f"U {points_str}"
        ]

    for i in range(len(lines)):

        line = lines[i]

        for target in targets:

            if target in line:

                print(
                    f"🎯 TOTAL TROBAT: {line}"
                )

                # BUSCAR ODDS PROPERES
                for j in range(
                    i,
                    min(i + 8, len(lines))
                ):

                    odd_line = (
                        lines[j]
                        .replace(",", ".")
                        .strip()
                    )

                    if re.match(
                        r"^\d\.\d{2}$",
                        odd_line
                    ):

                        return float(
                            odd_line
                        )

    return None


def find_spread_market(
    section_text,
    side,
    points
):

    lines = section_text.splitlines()

    target = str(points)

    for i in range(len(lines)):

        line = lines[i]

        if target in line:

            print(
                f"🎯 HANDICAP TROBAT: {line}"
            )

            for j in range(
                i,
                min(i + 8, len(lines))
            ):

                odd_line = (
                    lines[j]
                    .replace(",", ".")
                    .strip()
                )

                if re.match(
                    r"^\d\.\d{2}$",
                    odd_line
                ):

                    return float(
                        odd_line
                    )

    return None


def scan_bet365_value(
    home_team,
    away_team,
    market_type,
    side,
    points,
    value_limit
):

    try:

        with sync_playwright() as p:

            browser = p.chromium.launch(
                headless=False,
                slow_mo=150
            )

            context = browser.new_context(
                viewport={
                    "width": 1400,
                    "height": 900
                },
                user_agent=(
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/137.0.0.0 "
                    "Safari/537.36"
                ),
                locale="es-ES"
            )

            page = context.new_page()

            print(
                "🌐 Obrint Bet365..."
            )

            page.goto(
                "https://www.bet365.es",
                wait_until="domcontentloaded",
                timeout=120000
            )

            print(
                "✅ Bet365 carregat"
            )

            time.sleep(8)

            # COOKIES
            try:

                buttons = page.locator(
                    "button"
                )

                count = buttons.count()

                for i in range(count):

                    try:

                        text = (
                            buttons
                            .nth(i)
                            .inner_text()
                        )

                        if (
                            "Aceptar" in text
                            or "Accept" in text
                            or "Agree" in text
                        ):

                            buttons.nth(i).click()

                            print(
                                "✅ Cookies acceptades"
                            )

                            break

                    except:
                        pass

            except:
                pass

            print(
                "⏳ Esperant DOM..."
            )

            page.wait_for_timeout(
                12000
            )

            print(
                "🔎 Extraient text visible..."
            )

            body_text = (
                page
                .locator("body")
                .inner_text()
            )

            print(
                "🔎 Buscant partit..."
            )

            section = find_match_section(
                body_text,
                home_team,
                away_team
            )

            if not section:

                print(
                    "❌ Match no trobat"
                )

                browser.close()

                return None

            print(
                "==================================="
            )

            print(
                "✅ MATCH TROBAT"
            )

            print(
                "==================================="
            )

            print(
                section[:6000]
            )

            print(
                "==================================="
            )

            print(
                "🔎 Buscant market..."
            )

            market_odds = None

            # TOTALS
            if market_type == "total":

                market_odds = find_total_market(
                    section,
                    side,
                    points
                )

            # HANDICAPS
            elif market_type == "spread":

                market_odds = find_spread_market(
                    section,
                    side,
                    points
                )

            if not market_odds:

                print(
                    "❌ Market no trobat"
                )

                browser.close()

                return None

            edge = round(
                market_odds
                - value_limit,
                3
            )

            value_available = (
                market_odds
                > value_limit
            )

            print(
                "==================================="
            )

            print(
                "🔥 RESULTAT FINAL"
            )

            print(
                "==================================="
            )

            print(
                f"⚽ Match: "
                f"{home_team} vs "
                f"{away_team}"
            )

            print(
                f"📈 Market: "
                f"{market_type}"
            )

            print(
                f"🎯 Selection: "
                f"{side} "
                f"{points}"
            )

            print(
                f"💰 Bet365 Odds: "
                f"{market_odds}"
            )

            print(
                f"✅ Value Limit: "
                f"{value_limit}"
            )

            print(
                f"📊 Edge: "
                f"{edge}"
            )

            print(
                f"🔥 Value Available: "
                f"{value_available}"
            )

            print(
                "==================================="
            )

            time.sleep(20)

            browser.close()

            return {
                "match": (
                    f"{home_team} "
                    f"vs "
                    f"{away_team}"
                ),
                "market_type": market_type,
                "side": side,
                "points": points,
                "bet365_odds": market_odds,
                "value_limit": value_limit,
                "edge": edge,
                "value_available": value_available
            }

    except Exception as e:

        print(
            f"ERROR: {e}"
        )

        return None


# TEST REAL
result = scan_bet365_value(
    home_team="PSG",
    away_team="Arsenal",
    market_type="total",
    side="over",
    points=2.5,
    value_limit=1.95
)

print(result)

