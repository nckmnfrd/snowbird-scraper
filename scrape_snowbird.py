import json
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

URL = "https://www.snowbird.com/the-mountain/mountain-report/lift-trail-report/"
OUTPUT_FILE = Path("lift_status.json")


def normalize_path(path_str: str) -> str:
    return " ".join(path_str.split())


def classify_status(path_d: str) -> str:
    path_d = normalize_path(path_d)

    if path_d.startswith("M15.959 7.173l-6.13 6.72"):
        return "Open"
    if path_d.startswith("M15.65 7.35a.885.885 0 0 0-1.25 0"):
        return "Closed"
    if path_d.startswith("M16.325 10.613H6.674"):
        return "On Hold"
    if path_d.startswith("M10.615 6.514l-.001 4.102H6.513"):
        return "Expected"

    return "Unknown"


def extract_rows_from_table(table_locator):
    results = []
    seen_names = set()

    rows = table_locator.locator("tbody tr")
    row_count = rows.count()

    for i in range(row_count):
        row = rows.nth(i)

        if not row.is_visible():
            continue

        cells = row.locator("td")
        cell_count = cells.count()
        if cell_count < 2:
            continue

        name = cells.nth(0).inner_text().strip()
        if not name:
            continue

        status_cell = cells.nth(1)
        paths = status_cell.locator("path")
        path_count = paths.count()

        if path_count == 0:
            continue

        status = "Unknown"
        for j in range(path_count):
            path_d = paths.nth(j).get_attribute("d")
            if not path_d:
                continue

            candidate = classify_status(path_d)
            if candidate != "Unknown":
                status = candidate
                break

        if name in seen_names:
            continue
        seen_names.add(name)

        results.append({
            "name": name,
            "status": status,
        })

    return results


def scrape_lifts_and_trails() -> dict:
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page()

        try:
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
        except PlaywrightTimeoutError:
            browser.close()
            raise RuntimeError("Timed out loading Snowbird page.")

        tables = page.locator("table")
        table_count = tables.count()

        print(f"Total rendered tables found: {table_count}")

        if table_count == 0:
            html = page.content()
            browser.close()
            raise RuntimeError(
                "No rendered tables found. First 3000 chars of page:\n\n" + html[:3000]
            )

        for i in range(table_count):
            preview = tables.nth(i).inner_text()
            print(f"\n--- TABLE {i} PREVIEW ---")
            print(preview[:500])

        lift_table_index = 0
        trail_table_index = 1 if table_count > 1 else 0

        lifts = extract_rows_from_table(tables.nth(lift_table_index))
        trails = extract_rows_from_table(tables.nth(trail_table_index))

        browser.close()

    return {
        "source": URL,
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "lift_count": len(lifts),
        "trail_count": len(trails),
        "total_count": len(lifts) + len(trails),
        "lifts": lifts,
        "trails": trails,
    }


def main():
    data = scrape_lifts_and_trails()

    print("\n=== FINAL COUNTS ===")
    print("Lifts:", data["lift_count"])
    print("Trails:", data["trail_count"])
    print("Total:", data["total_count"])

    print("\n=== LIFTS SAMPLE ===")
    for item in data["lifts"]:
        print(item)

    print("\n=== TRAILS SAMPLE ===")
    for item in data["trails"][:10]:
        print(item)

    OUTPUT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\nSaved {OUTPUT_FILE}")


if __name__ == "__main__":
    main()