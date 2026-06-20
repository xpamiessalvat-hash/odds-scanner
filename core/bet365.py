from playwright.sync_api import sync_playwright

import re
import time


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
                lines[i:i + 400]
            )

            possible_sections.append(
                section
            )

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


class Bet365Client:

    def __init__(self):

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def _accept_cookies(self):

        try:

            buttons = self.page.locator(
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

                        return

                except Exception:
                    pass

        except Exception:
            pass

    def open(self):

        self.playwright = sync_playwright().start()

        self.browser = self.playwright.chromium.launch(
            headless=False,
            slow_mo=150
        )

        self.context = self.browser.new_context(
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

        self.page = self.context.new_page()

        print("🌐 Obrint Bet365...")

        self.page.goto(
            "https://www.bet365.es",
            wait_until="domcontentloaded",
            timeout=120000
        )

        print("✅ Bet365 carregat")

        time.sleep(8)

        self._accept_cookies()

        print("⏳ Esperant DOM...")

        self.page.wait_for_timeout(
            12000
        )

        print("✅ Bet365 preparat")

    def close(self):

        if self.context:
            self.context.close()

        if self.browser:
            self.browser.close()

        if self.playwright:
            self.playwright.stop()