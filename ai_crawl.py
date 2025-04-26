import os, json, asyncio
from pathlib import Path
from typing import List, Set
from urllib.parse import urlparse
from dotenv import load_dotenv

from crawl4ai import AsyncWebCrawler
from category_finder import CategoryLinkFinder
from product_extractor import ProductExtractor
from db import DB, CategoryLink

# --------------------------------------------------------------------------- #
#  Environment & basic helpers
# --------------------------------------------------------------------------- #

load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

CACHE_DIR = Path("crawler_cache")
VISITED_INDEX = CACHE_DIR / "visited_pages.json"
CACHE_DIR.mkdir(exist_ok=True)

def load_visited() -> Set[str]:
    if VISITED_INDEX.exists():
        return set(json.loads(VISITED_INDEX.read_text()))
    return set()

def save_visited(visited: Set[str]):
    VISITED_INDEX.write_text(json.dumps(list(visited), indent=2))

# --------------------------------------------------------------------------- #
#  Main Orchestration Logic
# --------------------------------------------------------------------------- #

async def main(entry_url: str):
    visited = load_visited()
    all_products: List[dict] = []
    domain = urlparse(entry_url).netloc

    db = DB()

    # Instantiate modular extractors
    category_finder = CategoryLinkFinder(llm_api_key=OPENROUTER_API_KEY, db=db)
    product_extractor = ProductExtractor(llm_api_key=OPENROUTER_API_KEY, db=db)

    async with AsyncWebCrawler(base_directory=str(CACHE_DIR)) as crawler:
        # 1. Find category URLs
        use_cached = False
        category_urls = []

        if use_cached:
            category_urls = [c.url for c in db.get_category_links(domain)]
        else:
            category_urls = await category_finder.find_category_links(crawler, entry_url)
        
        return
    
        if not category_urls:
            return


        # 2. Test extraction on one category URL
        url: str = category_urls[0]
        products = await product_extractor.extract_products_from_category(
            crawler, url, cache_dir=str(CACHE_DIR)
        )
        db.add_products(domain, url, products)
        all_products.extend(products)

    print(f"✅ Extracted {len(all_products)} products in total")
    Path("products.json").write_text(json.dumps(all_products, indent=2))

# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    import sys
    start_url = (
        sys.argv[1] if len(sys.argv) > 1 else "https://qvc.com/"
    )
    asyncio.run(main(start_url))
