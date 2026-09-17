import asyncio
import csv
import os
import sys
import json
import logging
import time
import signal
import argparse
import tempfile
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

PRODUCT_SEARCH_URL = "https://ar.prvademecum.com/resultados/"
RESULTS_PER_PAGE = 12

async def search_for_query(query, seen_urls, page_start=1):
    """Search for products using a query term, paginate through results."""
    logger.info(f"Searching for '{query}' starting at page {page_start}...")
    
    page_num = page_start
    consecutive_empty = 0
    MAX_PAGES = 700  # Safety limit per query
    
    while page_num <= MAX_PAGES:
        url = f"{PRODUCT_SEARCH_URL}?q={query}&tipo=producto&pagina={page_num}"
        try:
            # Use browser context passed as parameter
            page = await browser.new_page()
            try:
                await page.goto(url, timeout=30000)
                
                # Count products on this page
                product_links = await page.query_selector_all("a[href*='/medicamento/']")
                page_count = len(product_links)
                
                if page_count == 0:
                    consecutive_empty += 1
                    if consecutive_empty >= 2:
                        logger.info(f"No more products for '{query}' after page {page_num}")
                        break
                else:
                    consecutive_empty = 0
                    logger.info(f"'{query}' page {page_num}: found {page_count} products")
                
                for link in product_links:
                    href = await link.get_attribute("href")
                    full_url = f"https://ar.prvademecum.com{href}"
                    if full_url not in seen_urls:
                        seen_urls.add(full_url)
                
                page_num += 1
                
                # Write checkpoint and incremental output after each page
                write_checkpoint(query, page_num)
                await write_urls_incremental(list(seen_urls))
                
            except Exception as e:
                logger.error(f"Error on '{query}' page {page_num}: {e}")
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    break
            finally:
                await page.close()
        except Exception as e:
            logger.error(f"Browser error for '{query}': {e}")
            break
    
    return seen_urls

# Global browser instance for use within functions
browser = None

def write_checkpoint(query, page_number):
    """Write checkpoint file atomically."""
    tmp_file = "productos_urls_checkpoint.txt.tmp"
    try:
        with open(tmp_file, "w") as f:
            f.write(f"{query}:{page_number}")
        os.rename(tmp_file, "productos_urls_checkpoint.txt")
    except Exception as e:
        logger.error(f"Failed to write checkpoint: {e}")

async def write_urls_incremental(urls):
    """Write URLs to output file incrementally and atomically."""
    tmp_file = "productos_urls.txt.tmp"
    try:
        with open(tmp_file, "w") as f:
            for url in urls:
                f.write(url + "\n")
        os.rename(tmp_file, "productos_urls.txt")
    except Exception as e:
        logger.error(f"Failed to write URLs: {e}")

async def collect_product_urls():
    """Collect all product URLs by searching with multiple query terms."""
    logger.info("Collecting product URLs from search results...")
    
    seen_urls = set()
    output_file = "productos_urls.txt"
    checkpoint_file = "productos_urls_checkpoint.txt"
    
    # Try to resume from checkpoint
    resume_query = None
    resume_page = 1
    if os.path.exists(checkpoint_file):
        try:
            with open(checkpoint_file, "r") as f:
                content = f.read().strip()
                if ":" in content:
                    resume_query, resume_page = content.split(":")
                    resume_page = int(resume_page)
                else:
                    resume_page = int(content)
            logger.info(f"Resuming from checkpoint: query='{resume_query}' page={resume_page}")
        except Exception as e:
            logger.warning(f"Failed to read checkpoint: {e}")
    
    # Load existing URLs into seen set
    if os.path.exists(output_file):
        try:
            with open(output_file, "r") as f:
                for line in f:
                    url = line.strip()
                    if url:
                        seen_urls.add(url)
            logger.info(f"Loaded {len(seen_urls)} existing URLs from {output_file}")
        except Exception as e:
            logger.warning(f"Failed to load existing URLs: {e}")
    
    # Build search queries: letters a-z, numbers 0-9, and special characters
    search_queries = []
    # Search only with vowels and numbers to find more products
    search_queries = ["a", "e", "i", "o", "u", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9"]
    
    global browser
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            for query in search_queries:
                # Skip completed queries if resuming
                if resume_query:
                    if query == resume_query:
                        logger.info(f"Resuming '{query}' from page {resume_page}")
                        seen_urls = await search_for_query(query, seen_urls, resume_page)
                        resume_query = None
                    elif query < resume_query:
                        logger.info(f"Skipping completed query '{query}'")
                        continue
                    else:
                        # We've passed the resume point, start fresh from page 1
                        seen_urls = await search_for_query(query, seen_urls, 1)
                else:
                    seen_urls = await search_for_query(query, seen_urls, 1)
        finally:
            await browser.close()
    
    # Final write
    write_checkpoint("done", 1)
    await write_urls_incremental(list(seen_urls))
    
    logger.info(f"Collected {len(seen_urls)} unique product URLs")
    return list(seen_urls)

async def main():
    urls = await collect_product_urls()
    logger.info(f"URL collection complete")

if __name__ == "__main__":
    asyncio.run(main())
