import asyncio
import csv
import time
import re
import sys
import os
from playwright.async_api import async_playwright

BASE_URL = "https://ar.prvademecum.com"
SEARCH_URL = f"{BASE_URL}/resultados/"
LETTERS = "abcdefghijklmnopqrstuvwxyzñ"
BROWSER_RESTART_INTERVAL = 100  # Restart browser every N pages to prevent memory leak

# Map section title patterns to CSV field names
SECTION_MAP = {
    "Acción terapéutica": "accion_therapeutica",
    "Propiedades": "propiedades",
    "Indicaciones": "indicaciones",
    "Dosificación": "dosificacion",
    "Dosis y administración": "dosificacion",
    "Reacciones adversas": "reacciones_adversas",
    "Efectos adversos": "reacciones_adversas",
    "Precauciones": "precauciones",
    "Precauciones y advertencias": "precauciones",
    "Interacciones": "interacciones",
    "Contraindicaciones": "contraindicaciones",
    "Sobredosificación": "sobredosificacion"
}

async def extract_substance_data(page, url):
    """Navigate to substance page and extract all fields."""
    try:
        await page.goto(url, timeout=30000)
        await page.wait_for_load_state("domcontentloaded")
        await asyncio.sleep(1)  # Extra time for full render

        data = {
            "url": url,
            "nombre": "",
            "accion_therapeutica": "",
            "propiedades": "",
            "indicaciones": "",
            "dosificacion": "",
            "reacciones_adversas": "",
            "precauciones": "",
            "interacciones": "",
            "contraindicaciones": "",
            "sobredosificacion": "",
            "medicamentos": ""
        }

        # Extract title from first h3 without period at end (has class, unlike section headings)
        try:
            title_text = await page.evaluate("""
                () => {
                    const headings = document.querySelectorAll('h3');
                    for (const h of headings) {
                        if (!h.textContent.endsWith('.')) {
                            return h.textContent.trim();
                        }
                    }
                    return '';
                }
            """)
            data["nombre"] = title_text
        except Exception:
            pass

        # Extract section content by finding h3 headings with periods
        try:
            sections = await page.evaluate("""
                () => {
                    const headings = document.querySelectorAll('h3');
                    let results = {};
                    let current_section = null;
                    let current_content = '';
                    
                    for (const h of headings) {
                        // Save previous section content
                        if (current_section !== null) {
                            results[current_section] = current_content.trim();
                        }
                        
                        // Check if this is a section heading (ends with period)
                        if (h.textContent.trim().endsWith('.')) {
                            current_section = h.textContent.trim().replace('.', '');
                            current_content = '';
                            
                            // Find content following this heading
                            let el = h.nextElementSibling;
                            while (el) {
                                if (el.tagName === 'H3' || el.tagName === 'H2') {
                                    break;
                                }
                                if (el.textContent && el.textContent.trim()) {
                                    current_content += ' ' + el.textContent.trim();
                                }
                                el = el.nextElementSibling;
                            }
                        }
                    }
                    
                    // Save last section
                    if (current_section !== null) {
                        results[current_section] = current_content.trim();
                    }
                    
                    return results;
                }
            """)

            # Map extracted sections to data fields
            for section_title, field_name in SECTION_MAP.items():
                # Try exact match first
                if section_title in sections:
                    data[field_name] = sections[section_title]
                else:
                    # Try case-insensitive partial match
                    for key in sections.keys():
                        if key.lower() == section_title.lower() or key.lower().startswith(section_title.lower()):
                            data[field_name] = sections[key]
                            break
        except Exception as e:
            print(f"  Error extracting sections: {e}")

        # Extract medications list
        try:
            drugs_text = await page.evaluate("""
                () => {
                    const headings = document.querySelectorAll('h2');
                for (const h of headings) {
                    if (h.textContent.includes('Medicamentos que contienen')) {
                        // Find the list after this heading
                        let el = h.nextElementSibling;
                        let drugs = [];
                        while (el && el.tagName !== 'H2') {
                            const links = el.querySelectorAll('a');
                            for (const link of links) {
                                if (link.textContent.trim()) {
                                    drugs.push(link.textContent.trim());
                                }
                            }
                            if (el.querySelector('ul') || el.querySelector('li')) {
                                break;
                            }
                            el = el.nextElementSibling;
                        }
                        return drugs.join('; ');
                    }
                }
                return '';
                }
            """)
            data["medicamentos"] = drugs_text
        except Exception:
            pass

        return data

    except Exception as e:
        print(f"  Error scraping {url}: {e}")
        return None


async def get_max_page(page, letter):
    """Get the maximum page number for a given letter by inspecting pagination links."""
    url = f"{SEARCH_URL}?q={letter}&tipo=sustancia"
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
    """Collect all substance URLs for a given letter, handling pagination."""
    urls = []
    
    # First, determine how many pages there are
    max_page = await get_max_page(page, letter)
    print(f"  Letter {letter}: {max_page} pages")

    for page_num in range(1, max_page + 1):
        url = f"{SEARCH_URL}?q={letter}&tipo=sustancia&pagina={page_num}"
        try:
            await page.goto(url, timeout=30000)
            await asyncio.sleep(1)

            # Collect substance URLs from this page
            substance_links = await page.evaluate("""
                () => {
                    const els = document.querySelectorAll('a');
                    let results = [];
                    for (let el of els) {
                        if (el.href.includes('principio-activo')) {
                            results.push(el.href);
                        }
                    }
                    return results;
                }
            """)

            if not substance_links:
                break

            print(f"  Letter {letter}, page {page_num}/{max_page}: found {len(substance_links)} substances")
            urls.extend(substance_links)

        except Exception as e:
            print(f"  Error with letter {letter}, page {page_num}: {e}")
            break

    return urls


