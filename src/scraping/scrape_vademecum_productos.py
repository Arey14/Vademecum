import asyncio
import csv
import os
import sys
import json
import logging
import time
import signal
import argparse
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def scrape_product(page, url):
    """Scrape individual product page."""
    try:
        await page.goto(url, timeout=15000)
        
        product = {
            'url': url,
            'nombre_producto': '',
            'nombre_laboratorio': '',
            'descripcion': '',
            'composicion': '',
            'indicaciones': '',
            'presentacion': '',
            'principios_activos': [],
            'patologias': []
        }
        
        # Product name (h1)
        h1 = await page.query_selector("article h1")
        if h1:
            product['nombre_producto'] = (await h1.inner_text()).strip()
        
        # Manufacturer (h2 under product name)
        h2s = await page.query_selector_all("article h2")
        if h2s:
            product['nombre_laboratorio'] = (await h2s[0].inner_text()).strip()
        
        # Description (paragraph after h2)
        paragraphs = await page.query_selector_all("article p")
        if paragraphs:
            product['descripcion'] = (await paragraphs[0].inner_text()).strip()
        
        # Extract section content by heading
        sections = await page.query_selector_all("h4")
        for h in sections:
            text = (await h.inner_text()).strip()
            if text.startswith("Composición."):
                product['composicion'] = await h.evaluate("el => el.nextElementSibling ? el.nextElementSibling.innerText.trim() : ''")
            elif text.startswith("Indicaciones."):
                product['indicaciones'] = await h.evaluate("el => el.nextElementSibling ? el.nextElementSibling.innerText.trim() : ''")
            elif text.startswith("Presentación."):
                product['presentacion'] = await h.evaluate("el => el.nextElementSibling ? el.nextElementSibling.innerText.trim() : ''")
        
        # Active ingredients
        active_section = await page.query_selector("section:has-text('Principios Activos')")
        if active_section:
            links = await active_section.query_selector_all("a")
            for link in links:
                text = (await link.inner_text()).strip().rstrip("→")
                product['principios_activos'].append(text)
        
        # Pathologies
        path_section = await page.query_selector("section:has-text('Patologías')")
        if path_section:
            links = await path_section.query_selector_all("a")
            for link in links:
                text = (await link.inner_text()).strip().rstrip("→")
                product['patologias'].append(text)
        
        return product
        
    except Exception as e:
        logger.error(f"Error scraping {url}: {e}")
        return {
            'url': url,
            'error': str(e),
            'nombre_producto': '',
            'nombre_laboratorio': '',
            'descripcion': '',
            'composicion': '',
            'indicaciones': '',
            'presentacion': '',
            'principios_activos': [],
            'patologias': []
        }

async def scrape_products(urls, output_file="vademecum_productos.csv"):
    """Scrape multiple products with concurrent requests."""
    logger.info(f"Scraping {len(urls)} products...")
    
    results = []
    errors = []
    processed = 0
    fieldnames = [
        'url', 'nombre_producto', 'nombre_laboratorio', 'descripcion',
        'composicion', 'indicaciones', 'presentacion',
        'principios_activos', 'patologias', 'error'
    ]
    
    # Open output file once and write header immediately
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                # Process in batches of 5
                batch_size = 5
                for i in range(0, len(urls), batch_size):
                    batch = urls[i:i+batch_size]
                    pages = []
                    batch_results = []
                    
                    for url in batch:
                        page = await browser.new_page()
                        pages.append((page, url))
                    
                    # Scrape all pages in batch concurrently
                    tasks = []
                    for page, url in pages:
                        task = asyncio.create_task(scrape_product(page, url))
                        tasks.append(task)
                    
                    batch_results = await asyncio.gather(*tasks)
                    
                    for result in batch_results:
                        processed += 1
                        results.append(result)
                        if processed % 50 == 0:
                            logger.info(f"Processed {processed}/{len(urls)} products")
                    
                    # Write batch results to CSV immediately
                    for result in batch_results:
                        row = dict(result)
                        row['principios_activos'] = "; ".join(row.get('principios_activos', []))
                        row['patologias'] = "; ".join(row.get('patologias', []))
                        writer.writerow(row)
                    f.flush()
                    
                    # Close pages
                    for page, url in pages:
                        await page.close()
                    
                    # Small delay between batches
                    await asyncio.sleep(0.1)
                    
            finally:
                await browser.close()
    
    logger.info(f"Scraped {len(results)} products. Saved to {output_file}")
    return results

async def main():
    parser = argparse.ArgumentParser(description='Scrape Vademecum product pages')
    parser.add_argument('--url-file', type=str, default='productos_urls_dedup.txt',
                      help='Path to file containing product URLs (one per line)')
    parser.add_argument('--output-file', type=str, default='vademecum_productos.csv',
                      help='Path to output CSV file')
    parser.add_argument('--timeout', type=int, default=15000,
                      help='Page load timeout in milliseconds')
    args = parser.parse_args()
    
    # Read URLs from file
    with open(args.url_file, "r") as f:
        urls = [line.strip() for line in f if line.strip()]
    
    logger.info(f"Loaded {len(urls)} product URLs from {args.url_file}")
    
    await scrape_products(urls, args.output_file)

if __name__ == "__main__":
    asyncio.run(main())