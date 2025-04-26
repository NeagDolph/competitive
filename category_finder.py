import re, json
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from typing import List, Set

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

    def __init__(self, llm_api_key: str, db: DB):
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
        self.classifier_strategy = LLMExtractionStrategy(
            llm_config=LLMConfig(
                provider="openrouter/meta-llama/llama-4-scout-17b-16e-instruct",
                api_token=llm_api_key,
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
                "The input is a plain-text list of absolute URLs and HTML content for links on a page. "
                "Return only those URLs that are TOP-LEVEL PRODUCT CATEGORY pages on an e-commerce site "
                "(e.g. /mens, /electronics, /shop/jewelry, /category/samsung, /content/featured/trending-today, /v/men, etc.). Do not return links to individual products, sales promos, "
                "customer-service pages, blogs, brand pages or external sites."
            ),
            input_format="text",
            apply_chunking=True,
            chunk_size=10000,
        )
        self.db = db

    def _get_base_domain(self, domain: str) -> str:
        """
        Normalize a domain to be subdomain agnostic (treat www and non-www as the same).
        """
        base = urlparse(domain).netloc
        if base.startswith("www."):
            return base[4:]
        return base
    
    def _normalize_url(self, url: str, base_url: str) -> str:
        parsed = urlparse(url)
        if not parsed.netloc:
            return urljoin(base_url, url)
        return url

    def _reduce_links(self, links: list, entry_url: str) -> list:
        """
        Reduce links to only valid, internal, absolute links.
        Removes:
        - mailto: and tel: links
        - links that are just '#' or start with '#'
        - external links
        Ensures all links are absolute.
        """
        base_domain = self._get_base_domain(entry_url)
        reduced = []
        seen = set()
        for r in links:
            href = r.get("href")
            if not href:
                continue
            href = href.strip()
            # Remove mailto: and tel:
            if href.startswith("mailto:") or href.startswith("tel:"):
                continue
            # Remove links that are just '#' or start with '#'
            if href == "#" or href.startswith("#"):
                continue

            full_url = self._normalize_url(href, entry_url)

            # Remove external links
            if self._get_base_domain(full_url) != base_domain:
                continue

            # Remove duplicates
            if full_url in seen:
                continue

            r["href"] = full_url
            seen.add(full_url)
            reduced.append(r)
        return reduced

    def _clean_a_tag_html(self, html: str) -> str:
        """
        Cleans an <a> tag HTML string so that its content is only its inner text (no HTML),
        and removes unnecessary attributes.
        """
        tags_to_remove = ["rel", "target", "style", "aria-haspopup", "aria-expanded"]
        if not html:
            return html
        soup = BeautifulSoup(html, "lxml")
        a_tag = soup.find("a")
        if a_tag:
            # Remove unwanted attributes
            for tag in tags_to_remove:
                if a_tag.has_attr(tag):
                    del a_tag[tag]
            # Replace all contents of the <a> tag with its inner text only
            tag_text = a_tag.get_text(strip=True)
            a_tag.clear()
            a_tag.append(tag_text)
            return str(a_tag)
        return html

    async def find_category_links(self, crawler: AsyncWebCrawler, entry_url: str) -> List[str]:
        """
        Finds category links from the entry URL using a two-stage process.
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
        res: CrawlResult = await crawler.arun(url=entry_url, config=css_config)
        rows = json.loads(res.extracted_content)

        print(f'Found {len(rows)} preliminary links')

        # Modify each <a> tag so that its content is only its inner text (no HTML), and remove unnecessary attributes
        for r in rows:
            html = r.get("html", "")
            r["html"] = self._clean_a_tag_html(html)

        # Use the new reduction method
        reduced_links = self._reduce_links(rows, entry_url)
        print(f'Found {len(reduced_links)} reduced links to process')

        if not reduced_links:
            return []
        
        # LLM classification
        prompt_text = "\n".join([f'URL: {r["href"]}\n{r["html"]}' for r in reduced_links])
        records = self.classifier_strategy.run(url=entry_url, sections=[prompt_text])
        fully_extracted = []
        for record in records:
            if not record.get("error"):
                fully_extracted.extend(record.get("category_urls", []))

        print(f'Found {len(fully_extracted)} fully extracted links')

        # Add all category links to the DB
        self.db.add_category_links(entry_url, fully_extracted)
        return fully_extracted

    def associate_products_with_category(self, entry_url: str, category_url: str, products: list):
        """
        Associates a set of products with a category link in the DB.
        """
        base_domain = self._get_base_domain(entry_url)
        link = self.db.add_category_link(base_domain, category_url)
        self.db.associate_products_with_category(link.id, products)