async def collect_urls_phase(p):
    """Phase 1: Collect all substance URLs across all letters."""
    print("\n=== Phase 1: Collecting substance URLs ===")
    
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
    
    # Remove duplicates
    unique_urls = list(set(all_urls))
    print(f"\nTotal unique URLs: {len(unique_urls)}")
    return unique_urls


async def scrape_phase(p, urls):
    """Phase 2: Scrape each substance with periodic browser restarts."""
    print("\n=== Phase 2: Scraping substance data ===")

    # Check for partial CSV to resume from
    results = []
    scraped_urls = set()
    partial_csv = "vademecum_sustancias_partial.csv"
    if os.path.exists(partial_csv):
        print(f"Found partial CSV: {partial_csv}")
        try:
            with open(partial_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    results.append(row)
                    if row.get("url"):
                        scraped_urls.add(row["url"])
            print(f"Loaded {len(results)} already-scraped substances from partial CSV")
        except Exception as e:
            print(f"Error loading partial CSV: {e}")

    # Filter out already-scraped URLs
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
        for i, url in enumerate(urls):
            # Restart browser periodically to prevent memory leak
            if pages_since_restart >= BROWSER_RESTART_INTERVAL:
                print(f"\n  Restarting browser after {pages_since_restart} pages...")
                await page.close()
                await browser.close()
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page()
                await page.set_viewport_size({"width": 1280, "height": 800})
                pages_since_restart = 0
            
            print(f"Scraping {i+1}/{total}: {url}")
            data = await extract_substance_data(page, url)
            if data:
                results.append(data)
                print(f"  ✓ {data['nombre']}")
            else:
                print(f"  ✗ Failed")
            
            pages_since_restart += 1
            
            # Save intermediate results periodically
            if (i + 1) % 50 == 0:
                save_to_csv(results, "vademecum_sustancias_partial.csv")
                print(f"  Saved intermediate results ({len(results)} so far)")
            
            await asyncio.sleep(0.5)
    finally:
        await page.close()
        await browser.close()
    
    return results


async def main():
    # Parse command line arguments
    test_url = None
    resume = False
    phase = "all"
    args = sys.argv[1:]
    while args:
        arg = args.pop(0)
        if arg == "--test":
            test_url = "https://ar.prvademecum.com/principio-activo/abacavir-4146"
        elif arg == "--resume":
            resume = True
        elif arg == "--phase":
            phase = args.pop(0)
        elif arg.startswith("http"):
            test_url = arg

    print("Starting Vademecum scraper...")
    start_time = time.time()

    async with async_playwright() as p:
        if test_url:
            print(f"\n=== Test mode: scraping {test_url} ===")
            unique_urls = [test_url]
            # Scrape only
            results = await scrape_phase(p, unique_urls)
            save_to_csv(results, "vademecum_sustancias.csv")
            elapsed = time.time() - start_time
            print(f"Done! {len(results)} substances scraped in {elapsed:.1f} seconds")
            return

        if phase in ("collect", "1") or (resume and phase == "all"):
            # Collect URLs phase
            if not os.path.exists("sustancias_urls.txt"):
                print("\n=== Collecting substance URLs ===")
                unique_urls = await collect_urls_phase(p)
                if not unique_urls:
                    print("No URLs collected. Exiting.")
                    return
            else:
                with open("sustancias_urls.txt", "r") as f:
                    unique_urls = [line.strip() for line in f if line.strip()]
                print(f"Loaded {len(unique_urls)} URLs from file")
        elif phase in ("scrape", "2"):
            # Scrape phase only - need saved URLs
            if not os.path.exists("sustancias_urls.txt"):
                print("No saved URLs found. Run collect phase first.")
                return
            with open("sustancias_urls.txt", "r") as f:
                unique_urls = [line.strip() for line in f if line.strip()]
            print(f"Loaded {len(unique_urls)} URLs from file")
        else:
            # Full run: collect then scrape
            unique_urls = await collect_urls_phase(p)
            if not unique_urls:
                print("No URLs collected. Exiting.")
                return

        # Save URLs
        with open("sustancias_urls.txt", "w") as f:
            for url in unique_urls:
                f.write(url + "\n")
        print("URLs saved to sustancias_urls.txt")

        # Scrape phase
        results = await scrape_phase(p, unique_urls)

        # Save final results
        print("\n=== Saving to CSV ===")
        save_to_csv(results, "vademecum_sustancias.csv")
        elapsed = time.time() - start_time
        print(f"Done! {len(results)} substances scraped in {elapsed:.1f} seconds")


def save_to_csv(results, filename):
    """Save results to CSV file."""
    if not results:
        return

    fieldnames = ["nombre", "url", "accion_therapeutica", "propiedades",
                 "indicaciones", "dosificacion", "reacciones_adversas",
                 "precauciones", "interacciones", "contraindicaciones",
                 "sobredosificacion", "medicamentos"]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow(result)


if __name__ == "__main__":
    asyncio.run(main())