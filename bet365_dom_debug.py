from playwright.sync_api import sync_playwright
import time
import re
from pathlib import Path

BET365_URL = "https://www.bet365.es"

def norm(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9áéíóúüñ ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def inspect_page():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="es-ES",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/137.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        try:
            print("=" * 72)
            print("⚾ BET365 BASEBALL DOM DEBUG")
            print("=" * 72)

            print("🌐 Obrint Bet365...")
            page.goto(BET365_URL, wait_until="domcontentloaded", timeout=120000)
            page.wait_for_timeout(10000)

            # Consent
            try:
                buttons = page.locator("button")
                for i in range(min(buttons.count(), 100)):
                    try:
                        t = buttons.nth(i).inner_text().strip().lower()
                        if any(k in t for k in ["aceptar", "accept", "agree"]):
                            buttons.nth(i).click(timeout=2000)
                            print("✅ Cookies gestionades")
                            break
                    except Exception:
                        pass
            except Exception:
                pass

            page.wait_for_timeout(5000)

            body = page.locator("body").inner_text()
            print(f"📄 Text visible: {len(body):,} caràcters")

            # Busquem exactament textos de baseball coneguts.
            targets = [
                "COL Rockies",
                "SEA Mariners",
                "Total",
                "Hándicap",
                "Línea de dinero",
            ]

            print("\n🔎 TEXTOS OBJECTIU:")
            for target in targets:
                loc = page.get_by_text(target, exact=True)
                print(f"  {target!r}: {loc.count()} elements")

                for i in range(min(loc.count(), 3)):
                    try:
                        el = loc.nth(i)
                        print(f"    [{i}] tag={el.evaluate('(e)=>e.tagName')}")
                        print(f"        class={el.get_attribute('class')}")
                        print(f"        text={el.inner_text()[:200]!r}")
                    except Exception as e:
                        print(f"        ERROR: {e}")

            # DOM ancestry d'un equip si és visible.
            print("\n🧬 ANCESTRIA DOM DE 'COL Rockies':")
            loc = page.get_by_text("COL Rockies", exact=True)

            if loc.count():
                el = loc.first
                info = el.evaluate("""
                (e) => {
                    const out = [];
                    let n = e;
                    for (let i = 0; i < 8 && n; i++, n = n.parentElement) {
                        out.push({
                            level: i,
                            tag: n.tagName,
                            id: n.id || "",
                            cls: typeof n.className === "string" ? n.className : "",
                            text: (n.innerText || "").slice(0, 1200)
                        });
                    }
                    return out;
                }
                """)

                for x in info:
                    print(
                        f"\nLEVEL {x['level']} | {x['tag']} "
                        f"| id={x['id']!r} | class={x['cls']!r}"
                    )
                    print(x["text"])

            # Tots els elements visibles que continguin simultàniament
            # Mariners + Rockies, limitant el text per poder estudiar
            # quina és la unitat real del DOM.
            print("\n🔬 ELEMENTS QUE CONTENEN MARINERS + ROCKIES:")
            candidates = page.locator("body *")
            count = candidates.count()
            found = 0

            for i in range(count):
                if found >= 20:
                    break
                try:
                    el = candidates.nth(i)
                    if not el.is_visible():
                        continue
                    txt = el.inner_text(timeout=300)
                    n = norm(txt)
                    if "sea mariners" in n and "col rockies" in n:
                        # Preferim elements petits: probablement són el
                        # contenidor real del partit.
                        if len(txt) <= 5000:
                            print(
                                f"\n[{found}] TAG={el.evaluate('(e)=>e.tagName')} "
                                f"CLASS={el.get_attribute('class')!r}"
                            )
                            print(txt[:2500])
                            found += 1
                except Exception:
                    pass

            print(f"\nTotal candidats DOM: {found}")

            # Guardem una còpia de l'HTML per inspecció posterior.
            html = page.locator("body").inner_html()
            Path("bet365_dom_debug.html").write_text(
                html, encoding="utf-8"
            )
            print("\n💾 HTML guardat a: bet365_dom_debug.html")

            print("\n⏳ Mantinc el navegador obert 20 segons...")
            time.sleep(20)

        finally:
            browser.close()

if __name__ == "__main__":
    inspect_page()
