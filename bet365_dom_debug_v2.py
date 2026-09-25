from playwright.sync_api import sync_playwright
import time, re
from pathlib import Path

URL = "https://www.bet365.es"

def dump_game(page):
    loc = page.get_by_text("COL Rockies", exact=True)
    if not loc.count():
        print("❌ COL Rockies no trobat")
        return

    el = loc.first

    # Provem els contenidors ascendents que el debug anterior ha identificat.
    for cls in ["cpr-a6", "cpr-f4c", "cpr-07", "cpr-a"]:
        node = el.locator("xpath=ancestor::div[contains(@class, '%s')][1]" % cls)
        print(f"\n{'='*72}\nCONTENIDOR {cls}\n{'='*72}")
        if not node.count():
            print("No trobat")
            continue

        try:
            print("TEXT:")
            print(node.first.inner_text()[:8000])

            print("\nHTML:")
            html = node.first.inner_html()
            print(html[:12000])

            Path(f"bet365_{cls}_debug.html").write_text(
                html, encoding="utf-8"
            )
        except Exception as e:
            print("ERROR:", e)

    # Busquem el contenidor més petit que tingui els dos equips i,
    # a partir d'aquí, els headers de mercat més propers.
    print(f"\n{'='*72}\nELEMENTS AMB ELS DOS EQUIPS\n{'='*72}")

    both = page.locator("div").filter(
        has_text=re.compile(r"SEA Mariners", re.I)
    ).filter(
        has_text=re.compile(r"COL Rockies", re.I)
    )

    candidates = []
    for i in range(min(both.count(), 100)):
        try:
            n = both.nth(i)
            txt = n.inner_text()
            if len(txt) <= 12000:
                candidates.append((len(txt), i, txt))
        except Exception:
            pass

    candidates.sort()

    for j, (size, i, txt) in enumerate(candidates[:10]):
        print(f"\n[{j}] index={i} text_len={size}")
        print(txt[:5000])

    # Guardem també una captura de pantalla de la zona actual.
    try:
        page.screenshot(path="bet365_dom_debug.png", full_page=False)
        print("\n📸 Captura guardada: bet365_dom_debug.png")
    except Exception:
        pass

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=50)
    context = browser.new_context(
        viewport={"width": 1400, "height": 900},
        locale="es-ES"
    )
    page = context.new_page()

    try:
        print("⚾ BET365 BASEBALL DOM DEBUG V2")
        print("=" * 72)
        print("🌐 Obrint Bet365...")
        page.goto(URL, wait_until="domcontentloaded", timeout=120000)
        page.wait_for_timeout(10000)

        # Cookies
        try:
            buttons = page.locator("button")
            for i in range(min(buttons.count(), 100)):
                try:
                    t = buttons.nth(i).inner_text().strip().lower()
                    if any(x in t for x in ["aceptar", "accept", "agree"]):
                        buttons.nth(i).click(timeout=2000)
                        print("✅ Cookies gestionades")
                        break
                except Exception:
                    pass
        except Exception:
            pass

        page.wait_for_timeout(5000)

        print(f"📄 Text visible: {len(page.locator('body').inner_text()):,} caràcters")
        dump_game(page)

        print("\n⏳ Navegador obert 15 segons...")
        time.sleep(15)
    finally:
        browser.close()
