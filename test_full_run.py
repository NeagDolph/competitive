#!/usr/bin/env python3

import asyncio
import os
import sys
import uuid
import argparse
from pathlib import Path
from dotenv import load_dotenv

sys.path.append('.')

from crawl4ai import AsyncWebCrawler
from db import DB
from main import extract_categories
from products.extractor import ProductExtractor
from util.url_helpers import get_base_domain

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CACHE_DIR = Path("crawler_cache")
CACHE_DIR.mkdir(exist_ok=True)

# Common lifestyle/jewelry e-commerce websites
TARGET_WEBSITES = [
    "https://www.kay.com",
    "https://www.zales.com",
    "https://www.jared.com",
    "https://www.tiffany.com",
    "https://www.cartier.com",
    "https://www.bluenile.com",
    "https://www.jamesallen.com",
]

async def test_run_for_site(entry_url: str, crawler: AsyncWebCrawler, debug: bool = True):
    """
    Runs category and product extraction for a single e-commerce site.
    """
    run_id = str(uuid.uuid4())[:8]
    domain = get_base_domain(entry_url)
    db = DB()

    print(f"--- Starting run {run_id} for {domain} ---")

    # 1. Extract Categories
    print(f"\n[PHASE 1] Extracting categories for {entry_url}")
    await extract_categories(entry_url, crawler, debug)

    # 2. Extract Products from 3 category pages
    print(f"\n[PHASE 2] Extracting products for {entry_url}")
    
    # Using get_oldest_uncrawled_category_link multiple times to get a few links
    category_links = []
    for _ in range(3):
        link = db.get_oldest_uncrawled_category_link(domain)
        if link and link not in category_links:
            category_links.append(link)

    if not category_links:
        print(f"❌ No uncrawled category links found for {domain}. Skipping product extraction.")
        return

    print(f"Found {len(category_links)} category links to process: {category_links}")

    product_extractor = ProductExtractor(
        llm_api_key=OPENROUTER_API_KEY,
        db=db,
        debug=debug,
        run_id=run_id
    )

    for link in category_links:
        print(f"\n🔍 Extracting products from {link}...")
        try:
            products = await product_extractor.extract_products_from_category(
                crawler,
                link,
                cache_dir=str(CACHE_DIR),
                extraction_mode="schema"
            )
            print(f"✅ Extracted {len(products)} products from {link}")
        except Exception as e:
            print(f"🔥 An error occurred while extracting products from {link}: {e}")
            import traceback
            traceback.print_exc()

    print(f"--- Finished run {run_id} for {domain} ---\n")


async def main():
    parser = argparse.ArgumentParser(description='Run full test for e-commerce sites.')
    parser.add_argument('--sites', nargs='+', default=TARGET_WEBSITES,
                        help='A list of websites to test.')
    parser.add_argument('--debug', action='store_true', default=True,
                        help='Enable debug mode with verbose output')

    args = parser.parse_args()

    async with AsyncWebCrawler(base_directory=str(CACHE_DIR)) as crawler:
        for site in args.sites:
            await test_run_for_site(site, crawler, args.debug)

if __name__ == "__main__":
    asyncio.run(main()) 