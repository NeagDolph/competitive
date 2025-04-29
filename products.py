import os, json, asyncio
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

from crawl4ai import AsyncWebCrawler
from product_extractor import ProductExtractor
from db import DB
from util.url_helpers import get_base_domain

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
CACHE_DIR = Path("crawler_cache")
CACHE_DIR.mkdir(exist_ok=True)

async def main(entry_url: str):
    domain = get_base_domain(entry_url)
    db = DB()
    product_extractor = ProductExtractor(llm_api_key=OPENROUTER_API_KEY, db=db)
    first_link = db.get_oldest_uncrawled_category_link(domain)
    if not first_link:
        print(f"❌ No category links found in DB for {domain}. Run categories.py first.")
        return
    print(f"🔍 Extracting products from {first_link}")
    all_products = []
    async with AsyncWebCrawler(base_directory=str(CACHE_DIR)) as crawler:
        products = await product_extractor.extract_products_from_category(
            crawler, first_link, cache_dir=str(CACHE_DIR)
        )
        db.add_products(domain, first_link, products)
        all_products.extend(products)
    print(f"✅ Extracted {len(all_products)} products from {first_link}")
    Path("products.json").write_text(json.dumps(all_products, indent=2))

if __name__ == "__main__":
    import sys
    start_url = sys.argv[1] if len(sys.argv) > 1 else "https://qvc.com/"
    asyncio.run(main(start_url)) 