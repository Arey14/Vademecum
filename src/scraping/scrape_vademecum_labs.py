import asyncio
import csv
import time
import sys
import os
from playwright.async_api import async_playwright

BASE_URL = "https://ar.prvademecum.com"
SEARCH_URL = f"{BASE_URL}/resultados/"
LETTERS = "abcdefghijklmnopqrstuvwxyzñ"
BROWSER_RESTART_INTERVAL = 100

async def extract_lab_data(page, url):
    """Navigate to lab page and extract fields."""
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(1)

        data = {
            "url": url,
            "nombre": "",
            "direccion": "",
            "ciudad": "",
            "provincia": "",
            "telefono": "",
            "productos": ""
        }

        # Extract name from h3 heading (format: just the name, no prefix)
        try:
            name = await page.evaluate("""
                () => {
                    const h3 = document.querySelector('h3');
                    if (h3) {
                        let text = h3.textContent.trim();
                        return text;
                    }
                    return '';
                }
            """)
            data["nombre"] = name
        except Exception:
            pass

        # Extract structured info via innerText parsing
        try:
            content = await page.evaluate("""
                () => {
                    const container = document.querySelector('.layout-content-container');
                    return container ? container.innerText : '';
                }
            """)

            # Parse fields from emoji-prefixed lines
            import re
            lines = content.split('\n')
            for line in lines:
                if line.startswith('📍'):
                    data["direccion"] = line.replace('📍', '').strip()
                elif line.startswith('🏙️'):
                    data["ciudad"] = line.replace('🏙️', '').strip()
                elif line.startswith('🌎'):
                    data["provincia"] = line.replace('🌎', '').strip()
                elif line.startswith('📞'):
                    data["telefono"] = line.replace('📞', '').strip()
        except Exception as e:
            print(f"  Error parsing lab fields: {e}")

        # Extract product names from links
        try:
            products = await page.evaluate("""
                () => {
                    const container = document.querySelector('.layout-content-container');
                    if (!container) return '';
                    const links = container.querySelectorAll('a');
                    const products = [];
                    for (let link of links) {
                        const text = link.textContent.trim();
                        if (link.href.includes('/medicamento/') && text) {
                            products.push(text);
                        }
                    }
                    return products.join('; ');
                }
            """)
            data["productos"] = products
        except Exception:
            pass

        return data

    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return None


async def get_max_page(page, letter):
    """Get max page number for lab search on a given letter."""
    url = f"{SEARCH_URL}?q={letter}&tipo=laboratorio"
    try:
        await page.goto(url, timeout=30000)
        await asyncio.sleep(1)

        max_page = 1
        links = await page.evaluate("""
            () => {
                const els = document.querySelectorAll('a');
                let pages = [];
                for (let el of els) {
                    if (el.href.includes('pagina=')) {
                        const match = el.href.match(/pagina=(\\d+)/);
                        if (match) {
                            pages.push(parseInt(match[1]));
                        }
                    }
                }
                return pages;
            }
        """)
        if links:
            max_page = max(links)
    except Exception as e:
        print(f"  Error getting max page for {letter}: {e}")
    return max_page


async def collect_urls_for_letter(page, letter):
    """Collect lab URLs for a given letter."""
    urls = []
    max_page = await get_max_page(page, letter)
    print(f"  Letter {letter}: {max_page} pages")

    for page_num in range(1, max_page + 1):
        url = f"{SEARCH_URL}?q={letter}&tipo=laboratorio&pagina={page_num}"
        try:
            await page.goto(url, timeout=30000)
            await asyncio.sleep(1)

            lab_links = await page.evaluate("""
                () => {
                    const els = document.querySelectorAll('a');
                    let results = [];
                    for (let el of els) {
                        if (el.href.includes('laboratorio/') && !el.href.includes('tipo=')) {
                            results.push(el.href);
                        }
                    }
                    return results;
                }
            """)

            if not lab_links:
                break

            print(f"  Letter {letter}, page {page_num}/{max_page}: found {len(lab_links)} labs")
            urls.extend(lab_links)

        except Exception as e:
            print(f"  Error with letter {letter}, page {page_num}: {e}")
            break

    return urls


async def collect_urls_phase(p):
    """Phase 1: Collect all lab URLs."""
    print("\n=== Phase 1: Collecting laboratory URLs ===")

    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.set_viewport_size({"width": 1280, "height": 800})

    try:
        all_urls = []
        for letter in LETTERS:
            print(f"Searching for letter: {letter}")
            urls = await collect_urls_for_letter(page, letter)
            all_urls.extend(urls)
            print(f"  Subtotal: {len(all_urls)} URLs")
    finally:
        await browser.close()

    unique_urls = list(set(all_urls))
    print(f"\nTotal unique lab URLs: {len(unique_urls)}")
    return unique_urls


