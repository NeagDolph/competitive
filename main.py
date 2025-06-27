import os, json, asyncio, argparse
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

from crawl4ai import AsyncWebCrawler
from categories.finder import CategoryLinkFinder
from products.extractor import ProductExtractor
from db import DB
from util.url_helpers import get_base_domain

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CACHE_DIR = Path("crawler_cache")
CACHE_DIR.mkdir(exist_ok=True)

def print_category_links(domain, links):
    print(f"\nCategory links for {domain}:")
    for link in links:
        print(f"- {link}")

async def extract_categories(entry_url: str, crawler: AsyncWebCrawler, debug: bool = False):
    """Extract category links from the entry URL."""
    domain = get_base_domain(entry_url)
    db = DB()
    print(f"🔍 Extracting categories from {entry_url}")
    category_finder = CategoryLinkFinder(llm_api_key=OPENROUTER_API_KEY, db=db, entry_url=entry_url)
    category_urls = await category_finder.find_category_links(crawler)
    if not category_urls:
        print(f"❌ No category links found for {domain}")
        return
    db.add_category_links(domain, category_urls)
    print_category_links(domain, category_urls)

async def extract_products(entry_url: str, crawler: AsyncWebCrawler, debug: bool = False):
    """Extract products from the first uncrawled category link."""
    domain = get_base_domain(entry_url)
    db = DB()
    product_extractor = ProductExtractor(llm_api_key=OPENROUTER_API_KEY, db=db, debug=debug)
    first_link = db.get_oldest_uncrawled_category_link(domain)
    if not first_link:
        print(f"❌ No category links found in DB for {domain}. Run categories extraction first.")
        return
    print(f"🔍 Extracting products from {first_link}")
    all_products = []
    products = await product_extractor.extract_products_from_category(
        crawler, first_link, cache_dir=str(CACHE_DIR)
    )
    db.add_products(domain, first_link, products)
    all_products.extend(products)
    print(f"✅ Extracted {len(all_products)} products from {first_link}")
    Path("products.json").write_text(json.dumps(all_products, indent=2))

async def main():
    parser = argparse.ArgumentParser(description='E-commerce site crawler')
    parser.add_argument('url', help='The URL to start crawling from')
    parser.add_argument('--mode', choices=['categories', 'products', 'both'], default='both',
                      help='What to extract: categories, products, or both (default: both)')
    parser.add_argument('--debug', action='store_true', default=True,
                      help='Enable debug mode with verbose output')
    
    args = parser.parse_args()
    
    # Create a single crawler instance for both operations
    async with AsyncWebCrawler(base_directory=str(CACHE_DIR)) as crawler:
        if args.mode in ['categories', 'both']:
            await extract_categories(args.url, crawler, args.debug)
        
        if args.mode in ['products', 'both']:
            await extract_products(args.url, crawler, args.debug)

if __name__ == "__main__":
    asyncio.run(main()) 