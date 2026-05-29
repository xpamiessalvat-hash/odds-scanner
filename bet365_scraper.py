from playwright.sync_api import sync_playwright
import time


print("===================================")
print("BET365 SCRAPER INICIAT")
print("===================================")


def test_bet365():

    try:

        with sync_playwright() as p:

            print("✅ Playwright carregat")

            browser = p.chromium.launch(
                headless=False,
                slow_mo=500
            )

            print("✅ Chromium obert")

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

            print("🌐 Obrint Bet365...")

            page.goto(
                "https://www.bet365.es",
                wait_until="domcontentloaded",
                timeout=120000
            )

            print("✅ Bet365 carregat")

            time.sleep(10)

            print("🔎 URL actual:")
            print(page.url)

            print("📄 Títol pàgina:")
            print(page.title())

            # SCREENSHOT DEBUG
            page.screenshot(
                path="bet365_debug.png",
                full_page=True
            )

            print(
                "📸 Screenshot guardat: "
                "bet365_debug.png"
            )

            # ACCEPT COOKIES
            try:

                print(
                    "🍪 Intentant acceptar cookies..."
                )

                buttons = page.locator(
                    "button"
                )

                count = buttons.count()

                print(
                    f"Botons trobats: {count}"
                )

                for i in range(count):

                    try:

                        text = (
                            buttons
                            .nth(i)
                            .inner_text()
                        )

                        print(
                            f"BUTTON {i}: {text}"
                        )

                        if (
                            "Accept" in text
                            or "Aceptar" in text
                            or "Agree" in text
                            or "Acepto" in text
                        ):

                            buttons.nth(i).click()

                            print(
                                "✅ Cookies acceptades"
                            )

                            time.sleep(5)

                            break

                    except:
                        pass

            except Exception as e:

                print(
                    f"⚠️ Error cookies: {e}"
                )

            print(
                "🔎 Buscant elements DOM..."
            )

            page.wait_for_timeout(10000)

            # DEBUG INPUTS
            inputs = page.locator(
                "input"
            )

            print(
                f"Inputs trobats: "
                f"{inputs.count()}"
            )

            # DEBUG BUTTONS
            buttons = page.locator(
                "button"
            )

            print(
                f"Botons totals: "
                f"{buttons.count()}"
            )

            # DEBUG DIVS
            all_divs = page.locator(
                "div"
            )

            div_count = all_divs.count()

            print(
                f"DIVS trobats: "
                f"{div_count}"
            )

            print(
                "🔎 Cercant textos Search/Buscar..."
            )

            found_texts = []

            for i in range(
                min(div_count, 500)
            ):

                try:

                    text = (
                        all_divs
                        .nth(i)
                        .inner_text()
                        .strip()
                    )

                    if not text:
                        continue

                    if (
                        "Buscar" in text
                        or "Search" in text
                        or "Partido" in text
                        or "Fútbol" in text
                        or "En directo" in text
                    ):

                        found_texts.append(text)

                except:
                    pass

            print(
                "==================================="
            )

            print(
                "TEXTOS TROBATS:"
            )

            print(
                "==================================="
            )

            for text in found_texts[:50]:

                print(text)

            print(
                "==================================="
            )

            # HTML DEBUG
            print(
                "🔎 HTML parcial:"
            )

            html = page.content()

            print(
                html[:5000]
            )

            print(
                "==================================="
            )

            print(
                "⏳ Browser obert 60 segons..."
            )

            time.sleep(60)

            browser.close()

            print(
                "✅ Browser tancat"
            )

    except Exception as e:

        print(
            "==================================="
        )

        print(
            "❌ ERROR DETECTAT"
        )

        print(
            "==================================="
        )

        print(str(e))


if __name__ == "__main__":

    test_bet365()


