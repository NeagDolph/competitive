import asyncio
import re, json
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from typing import List, NotRequired, Set
from typing import TypedDict
from crawl4ai import (
    AsyncWebCrawler,
    CrawlerRunConfig,
    CacheMode,
    JsonCssExtractionStrategy,
    LLMExtractionStrategy,
    LLMConfig,
    CrawlResult,
    LXMLWebScrapingStrategy,
)
from db import DB
from util.url_helpers import get_base_domain, normalize_url, prune_invalid_links
from util.types import Link

class CategoryLinkFinder:
    """
    Extracts category links from an e-commerce entry page using a hybrid approach:
    1. Fast CSS extraction to get all links.
    2. Heuristic filtering for likely category links.
    3. LLM-based classification for final selection.
    """

    _NON_CATEGORY_PAT = re.compile(
        r"""
        javascript:;? | # Javascript links
        tel: | # Telephone links
        /(?:account|login|register|signin|sign-up|my-?account|orders?|wishlist) | # Account management
        /(?:help|faq|contact|support|customer-?service|returns?|shipping|polic(?:y|ies)|terms|privacy|track|accessibility) | # Customer service/info
        /(?:about|career|press|blog|news|company|investor|affiliate) | # Informational pages
        /(?:store-?locator|find-a-store|stores) | # Store locators
        /(?:gift-?card|registry) | # Gift cards / Registry
        /(?:cart|checkout|bag) | # Cart/Checkout
        """,
        re.I | re.X # Case-insensitive and verbose mode for readability
    )

    def __init__(self, llm_api_key: str, db: DB, entry_url: str):
        self.css_link_strategy = JsonCssExtractionStrategy(schema={
            "name": "Links + context",
            "baseSelector": "a",
            "baseFields": [
                {"name": "href",  "type": "attribute", "attribute": "href"},
                {"name": "html", "type": "html", "default": ""},
            ],
            "fields": [
                {"name": "title", "type": "text", "default": "No Title"},
            ]
        })

        self.entry_url = entry_url
        self.domain = get_base_domain(entry_url)

        self.classifier_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="openrouter/deepseek/deepseek-chat-v3-0324",
                api_token=llm_api_key,
                frequency_penalty=0.0,
                temprature=0.0,
                presence_penalty=0.0,
            ),
            schema={
                "type": "object",
                "properties": {
                    "category_urls": {
                        "type": "array",
                        "items": {"type": "string", "format": "uri"},
                    }
                },
                "required": ["category_urls"],
            },
            extraction_type="schema",
            instruction=(
                f"From the provided list of URLs and their HTML context from the e-commerce site {self.domain}, "
                "extract all URLs that lead to product category or sub-category pages. "
                "These pages typically list multiple products. "
                "Return only the absolute URLs from the list. "
                "Exclude links to specific products, account pages, customer service, or informational pages."
            ),
            input_format="text",
            apply_chunking=True,
            chunk_size=1000
        )
        self.db = db

    def _clean_a_tag_html(self, html: str, tags: List[str] = None) -> str:
        """
        Cleans an <a> tag HTML string so that its content is only its inner text (no HTML),
        and removes unnecessary attributes.
        """
        if not html:
            return html
        soup = BeautifulSoup(html, "lxml")
        a_tag = soup.find("a")
        if a_tag:
            # Remove unwanted attributes
            for tag in tags:
                if a_tag.has_attr(tag):
                    del a_tag[tag]
            # Replace all contents of the <a> tag with its inner text only
            tag_text = a_tag.get_text(strip=True)
            a_tag.clear()
            a_tag.append(tag_text)
            return str(a_tag)
        return html

    async def find_category_links(self, crawler: AsyncWebCrawler) -> List[str]:
        """
        Finds links for product categories from the entry URL using a three step process.

        Step 1: Scrape all links
        Step 2: Filter for valid internal links
        Step 3: LLM classification for final category link selection

        Args:
            crawler: An AsyncWebCrawler instance.
            entry_url: The URL to start from.
        Returns:
            List of category URLs (absolute).
        """
        # Stage 1: CSS link scrape
        css_config = CrawlerRunConfig(
            extraction_strategy=self.css_link_strategy,
            scraping_strategy=LXMLWebScrapingStrategy(),
            excluded_tags=["script", "style", "noscript", "footer"],
            keep_data_attributes=True,
            verbose=True,
            cache_mode=CacheMode.READ_ONLY,
        )
        res: CrawlResult = await crawler.arun(url=self.entry_url, config=css_config)
        rows: list[Link] = json.loads(res.extracted_content)

        print(f'Found {len(rows)} preliminary links')

        # Modify each <a> tag so that its content is only its inner text (no HTML), and remove unnecessary attributes
        for r in rows:
            html = r.get("html", "")
            r["html"] = self._clean_a_tag_html(html, ["rel", "target", "style", "aria-haspopup", "aria-expanded", "class"])

        # Use the new reduction method to filter for internal links only
        reduced_links = prune_invalid_links(rows, self.entry_url)
        print(f'Found {len(reduced_links)} reduced links to process')

        if not reduced_links:
            return []
        
        # # LLM classification
        # prompt_text = "\n".join([f'- {r["href"]} - {r["html"][:150]}' for r in reduced_links])
        # print(f'Prompt text: {prompt_text}')
        # print('[INFO] Running LLM category classification')
        # # Ensure classifier_strategy.run is called asynchronously
        # loop = asyncio.get_event_loop()
        # records = await loop.run_in_executor(
        #     None, 
        #     lambda: self.classifier_strategy.run(url=self.entry_url, sections=[prompt_text])
        # )
        # print(f'Records: {records}')
        # fully_extracted: list[str] = []
        # for record in records:
        #     if not record.get("error"):
        #         fully_extracted.extend(record.get("category_urls", []))

        # # Match to the items in reduced_links and return those so that other keys of the link dicts are retained
        # fully_extracted_set = set(fully_extracted)
        # fully_extracted_links = [r for r in reduced_links if r["href"] in fully_extracted_set]

        # print(f'Found {len(fully_extracted_links)} fully extracted links')

        # Ensure all links are absolute
        normalized_links: list[Link] = [{
            "href": normalize_url(link["href"], self.entry_url),
            "html": link["html"]
        } for link in reduced_links]

        # Add all category links to the DB
        self.db.add_category_links(self.domain, normalized_links)
        return normalized_links 