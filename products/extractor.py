import json
from typing import List, Set
from pathlib import Path
from crawl4ai import (
    AsyncWebCrawler,
    CrawlResult,
    CrawlerRunConfig,
    CacheMode,
    JsonXPathExtractionStrategy,
    LLMExtractionStrategy,
    LLMConfig,
)
import re
from db import DB
from crawl4ai import JsonCssExtractionStrategy
import datetime

from util.clean_html import clean_html_for_llm
from util.url_helpers import get_base_domain

class ProductExtractor:
    """
    Extracts products from category pages, handling pagination up to a configurable depth.
    """
    _price_re = re.compile(r"\d[\d,]*\.?\d*")

    def __init__(self, llm_api_key: str, max_depth: int = 3, db: DB = None, debug: bool = False, run_id: str = None):
        self.max_depth = max_depth
        self.llm_api_key = llm_api_key
        self.debug = debug
        self.run_id = run_id
        self.llama_4_scout_config = LLMConfig(
                provider="openrouter/meta-llama/llama-4-scout-17b-16e-instruct",
                api_token=llm_api_key,
            )
        self.gpt_4_1_config = LLMConfig(
                provider="openrouter/openai/gpt-4.1",
                api_token=llm_api_key,
            )
        self.deepseek_v3_config = LLMConfig(
                provider="openrouter/deepseek/deepseek-chat-v3-0324",
                api_token=llm_api_key,
            )
        self.claude_4_sonnet_config = LLMConfig(
                provider="openrouter/anthropic/claude-sonnet-4",
                api_token=llm_api_key,
            )
        self.llama_3_1_405b_config = LLMConfig(
                provider="openrouter/meta-llama/llama-3.1-405b-instruct",
                api_token=llm_api_key,
            )
        self.db = db
        self.llm_product_strategy = self._create_llm_extraction_strategy(self.llama_4_scout_config)
        if self.debug:
            print(f"[DEBUG] ProductExtractor initialized with debug=True, max_depth={max_depth}")

    def _debug_print(self, message: str):
        """Print debug message if debug mode is enabled."""
        if self.debug:
            print(f"[DEBUG] {message}")

    @staticmethod
    def _create_llm_extraction_strategy(llm_config: LLMConfig) -> LLMExtractionStrategy:
        """
        Create an LLM extraction strategy for a given domain.
        """
        return LLMExtractionStrategy(
            llm_config=llm_config,  
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

    def clean_invalid_products(self, products: List[dict]) -> List[dict]:
        """
        Remove products with invalid price or missing name.
        """
        price_pattern = re.compile(r"\d[\d,]*\.?\d*")
        
        self._debug_print(f"Cleaning {len(products)} products")

        def is_valid_product(product: dict) -> bool:
            price = product.get("price", "").replace("$", "").strip()
            name = product.get("name", "").strip()
            title = product.get("title", "").strip()
            
            valid_name = bool(name) or bool(title)
            valid_price = bool(price_pattern.fullmatch(price))
            
            # self._debug_print(f"Product validation - Name: '{name}', Title: '{title}', Price: '{price}', Valid name: {valid_name}, Valid price: {valid_price}")
            
            return valid_name and valid_price

        valid_products = [product for product in products if is_valid_product(product)]
        self._debug_print(f"After cleaning: {len(valid_products)} valid products out of {len(products)}")
        return valid_products

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
        
    def _save_html_to_file(self, html: str, suffix: str, domain: str) -> None:
        test_dir = Path("test_html_outputs")
        test_dir.mkdir(exist_ok=True)
        
        filename_parts = [domain.replace('.', '_')]
        if self.run_id:
            filename_parts.append(self.run_id)
        filename_parts.append(suffix)

        test_file = test_dir / f"{'_'.join(filename_parts)}.html"
        try:
            test_file.write_text(html)
            print(f"[INFO] Saved cleaned HTML to {test_file}")
        except Exception as e:
            print(f"[WARN] Failed to save cleaned HTML to {test_file}: {e}")

    @staticmethod
    def _write_json_cache(path: Path, data: set) -> None:
        """
        Write a set to a JSON file.
        """
        try:
            path.write_text(json.dumps(list(data), indent=2))
        except Exception as e:
            print(f"[WARN] Failed to write to {path}: {e}")

    async def _get_or_generate_schema(self, crawler: AsyncWebCrawler, category_url: str, always_generate_schema: bool = False) -> dict:
        """
        Retrieve the latest schema for the domain, or generate a new one if older than 1 hour.
        """
        base_domain = get_base_domain(category_url)
        self._debug_print(f"Getting/generating schema for domain: {base_domain}")
        
        schema_record = self.db.get_latest_schema(base_domain)
        schema = None
        generated_at = None

        if schema_record:
            generated_at = schema_record["generated_at"]
            if generated_at.tzinfo is not None:
                generated_at = generated_at.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            self._debug_print(f"Found existing schema generated at: {generated_at}")

        # Make now timezone-naive to match generated_at
        now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

        if always_generate_schema or not schema_record or (now - generated_at).total_seconds() > 120:
            self._debug_print(f"Generating new schema for {category_url}")
            # Fetch HTML for schema generation

            # -since Crawl4AI's default content filter is removing class attributes.

            config = CrawlerRunConfig(
                cache_mode=CacheMode.BYPASS
            )
            
            result: CrawlResult = await crawler.arun(url=category_url, config=config)
            if not result.success:
                print(f"[WARN] Failed to fetch {category_url} for schema generation: {result.error}")
                self._debug_print(f"Crawl result failed: {result.error}")
                return None
            
            cleaned_html = result.html
            self._debug_print(f"Raw HTML length: {len(cleaned_html) if cleaned_html else 0}")

            if not cleaned_html:
                print(f"[WARN] No HTML content for schema generation at {category_url}")
                return None
            
            self._save_html_to_file(cleaned_html, "raw", base_domain)
            
            cleaned_html = clean_html_for_llm(cleaned_html)
            self._debug_print(f"Cleaned HTML length: {len(cleaned_html)}")

            # Save cleaned HTML to a test file for inspection
            self._save_html_to_file(cleaned_html, "cleaned", base_domain)

            target_json_example = """
            [
                {
                        "name": "Product Title",
                        "price": "37.49",
                        "original_price": "49.99",
                        "discount": "25% off",
                        "sku": "1234567890",
                        "image_url": "https://example.com/image.jpg",
                        "description": "Product description",
                        "url": "https://example.com/product/123"
                },
                {
                    "name": "Cozy Winter Sweater",
                    "price": "32.99",
                    "original_price": "48.00",
                    "discount": "31% off",
                    "sku": "A123456",
                    "image_url": "https://example.com/sweater.jpg",
                    "description": "Warm knit sweater for cold weather",
                    "url": "https://example.com/product/sweater"
                }
            ]
            """
        
            # raise Exception("Stop here")
            self._debug_print("Calling JsonXPathExtractionStrategy.generate_schema...")

            schema = JsonXPathExtractionStrategy.generate_schema(
                cleaned_html,
                query="Extract products from the page. Extract name, price, product url, discounts, original price, image url and SKU/Item code for each product. Ensure field names in the schema match the target_json_example exactly. ONLY RETURN THE RAW JSON SCHEMA - DO NOT WRAP WITH TILDAS (```json) OR ANYTHING ELSE.", 
                target_json_example=target_json_example,
                llm_config=self.claude_4_sonnet_config)
            
            self._debug_print(f"Generated schema type: {type(schema)}")
            if isinstance(schema, str):
                self._debug_print(f"Generated schema (string): {schema[:500]}...")
            else:
                self._debug_print(f"Generated schema: {schema}")
                
            print(f"[INFO] Generated schema for {category_url}: \n{schema}")
            self.db.add_schema(base_domain, schema)
            self._debug_print("Schema saved to database")
        else:
            schema = schema_record["schema"]
            self._debug_print(f"Using existing schema: {schema}")
        return schema

    async def _extract_with_llm(self, crawler, category_url: str, cache_dir: str = "crawler_cache") -> List[dict]:
        """
        Extract products using the LLM-based strategy (single page, no pagination).
        """
        base_domain = get_base_domain(category_url)
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

    async def _extract_with_schema(self, crawler: AsyncWebCrawler, category_url: str) -> List[dict]:
        """
        Extract products using the schema-based strategy (single page, no pagination).
        """
        base_domain = get_base_domain(category_url)
        self._debug_print(f"Starting schema-based extraction for {category_url}")
        
        products_schema = []
        schema = await self._get_or_generate_schema(crawler, category_url, always_generate_schema=True)
        if not schema:
            self._debug_print("No schema available, returning empty list")
            return []
            
        self._debug_print(f"Creating JsonCssExtractionStrategy with schema")
        json_strategy = JsonCssExtractionStrategy(
            schema=schema,
            extraction_type="json",
            instruction="Extract the products from the HTML",
            input_format="html",
        )
        
        self._debug_print(f"Running crawler with JsonCssExtractionStrategy...")
        result = await crawler.arun(
            url=category_url,
            config=CrawlerRunConfig(
                extraction_strategy=json_strategy,
                cache_mode=CacheMode.BYPASS,
            ),
        )
        
        if result.success:
            self._debug_print(f"Crawl successful, extracted content length: {len(result.extracted_content) if result.extracted_content else 0}")
            # self._debug_print(f"Raw extracted content: {result.extracted_content}")
            
            page_data = None
            try:
                page_data = json.loads(result.extracted_content)
                self._debug_print(f"Parsed JSON successfully, type: {type(page_data)}")
            except Exception as e:
                print(f"[WARN] Failed to parse schema-based extraction: {e}")
                self._debug_print(f"JSON parsing error: {e}")
                return []
            
            # Save the extracted content to a JSON file for debugging
            try:
                test_dir = Path("test_html_outputs")
                test_dir.mkdir(exist_ok=True)

                filename_parts = [base_domain.replace('.', '_')]
                if self.run_id:
                    filename_parts.append(self.run_id)
                filename_parts.append("schema_extracted")

                json_file = test_dir / f"{'_'.join(filename_parts)}.json"
                with open(json_file, 'w') as f:
                    json.dump(page_data, f, indent=2)
                self._debug_print(f"Saved extracted JSON content to {json_file}")
            except Exception as e:
                self._debug_print(f"Failed to save extracted JSON content: {e}")
                
            # self._debug_print(f"Raw page_data before cleaning: {page_data}")
            valid = self.clean_invalid_products(page_data)
            self._debug_print(f"Products after cleaning: {len(valid)} valid products")
            if valid:
                self._debug_print(f"Sample valid product: {valid[0]}")
            
            products_schema.extend(valid)
            self.db.add_products(base_domain, category_url, valid)
            self.db.update_category_link_crawled(base_domain, category_url)
            print(f"Schema-based extraction found {len(valid)} products")
        else:
            print(f"[WARN] Schema-based extraction failed: {result}")
            self._debug_print(f"Crawl failed with error: {result.error if hasattr(result, 'error') else 'Unknown error'}")
        return products_schema

    async def extract_products_from_category(self, 
                                             crawler,
                                             category_url: str,
                                             cache_dir: str = "crawler_cache",
                                             extraction_mode: str = "schema") -> List[dict]:
        """
        Crawl a category page and extract products using the specified extraction mode ('llm' or 'schema').
        """
        self._debug_print(f"Starting product extraction with mode: {extraction_mode}")
        
        if extraction_mode == "llm":
            products = await self._extract_with_llm(crawler, category_url, cache_dir)
            return products
        elif extraction_mode == "schema":
            products = await self._extract_with_schema(crawler, category_url)
            return products
        else:
            raise ValueError(f"Unknown extraction_mode: {extraction_mode}") 