async def scrape_phase(p, urls):
    """Phase 2: Scrape each lab with periodic browser restarts."""
    print("\n=== Phase 2: Scraping laboratory data ===")

    results = []
    scraped_urls = set()
    partial_csv = "vademecum_laboratorios_partial.csv"

    if os.path.exists(partial_csv):
        print(f"Found partial CSV: {partial_csv}")
        try:
            with open(partial_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    results.append(row)
                    if row.get("url"):
                        scraped_urls.add(row["url"])
            print(f"Loaded {len(results)} already-scraped labs from partial CSV")
        except Exception as e:
            print(f"Error loading partial CSV: {e}")

    remaining_urls = [url for url in urls if url not in scraped_urls]
    if remaining_urls:
        print(f"Scraping {len(remaining_urls)} remaining URLs (skipping {len(scraped_urls)} already done)")
    else:
        print("All URLs already scraped!")
        return results

    browser = await p.chromium.launch(headless=True)
    page = await browser.new_page()
    await page.set_viewport_size({"width": 1280, "height": 800})

    total = len(remaining_urls)
    pages_since_restart = 0

    try:
        for i, url in enumerate(remaining_urls):
            if pages_since_restart >= BROWSER_RESTART_INTERVAL:
                print(f"\n  Restarting browser after {pages_since_restart} pages...")
                await page.close()
                await browser.close()
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_viewport_size({"width": 1280, "height": 800})
                pages_since_restart = 0

            print(f"Scraping {i+1}/{total}: {url}")
            data = await extract_lab_data(page, url)
            if data:
                results.append(data)
                print(f"  ✓ {data['nombre']}")
            else:
                print(f"  ✗ Failed")

            pages_since_restart += 1

            if (i + 1) % 50 == 0:
                save_to_csv(results, partial_csv)
                print(f"  Saved intermediate results ({len(results)} so far)")

            await asyncio.sleep(0.5)
    finally:
        await page.close()
        await browser.close()

    return results


def save_to_csv(results, filename):
    """Save lab results to CSV."""
    if not results:
        return

    fieldnames = ["nombre", "url", "direccion", "ciudad", "provincia", "telefono", "productos"]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(result)


async def main():
    test_url = None
    phase = "all"
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--test":
            test_url = "https://ar.prvademecum.com/laboratorio/a-m-farma-activ-552/"
        elif arg == "--phase":
            phase = args.pop(0)
        elif arg.startswith("http"):
            test_url = arg

    print("Starting Vademecum lab scraper...")
    start_time = time.time()

    async with async_playwright() as p:
        if test_url:
            print(f"\n=== Test mode: scraping {test_url} ===")
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            results = [await extract_lab_data(page, test_url)]
            if results and results[0]:
                save_to_csv(results, "vademecum_laboratorios.csv")
            await page.close()
            await browser.close()
            elapsed = time.time() - start_time
            print(f"Done! {len([r for r in results if r])} lab(s) scraped in {elapsed:.1f} seconds")
            return

        if phase in ("collect", "1"):
            unique_urls = await collect_urls_phase(p)
            if not unique_urls:
                print("No URLs collected. Exiting.")
                return
            with open("laboratorios_urls.txt", "w") as f:
                for url in unique_urls:
                    f.write(url + "\n")
            print(f"URLs saved to laboratorios_urls.txt")
            return

        if phase in ("scrape", "2"):
            if not os.path.exists("laboratorios_urls.txt"):
                print("No saved URLs found. Run collect phase first.")
                return
            with open("laboratorios_urls.txt", "r") as f:
                unique_urls = [line.strip() for line in f if line.strip()]
            print(f"Loaded {len(unique_urls)} URLs from file")
            results = await scrape_phase(p, unique_urls)
            print("\n=== Saving to CSV ===")
            save_to_csv(results, "vademecum_laboratorios.csv")
            elapsed = time.time() - start_time
            print(f"Done! {len(results)} labs scraped in {elapsed:.1f} seconds")
            return

        # Full run: collect then scrape
        unique_urls = await collect_urls_phase(p)
        if not unique_urls:
            print("No URLs collected. Exiting.")
            return

        with open("laboratorios_urls.txt", "w") as f:
            for url in unique_urls:
                f.write(url + "\n")
        print(f"URLs saved to laboratorios_urls.txt")

        results = await scrape_phase(p, unique_urls)
        print("\n=== Saving to CSV ===")
        save_to_csv(results, "vademecum_laboratorios.csv")
        elapsed = time.time() - start_time
        print(f"Done! {len(results)} labs scraped in {elapsed:.1f} seconds")


if __name__ == "__main__":
    asyncio.run(main())
