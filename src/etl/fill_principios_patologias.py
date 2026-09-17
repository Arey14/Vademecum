#!/home/augusto/envs/tesis/bin/python
import asyncio
import csv
import logging
import time
import aiohttp
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import os
from pathlib import Path

try:
    from src.config import INTERMEDIATE_PRODUCTOS_COMPLETE_CSV, LOGS_DIR
    INPUT_CSV = str(INTERMEDIATE_PRODUCTOS_COMPLETE_CSV)
    FAILED_LOG = str(LOGS_DIR / 'failed_urls.log')
except ImportError:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
    INPUT_CSV = str(BASE_DIR / 'data' / 'intermediate' / 'vademecum_productos_complete.csv')
    FAILED_LOG = str(BASE_DIR / 'logs' / 'failed_urls.log')

MAX_CONCURRENCY = 15
MAX_RETRIES = 3
REQUEST_TIMEOUT = 12
SAVE_EVERY = 50

def parse_html_sections(html_text):
    """
    Extract principios_activos and patologias from prvademecum product HTML.
    Looks inside <div class="doclist"> sections and falls back to link href patterns.
    """
    soup = BeautifulSoup(html_text, 'html.parser')
    
    principios = []
    patologias = []
    
    # 1. Primary extraction: div.doclist containing h2 headings
    for doclist in soup.find_all('div', class_='doclist'):
        h2 = doclist.find('h2')
        if not h2:
            continue
        h2_text = h2.get_text().strip()
        
        if 'Principios Activos' in h2_text:
            for a in doclist.find_all('a'):
                title = a.get('title') or a.get_text().replace('→', '').strip()
                if title:
                    principios.append(title)
        elif 'Patologías' in h2_text or 'Patologias' in h2_text:
            for a in doclist.find_all('a'):
                title = a.get('title') or a.get_text().replace('→', '').strip()
                if title:
                    patologias.append(title)
                    
    # 2. Fallback: Check links by href pattern if doclist was empty
    if not principios:
        for a in soup.find_all('a'):
            href = a.get('href', '')
            if '/principio-activo/' in href:
                title = a.get('title') or a.get_text().replace('→', '').strip()
                if title:
                    principios.append(title)
                    
    if not patologias:
        for a in soup.find_all('a'):
            href = a.get('href', '')
            if '/patologia/' in href:
                title = a.get('title') or a.get_text().replace('→', '').strip()
                if title:
                    patologias.append(title)
                    
    # Deduplicate preserving order
    principios_clean = list(dict.fromkeys(filter(None, principios)))
    patologias_clean = list(dict.fromkeys(filter(None, patologias)))
    
    return "; ".join(principios_clean), "; ".join(patologias_clean)

async def fetch_product_info(session, url, semaphore):
    """Fetch product page and return (principios_activos, patologias, error_str)."""
    if not url or not url.startswith('http'):
        return "", "", "invalid_url"
        
    async with semaphore:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with session.get(url, timeout=REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        text = await response.text()
                        principios, patologias = parse_html_sections(text)
                        return principios, patologias, ""
                    else:
                        if attempt == MAX_RETRIES:
                            return "", "", f"HTTP {response.status}"
            except asyncio.TimeoutError:
                if attempt == MAX_RETRIES:
                    return "", "", "timeout"
            except Exception as e:
                if attempt == MAX_RETRIES:
                    return "", "", str(e)
            await asyncio.sleep(0.5 * attempt)
            
    return "", "", "failed"

def save_csv(csv_path, fieldnames, rows):
    """Save rows back to CSV preserving original column structure."""
    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

async def main_async():
    logger.info("Starting fill_principios_patologias process...")
    
    # Read CSV
    with open(INPUT_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
        
    logger.info(f"Loaded {len(rows)} records from {INPUT_CSV}")
    logger.info(f"CSV Headers: {fieldnames}")
    
    # Filter rows to process (skip if both campos already populated)
    to_process_indices = []
    skipped = 0
    for idx, row in enumerate(rows):
        p_val = row.get('principios_activos', '').strip()
        pat_val = row.get('patologias', '').strip()
        if p_val != '' or pat_val != '':
            skipped += 1
        else:
            to_process_indices.append(idx)
            
    logger.info(f"To process: {len(to_process_indices)} rows (Skipped already filled: {skipped})")
    
    if not to_process_indices:
        logger.info("All rows are already processed. Exiting.")
        return
        
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    processed = 0
    updated = 0
    errors = 0
    start_time = time.time()
    
    async with aiohttp.ClientSession(headers=headers) as session:
        # Process in batches to save progress periodically
        for b_start in range(0, len(to_process_indices), SAVE_EVERY):
            batch_indices = to_process_indices[b_start:b_start + SAVE_EVERY]
            tasks = [
                fetch_product_info(session, rows[idx]['url'], semaphore)
                for idx in batch_indices
            ]
            
            results = await asyncio.gather(*tasks)
            
            for idx, (p_activos, pat, err) in zip(batch_indices, results):
                processed += 1
                if err:
                    errors += 1
                    rows[idx]['error'] = err
                else:
                    rows[idx]['principios_activos'] = p_activos
                    rows[idx]['patologias'] = pat
                    rows[idx]['error'] = ""
                    updated += 1
                    
            # Save checkpoint
            save_csv(INPUT_CSV, fieldnames, rows)
            
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(to_process_indices) - processed) / rate if rate > 0 else 0
            logger.info(f"Progress: {processed}/{len(to_process_indices)} ({processed/len(to_process_indices)*100:.1f}%) - Updated: {updated}, Errors: {errors} - Rate: {rate:.1f} r/s - ETA: {eta/60:.1f}m")
            
    # Final save
    save_csv(INPUT_CSV, fieldnames, rows)
    
    # Save failed URLs log if any
    failed_rows = [r for r in rows if r.get('error', '').strip()]
    if failed_rows:
        logger.info(f"Writing {len(failed_rows)} failed records to {FAILED_LOG}")
        with open(FAILED_LOG, 'w', encoding='utf-8') as f:
            for r in failed_rows:
                f.write(f"{r.get('url')} - Error: {r.get('error')}\n")
                
    logger.info(f"Finished! Total: {len(rows)}, Processed: {processed}, Updated: {updated}, Errors: {errors}, Skipped: {skipped}")
    logger.info(f"Saved to {INPUT_CSV}")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()