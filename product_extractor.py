import json
from typing import List, Set
from pathlib import Path
from crawl4ai import (
    AsyncWebCrawler,
    CrawlResult,
    CrawlerRunConfig,
    CacheMode,
    DefaultMarkdownGenerator,
    JsonXPathExtractionStrategy,
    LLMExtractionStrategy,
    LLMConfig,
    LXMLWebScrapingStrategy,
    PruningContentFilter,
)
import re
from db import DB
from urllib.parse import urlparse
from crawl4ai import JsonCssExtractionStrategy
import datetime

class ProductExtractor:
    """
    Extracts products from category pages, handling pagination up to a configurable depth.
    """
    _price_re = re.compile(r"\d[\d,]*\.?\d*")

    def __init__(self, llm_api_key: str, max_depth: int = 3, db: DB = None):
        self.max_depth = max_depth
        self.llm_api_key = llm_api_key
        self.llama_4_scout_config = LLMConfig(
                provider="openrouter/meta-llama/llama-4-scout-17b-16e-instruct",
                api_token=llm_api_key,
            )
        self.gpt_4_config = LLMConfig(
                provider="openrouter/meta-llama/llama-3.3-70b-instruct",
                api_token=llm_api_key,
            )
        self.db = db

        self.llm_product_strategy = LLMExtractionStrategy(
            llm_config=self.llama_4_scout_config,  
            schema={
                "type": "object",
                "properties": {
                    "products": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "price": {"type": "string"},
                            },
                            "required": ["name", "price"],
                        },
                    },
                    "next_page": {"type": ["string", "null"], "format": "uri"},
                },
                "required": ["products", "next_page"],
            },
            extraction_type="schema",
            instruction=(
                "Extract every product name and price on this listing page, "
                "and if there is a pagination link that goes to the next page "
                "return its ABSOLUTE URL; otherwise return null."
            ),
            input_format="html",
            apply_chunking=True,
            chunk_size=100000,
        )

    @staticmethod
    def clean_invalid_products(products: List[dict]) -> List[dict]:
        """
        Remove products with invalid price or missing name.
        """
        price_pattern = re.compile(r"\d[\d,]*\.?\d*")

        def is_valid_product(product: dict) -> bool:
            price = product.get("price", "").replace("$", "").strip()
            name = product.get("name", "").strip()
            title = product.get("title", "").strip()
            return (bool(name) or bool(title)) and bool(price_pattern.fullmatch(price))

        return [product for product in products if is_valid_product(product)]

    @staticmethod
    def _read_json_cache(path: Path) -> set:
        """
        Read a JSON file and return its contents as a set. Return an empty set if file does not exist or is invalid.
        """
        if not path.exists():
            return set()
        try:
            return set(json.loads(path.read_text()))
        except Exception as e:
            print(f"[WARN] Failed to read or parse {path}: {e}")
            return set()

    @staticmethod
    def _write_json_cache(path: Path, data: set) -> None:
        """
        Write a set to a JSON file.
        """
        try:
            path.write_text(json.dumps(list(data), indent=2))
        except Exception as e:
            print(f"[WARN] Failed to write to {path}: {e}")

    async def _get_or_generate_schema(self, crawler: AsyncWebCrawler, category_url: str) -> dict:
        """
        Retrieve the latest schema for the domain, or generate a new one if older than 1 hour.
        """
        base_domain = urlparse(category_url).netloc
        now = datetime.datetime.utcnow()
        schema_record = self.db.get_latest_schema(base_domain)
        schema = None
        generated_at = None

        if schema_record:
            generated_at = schema_record["generated_at"]
            if generated_at.tzinfo is not None:
                generated_at = generated_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)

        # if not schema_record or (now - generated_at).total_seconds() > 120:
        if True: # Always generate schema for now
            print(f"[INFO] Generating schema for {category_url}")
            # Fetch HTML for schema generation


            # TODO: Implement manual content filter and pruning for HTML schema generation
            # -since Crawl4AI's default content filter is removing class attributes.

            prune_filter = PruningContentFilter(
                # Lower → more content retained, higher → more content pruned
                threshold=0.3,
                threshold_type="dynamic",
                min_word_threshold=5
            )


            config = CrawlerRunConfig(
                excluded_tags=['style', 'script', 'form', 'header', 'footer', 'noscript'],
                exclude_external_links=True,
                process_iframes=False,
                remove_overlay_elements=True,
                keep_data_attributes=False,
                cache_mode=CacheMode.BYPASS,
                markdown_generator=DefaultMarkdownGenerator(
                    content_filter=prune_filter
                )
            )
            result: CrawlResult = await crawler.arun(url=category_url, config=config)
            if not result.success:
                print(f"[WARN] Failed to fetch {category_url} for schema generation: {result.error}")
                return None
            cleaned_html = result.markdown.fit_html

            if not cleaned_html:
                print(f"[WARN] No HTML content for schema generation at {category_url}")
                return None
            
            # Save cleaned HTML to a test file for inspection
            test_dir = Path("test_html_outputs")
            test_dir.mkdir(exist_ok=True)
            test_file = test_dir / f"{base_domain.replace('.', '_')}_cleaned.html"
            try:
                test_file.write_text(cleaned_html)
                print(f"[INFO] Saved cleaned HTML to {test_file}")
            except Exception as e:
                print(f"[WARN] Failed to save cleaned HTML to {test_file}: {e}")


            target_json_example = """
            [
                {
                        "title": "Product Title",
                        "price": "37.49",
                        "original_price": "49.99",
                        "discount": "25% off",
                        "image_url": "https://example.com/image.jpg",
                        "description": "Product description",
                        "url": "https://example.com/product/123"
                }
            ]
            """
        
            schema = JsonXPathExtractionStrategy.generate_schema(
                cleaned_html,
                query="Extract products from the page with details such as title, price, product url, discounts, original price, image url, description, etc.", 
                # target_json_example=target_json_example,
                llm_config=self.gpt_4_config)
            print(f"[INFO] Generated schema for {category_url}: \n{schema}")
            self.db.add_schema(base_domain, schema)
        else:
            schema = schema_record["schema"]
        return schema

    async def _extract_with_llm(self, crawler, category_url: str, cache_dir: str = "crawler_cache") -> List[dict]:
        """
        Extract products using the LLM-based strategy (single page, no pagination).
        """
        base_domain = urlparse(category_url).netloc
        products_llm = []
        visited_llm = set()
        result = await crawler.arun(
            url=category_url,
            config=CrawlerRunConfig(
                extraction_strategy=self.llm_product_strategy,
                cache_mode=CacheMode.BYPASS,
            ),
        )
        if result.success:
            try:
                page_data = json.loads(result.extracted_content)
            except Exception as e:
                print(f"[WARN] Failed to parse LLM-based extraction: {e}")
                return []
            valid = self.clean_invalid_products(page_data.get("products", []))
            products_llm.extend(valid)
            self.db.add_products(base_domain, category_url, valid)
            self.db.update_category_link_crawled(base_domain, category_url)
            print(f"Visited {category_url} (LLM) and found {len(valid)} products")
            cache_path = Path(cache_dir) / "visited_pages.json"
            visited_llm.add(category_url)
            existing_visited = self._read_json_cache(cache_path)
            visited_llm.update(existing_visited)
            self._write_json_cache(cache_path, visited_llm)
        else:
            print(f"[WARN] Failed to fetch {category_url}: {result.error}")
        return products_llm

    async def _extract_with_schema(self, crawler, category_url: str) -> List[dict]:
        """
        Extract products using the schema-based strategy (single page, no pagination).
        """
        base_domain = urlparse(category_url).netloc
        products_schema = []
        schema = await self._get_or_generate_schema(crawler, category_url)
        if not schema:
            return []
        json_strategy = JsonCssExtractionStrategy(
            schema=schema,
            extraction_type="json",
            instruction="Extract the products from the HTML",
            input_format="html",
        )
        result = await crawler.arun(
            url=category_url,
            config=CrawlerRunConfig(
                extraction_strategy=json_strategy,
                cache_mode=CacheMode.BYPASS,
            ),
        )
        if result.success:
            page_data = None
            try:
                page_data = json.loads(result.extracted_content)
            except Exception as e:
                print(f"[WARN] Failed to parse schema-based extraction: {e}")
            valid = self.clean_invalid_products(page_data)
            print(valid)
            products_schema.extend(valid)
            self.db.add_products(base_domain, category_url, valid)
            self.db.update_category_link_crawled(base_domain, category_url)
        else:
            print(f"[WARN] Schema-based extraction failed: {result.error}")
        return products_schema

    async def extract_products_from_category(self, 
                                             crawler,
                                             category_url: str,
                                             cache_dir: str = "crawler_cache",
                                             extraction_mode: str = "schema") -> List[dict]:
        """
        Crawl a category page and extract products using the specified extraction mode ('llm' or 'schema').
        """
        if extraction_mode == "llm":
            products = await self._extract_with_llm(crawler, category_url, cache_dir)
            return products
        elif extraction_mode == "schema":
            products = await self._extract_with_schema(crawler, category_url)
            return products
        else:
            raise ValueError(f"Unknown extraction_mode: {extraction_mode}") 