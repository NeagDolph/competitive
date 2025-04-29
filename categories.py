import os, json, asyncio
from pathlib import Path
from urllib.parse import urlparse
from dotenv import load_dotenv

from crawl4ai import AsyncWebCrawler
from category_finder import CategoryLinkFinder
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

async def main(entry_url: str):
    domain = get_base_domain(entry_url)
    db = DB()
    category_finder = CategoryLinkFinder(llm_api_key=OPENROUTER_API_KEY, db=db, entry_url=entry_url)
    async with AsyncWebCrawler(base_directory=str(CACHE_DIR)) as crawler:
        category_urls = await category_finder.find_category_links(crawler)
        if not category_urls:
            print(f"❌ No category links found for {domain}")
            return
        db.add_category_links(domain, category_urls)
        print_category_links(domain, category_urls)

if __name__ == "__main__":
    import sys
    start_url = sys.argv[1] if len(sys.argv) > 1 else "https://qvc.com/"
    asyncio.run(main(start_url)) 