from playwright.sync_api import sync_playwright
import json

def handle_response(response):

    try:

        url = response.url

        # FILTRAR NOMÉS APIs
        keywords = [
            "api",
            "matchups",
            "markets",
            "related",
            "straight",
            "odds"
        ]

        if any(
            word in url.lower()
            for word in keywords
        ):

            print("\n====================")
            print("URL:", url)

            content_type = response.headers.get(
                "content-type",
                ""
            )

            print("TYPE:", content_type)

            if "application/json" in content_type:

                try:

                    data = response.json()

                    print(
                        json.dumps(
                            data,
                            indent=2
                        )[:3000]
                    )

                except:

                    print("No JSON")

    except Exception as e:

        print("ERROR:", e)


with sync_playwright() as p:

    browser = p.chromium.launch(
    headless=True,
    args=["--no-sandbox"]
)

    page = browser.new_page()

    page.on(
        "response",
        handle_response
    )

    page.goto(
        "https://www.pinnacle.com/en/soccer",
        wait_until="networkidle"
    )

    page.wait_for_timeout(30000)

    browser.close()