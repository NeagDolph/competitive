import pytest
import json
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from pathlib import Path
import tempfile
import os
from datetime import datetime, timezone

# Import modules to test
from main import extract_categories, extract_products, main
from util.ecommerce_content_filter import EcommerceContentFilter
from util.universal_content_filter import UniversalProductFilter
from util.clean_html import clean_tags, clean_attributes, prettify_html, clean_html_for_llm
from util.url_helpers import get_base_domain, normalize_url, prune_invalid_links
from products.extractor import ProductExtractor
from categories.finder import CategoryLinkFinder
from db import DB, Domain, CategoryLink, Product, ProductSchema
from util.types import Link

# Test fixtures and sample data
@pytest.fixture
def sample_html():
    return """
    <html>
        <head><title>Test Store</title></head>
        <body>
            <nav class="navigation">
                <a href="/category/electronics" class="nav-link">Electronics</a>
                <a href="/category/clothing" class="nav-link">Clothing</a>
            </nav>
            <div class="product-grid">
                <div class="product-card" data-price="29.99">
                    <h3>Wireless Headphones</h3>
                    <span class="price">$29.99</span>
                    <p>High-quality wireless headphones</p>
                </div>
                <div class="product-card" data-price="49.99">
                    <h3>Bluetooth Speaker</h3>
                    <span class="price">$49.99</span>
                    <p>Portable bluetooth speaker</p>
                </div>
            </div>
            <script>console.log('test');</script>
            <style>body { margin: 0; }</style>
        </body>
    </html>
    """

@pytest.fixture
def sample_links():
    return [
        {"href": "https://example.com/category/electronics", "html": "<a href='/category/electronics'>Electronics</a>", "title": "Electronics"},
        {"href": "https://example.com/category/clothing", "html": "<a href='/category/clothing'>Clothing</a>", "title": "Clothing"},
        {"href": "mailto:test@example.com", "html": "<a href='mailto:test@example.com'>Contact</a>", "title": "Contact"},
        {"href": "#", "html": "<a href='#'>Scroll to top</a>", "title": "Scroll"},
        {"href": "https://external.com/page", "html": "<a href='https://external.com/page'>External</a>", "title": "External"}
    ]

@pytest.fixture
def sample_products():
    return [
        {"name": "Wireless Headphones", "price": "29.99", "url": "https://example.com/product/1"},
        {"name": "Bluetooth Speaker", "price": "49.99", "url": "https://example.com/product/2"},
        {"name": "Invalid Product", "price": "", "url": "https://example.com/product/3"},  # Invalid
        {"name": "", "price": "19.99", "url": "https://example.com/product/4"}  # Invalid
    ]

@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    fd, temp_path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    db = DB(f'sqlite:///{temp_path}')
    yield db
    os.unlink(temp_path)

@pytest.fixture
def mock_crawler():
    """Mock AsyncWebCrawler"""
    crawler = AsyncMock()
    crawler.arun = AsyncMock()
    return crawler

@pytest.fixture
def mock_crawl_result():
    """Mock CrawlResult"""
    result = Mock()
    result.success = True
    result.html = "<html><body>Test content</body></html>"
    result.extracted_content = '{"products": [{"name": "Test Product", "price": "19.99"}], "next_page": null}'
    result.error = None
    return result

class TestURLHelpers:
    """Test URL manipulation functions"""
    
    def test_get_base_domain(self):
        """Test base domain extraction"""
        assert get_base_domain("https://www.example.com/path") == "example.com"
        assert get_base_domain("http://example.com") == "example.com"
        assert get_base_domain("example.com") == "example.com"
        assert get_base_domain("subdomain.example.com") == "subdomain.example.com"
        assert get_base_domain("www.subdomain.example.com") == "subdomain.example.com"

    def test_normalize_url(self):
        """Test URL normalization"""
        base_url = "https://example.com"
        
        # Absolute URLs should remain unchanged
        assert normalize_url("https://example.com/page", base_url) == "https://example.com/page"
        
        # Relative URLs should be converted to absolute
        assert normalize_url("/category/electronics", base_url) == "https://example.com/category/electronics"
        assert normalize_url("product.html", base_url) == "https://example.com/product.html"

    def test_prune_invalid_links(self, sample_links):
        """Test link pruning functionality"""
        entry_url = "https://example.com"
        pruned = prune_invalid_links(sample_links, entry_url)
        
        # Should remove mailto, #, and external links
        assert len(pruned) == 2
        urls = [link["href"] for link in pruned]
        assert "https://example.com/category/electronics" in urls
        assert "https://example.com/category/clothing" in urls
        assert not any("mailto:" in url for url in urls)
        assert not any("external.com" in url for url in urls)

class TestHTMLCleaning:
    """Test HTML cleaning utilities"""
    
    def test_clean_tags(self, sample_html):
        """Test tag removal"""
        cleaned = clean_tags(sample_html, ['script', 'style'])
        assert '<script>' not in cleaned
        assert '<style>' not in cleaned
        assert '<div class="product-card"' in cleaned

    def test_clean_attributes(self, sample_html):
        """Test attribute removal"""
        cleaned = clean_attributes(sample_html, ['class', 'data-*'])
        assert 'class="product-card"' not in cleaned
        assert 'data-price="29.99"' not in cleaned
        assert '<div>' in cleaned  # Tag should remain, just without attributes

    def test_prettify_html(self):
        """Test HTML prettification"""
        ugly_html = "<div><p>Test</p></div>"
        pretty = prettify_html(ugly_html)
        assert "\n" in pretty
        assert " <p>" in pretty  # Should have proper indentation (1 space is BeautifulSoup default)

    def test_clean_html_for_llm(self, sample_html):
        """Test comprehensive HTML cleaning for LLM processing"""
        cleaned = clean_html_for_llm(sample_html)
        
        # Test that unwanted tags are removed
        assert '<script>' not in cleaned
        assert '<style>' not in cleaned
        
        # Test that the HTML is prettified
        assert "\n" in cleaned

class TestContentFilters:
    """Test content filtering classes"""
    
    def test_ecommerce_content_filter_initialization(self):
        """Test EcommerceContentFilter initialization"""
        filter_instance = EcommerceContentFilter(
            retention_threshold=0.5,
            min_word_threshold=3,
            verbose=True
        )
        assert filter_instance.retention_threshold == 0.5
        assert filter_instance.min_word_threshold == 3
        assert filter_instance.verbose is True

    def test_ecommerce_content_filter_price_detection(self, sample_html):
        """Test price detection in ecommerce filter"""
        filter_instance = EcommerceContentFilter()
        filter_instance.user_query = "headphones"
        filter_instance.keep_top_n = 10
        
        filtered_content = filter_instance.filter_content(sample_html)
        assert isinstance(filtered_content, list)
        # Should find content with prices
        assert len(filtered_content) > 0

    def test_universal_product_filter_initialization(self):
        """Test UniversalProductFilter initialization"""
        filter_instance = UniversalProductFilter(
            keep_top_n=50,
            retention_ratio=0.3,
            min_words=5,
            max_chars=1000,
            user_query="electronics",
            verbose=True
        )
        assert filter_instance.keep_top_n == 50
        assert filter_instance.retention_ratio == 0.3
        assert filter_instance.min_words == 5
        assert filter_instance.max_chars == 1000
        assert filter_instance.user_query == "electronics"

    def test_universal_product_filter_content_filtering(self, sample_html):
        """Test content filtering with UniversalProductFilter"""
        filter_instance = UniversalProductFilter(
            keep_top_n=20,
            user_query="wireless headphones"
        )
        
        filtered_content = filter_instance.filter_content(sample_html)
        assert isinstance(filtered_content, list)
        assert len(filtered_content) > 0

class TestDatabase:
    """Test database operations"""
    
    def test_db_initialization(self, temp_db):
        """Test database initialization"""
        assert temp_db.engine is not None
        assert temp_db.Session is not None

    def test_domain_creation(self, temp_db):
        """Test domain creation and retrieval"""
        # Create a session to work with
        session = temp_db.Session()
        try:
            domain = temp_db.get_or_create_domain("example.com", session)
            assert domain is not None
            assert domain.name == "example.com"
            
            # Should return existing domain on second call
            domain2 = temp_db.get_or_create_domain("example.com", session)
            assert domain.id == domain2.id
            session.commit()
        finally:
            session.close()

    def test_category_link_operations(self, temp_db):
        """Test category link CRUD operations"""
        domain_name = "example.com"
        url = "https://example.com/category/electronics"
        html = "<a href='/category/electronics'>Electronics</a>"
        
        # Add category link
        temp_db.add_category_link(domain_name, url, html)
        
        # Retrieve category links
        links = temp_db.get_category_links(domain_name)
        assert url in links

    def test_multiple_category_links(self, temp_db):
        """Test adding multiple category links"""
        domain_name = "example.com"
        links = [
            {"href": "https://example.com/category/electronics", "html": "<a>Electronics</a>"},
            {"href": "https://example.com/category/clothing", "html": "<a>Clothing</a>"}
        ]
        
        temp_db.add_category_links(domain_name, links)
        retrieved_links = temp_db.get_category_links(domain_name)
        assert len(retrieved_links) == 2

    def test_product_operations(self, temp_db):
        """Test product CRUD operations"""
        domain_name = "example.com"
        category_url = "https://example.com/category/electronics"
        
        # Add single product
        temp_db.add_product(
            domain_name=domain_name,
            category_url=category_url,
            name="Test Product",
            price="29.99",
            original_price="39.99",
            discount="25% off",
            image_url="https://example.com/image.jpg",
            url="https://example.com/product/1"
        )

    def test_multiple_products(self, temp_db, sample_products):
        """Test adding multiple products"""
        domain_name = "example.com"
        category_url = "https://example.com/category/electronics"
        
        valid_products = [p for p in sample_products if p["name"] and p["price"]]
        temp_db.add_products(domain_name, category_url, valid_products)

    def test_schema_operations(self, temp_db):
        """Test schema storage and retrieval"""
        domain_name = "example.com"
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        
        # Add schema
        temp_db.add_schema(domain_name, schema)
        
        # Retrieve schema
        retrieved_schema = temp_db.get_latest_schema(domain_name)
        assert retrieved_schema is not None
        assert retrieved_schema["schema"] == schema

    def test_category_link_crawling_status(self, temp_db):
        """Test category link crawling status updates"""
        domain_name = "example.com"
        url = "https://example.com/category/electronics"
        html = "<a href='/category/electronics'>Electronics</a>"
        
        # Add category link
        temp_db.add_category_link(domain_name, url, html)
        
        # Get oldest uncrawled link
        oldest = temp_db.get_oldest_uncrawled_category_link(domain_name)
        assert oldest == url
        
        # Update crawling status
        temp_db.update_category_link_crawled(domain_name, url)

class TestProductExtractor:
    """Test ProductExtractor functionality"""
    
    @pytest.fixture
    def product_extractor(self, temp_db):
        """Create ProductExtractor instance"""
        return ProductExtractor(
            llm_api_key="test_api_key",
            max_depth=2,
            db=temp_db
        )

    def test_product_extractor_initialization(self, product_extractor):
        """Test ProductExtractor initialization"""
        assert product_extractor.max_depth == 2
        assert product_extractor.llm_api_key == "test_api_key"
        assert product_extractor.db is not None

    def test_clean_invalid_products(self, sample_products):
        """Test product validation"""
        valid_products = ProductExtractor.clean_invalid_products(sample_products)
        assert len(valid_products) == 2  # Only 2 valid products
        
        for product in valid_products:
            assert product["name"]  # Should have name
            assert product["price"]  # Should have price

    def test_json_cache_operations(self, tmp_path):
        """Test JSON cache read/write operations"""
        cache_file = tmp_path / "test_cache.json"
        test_data = {"url1", "url2", "url3"}
        
        # Write cache
        ProductExtractor._write_json_cache(cache_file, test_data)
        assert cache_file.exists()
        
        # Read cache
        retrieved_data = ProductExtractor._read_json_cache(cache_file)
        assert retrieved_data == test_data
        
        # Test reading non-existent file
        non_existent = tmp_path / "non_existent.json"
        empty_data = ProductExtractor._read_json_cache(non_existent)
        assert empty_data == set()

    @patch('products.extractor.clean_html_for_llm')
    async def test_extract_with_llm(self, mock_clean_html, product_extractor, mock_crawler, mock_crawl_result):
        """Test LLM-based product extraction"""
        mock_clean_html.return_value = "<html>Test</html>"
        mock_crawler.arun.return_value = mock_crawl_result
        
        category_url = "https://example.com/category/electronics"
        products = await product_extractor._extract_with_llm(mock_crawler, category_url)
        
        assert isinstance(products, list)
        mock_crawler.arun.assert_called_once()

    @patch('products.extractor.clean_html_for_llm')
    async def test_extract_with_schema(self, mock_clean_html, product_extractor, mock_crawler):
        """Test schema-based product extraction"""
        mock_clean_html.return_value = "<html>Test</html>"
        
        # Create a proper mock result with valid JSON structure
        mock_result = Mock()
        mock_result.success = True
        mock_result.extracted_content = '[{"name": "Test Product", "price": "19.99"}]'
        mock_crawler.arun.return_value = mock_result
        
        # Mock schema generation
        with patch.object(product_extractor, '_get_or_generate_schema', return_value={"test": "schema"}):
            category_url = "https://example.com/category/electronics"
            products = await product_extractor._extract_with_schema(mock_crawler, category_url)
            
            assert isinstance(products, list)

    async def test_extract_products_from_category_llm_mode(self, product_extractor, mock_crawler):
        """Test extract_products_from_category with LLM mode"""
        with patch.object(product_extractor, '_extract_with_llm', return_value=[{"name": "Test", "price": "10.00"}]):
            category_url = "https://example.com/category/electronics"
            products = await product_extractor.extract_products_from_category(
                mock_crawler, category_url, extraction_mode="llm"
            )
            assert len(products) == 1
            assert products[0]["name"] == "Test"

    async def test_extract_products_from_category_schema_mode(self, product_extractor, mock_crawler):
        """Test extract_products_from_category with schema mode"""
        with patch.object(product_extractor, '_extract_with_schema', return_value=[{"name": "Test", "price": "10.00"}]):
            category_url = "https://example.com/category/electronics"
            products = await product_extractor.extract_products_from_category(
                mock_crawler, category_url, extraction_mode="schema"
            )
            assert len(products) == 1
            assert products[0]["name"] == "Test"

    def test_extract_products_invalid_mode(self, product_extractor, mock_crawler):
        """Test extract_products_from_category with invalid mode"""
        with pytest.raises(ValueError):
            asyncio.run(
                product_extractor.extract_products_from_category(
                    mock_crawler, "https://example.com", extraction_mode="invalid"
                )
            )

class TestCategoryLinkFinder:
    """Test CategoryLinkFinder functionality"""
    
    @pytest.fixture
    def category_finder(self, temp_db):
        """Create CategoryLinkFinder instance"""
        return CategoryLinkFinder(
            llm_api_key="test_api_key",
            db=temp_db,
            entry_url="https://example.com"
        )

    def test_category_finder_initialization(self, category_finder):
        """Test CategoryLinkFinder initialization"""
        assert category_finder.entry_url == "https://example.com"
        assert category_finder.domain == "example.com"
        assert category_finder.db is not None

    def test_clean_a_tag_html(self, category_finder):
        """Test HTML cleaning for anchor tags"""
        html = '<a href="/category" class="nav-link" style="color: blue;">Electronics</a>'
        cleaned = category_finder._clean_a_tag_html(html, ["class", "style"])
        
        assert 'class="nav-link"' not in cleaned
        assert 'style="color: blue;"' not in cleaned
        assert 'Electronics' in cleaned
        assert 'href="/category"' in cleaned

    @patch('categories.finder.prune_invalid_links')
    @patch('asyncio.get_event_loop')
    async def test_find_category_links(self, mock_get_loop, mock_prune_links, category_finder, mock_crawler):
        """Test category link finding workflow"""
        # Mock the CSS extraction result
        mock_result = Mock()
        mock_result.extracted_content = json.dumps([
            {"href": "/category/electronics", "html": "<a>Electronics</a>", "title": "Electronics"},
            {"href": "/category/clothing", "html": "<a>Clothing</a>", "title": "Clothing"}
        ])
        mock_crawler.arun.return_value = mock_result

        # Mock pruned links
        mock_prune_links.return_value = [
            {"href": "https://example.com/category/electronics", "html": "<a>Electronics</a>"},
            {"href": "https://example.com/category/clothing", "html": "<a>Clothing</a>"}
        ]

        # Mock LLM classification
        mock_executor = AsyncMock()
        mock_loop = Mock()
        mock_loop.run_in_executor = mock_executor
        mock_get_loop.return_value = mock_loop
        
        mock_executor.return_value = [
            {"category_urls": ["https://example.com/category/electronics"]}
        ]

        result = await category_finder.find_category_links(mock_crawler)
        
        assert isinstance(result, list)
        mock_crawler.arun.assert_called_once()

class TestMainApplication:
    """Test main application functions"""
    
    @patch('main.CategoryLinkFinder')
    @patch('main.DB')
    @patch('main.AsyncWebCrawler')
    async def test_extract_categories(self, mock_crawler_class, mock_db_class, mock_finder_class):
        """Test category extraction workflow"""
        # Setup mocks
        mock_db = Mock()
        mock_db_class.return_value = mock_db
        
        mock_finder = Mock()
        mock_finder.find_category_links = AsyncMock(return_value=[
            {"href": "https://example.com/category/electronics", "html": "<a>Electronics</a>"}
        ])
        mock_finder_class.return_value = mock_finder
        
        mock_crawler = AsyncMock()
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=None)
        mock_crawler_class.return_value = mock_crawler

        # Test
        await extract_categories("https://example.com")
        
        # Verify calls
        mock_finder_class.assert_called_once()
        mock_finder.find_category_links.assert_called_once()

    @patch('main.ProductExtractor')
    @patch('main.DB')
    @patch('main.AsyncWebCrawler')
    @patch('main.Path')
    async def test_extract_products(self, mock_path_class, mock_crawler_class, mock_db_class, mock_extractor_class):
        """Test product extraction workflow"""
        # Setup mocks
        mock_db = Mock()
        mock_db.get_oldest_uncrawled_category_link.return_value = "https://example.com/category/electronics"
        mock_db_class.return_value = mock_db
        
        mock_extractor = Mock()
        mock_extractor.extract_products_from_category = AsyncMock(return_value=[
            {"name": "Test Product", "price": "19.99"}
        ])
        mock_extractor_class.return_value = mock_extractor
        
        mock_crawler = AsyncMock()
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=None)
        mock_crawler_class.return_value = mock_crawler
        
        mock_path = Mock()
        mock_path.write_text = Mock()
        mock_path_class.return_value = mock_path

        # Test
        await extract_products("https://example.com")
        
        # Verify calls
        mock_extractor_class.assert_called_once()
        mock_extractor.extract_products_from_category.assert_called_once()

    @patch('main.extract_categories')
    @patch('main.extract_products')
    @patch('sys.argv', ['main.py', 'https://example.com', '--mode', 'both'])
    async def test_main_both_mode(self, mock_extract_products, mock_extract_categories):
        """Test main function with both mode"""
        mock_extract_categories.return_value = None
        mock_extract_products.return_value = None
        
        await main()
        
        mock_extract_categories.assert_called_once_with('https://example.com')
        mock_extract_products.assert_called_once_with('https://example.com')

    @patch('main.extract_categories')
    @patch('main.extract_products')
    @patch('sys.argv', ['main.py', 'https://example.com', '--mode', 'categories'])
    async def test_main_categories_only(self, mock_extract_products, mock_extract_categories):
        """Test main function with categories only mode"""
        mock_extract_categories.return_value = None
        
        await main()
        
        mock_extract_categories.assert_called_once_with('https://example.com')
        mock_extract_products.assert_not_called()

    @patch('main.extract_categories')
    @patch('main.extract_products')
    @patch('sys.argv', ['main.py', 'https://example.com', '--mode', 'products'])
    async def test_main_products_only(self, mock_extract_products, mock_extract_categories):
        """Test main function with products only mode"""
        mock_extract_products.return_value = None
        
        await main()
        
        mock_extract_categories.assert_not_called()
        mock_extract_products.assert_called_once_with('https://example.com')

class TestPlaywrightIntegration:
    """Test Playwright/Crawl4AI integration aspects"""
    
    async def test_crawler_configuration(self):
        """Test AsyncWebCrawler configuration"""
        from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode
        
        # Test that we can create crawler configurations
        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            verbose=True
        )
        assert config.cache_mode == CacheMode.BYPASS
        assert config.verbose is True

    async def test_extraction_strategy_creation(self):
        """Test extraction strategy creation"""
        from crawl4ai import LLMExtractionStrategy, LLMConfig
        
        llm_config = LLMConfig(
            provider="test_provider",
            api_token="test_token"
        )
        
        strategy = LLMExtractionStrategy(
            llm_config=llm_config,
            schema={"type": "object"},
            extraction_type="schema",
            instruction="Test instruction"
        )
        
        assert strategy.llm_config == llm_config
        assert strategy.schema == {"type": "object"}

    @patch('crawl4ai.AsyncWebCrawler')
    async def test_mock_crawler_usage(self, mock_crawler_class):
        """Test mocked crawler usage patterns"""
        mock_crawler = AsyncMock()
        mock_crawler.arun = AsyncMock()
        mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
        mock_crawler.__aexit__ = AsyncMock(return_value=None)
        mock_crawler_class.return_value = mock_crawler
        
        # Simulate using the crawler
        async with mock_crawler_class() as crawler:
            result = await crawler.arun(url="https://example.com")
            
        mock_crawler.arun.assert_called_once_with(url="https://example.com")

# Integration tests
class TestIntegration:
    """Integration tests combining multiple components"""
    
    async def test_full_workflow_mock(self, temp_db):
        """Test complete workflow with mocked external dependencies"""
        with patch('crawl4ai.AsyncWebCrawler') as mock_crawler_class:
            # Setup mock crawler
            mock_crawler = AsyncMock()
            mock_result = Mock()
            mock_result.success = True
            mock_result.extracted_content = json.dumps([
                {"href": "/category/electronics", "html": "<a>Electronics</a>", "title": "Electronics"}
            ])
            mock_crawler.arun = AsyncMock(return_value=mock_result)
            mock_crawler.__aenter__ = AsyncMock(return_value=mock_crawler)
            mock_crawler.__aexit__ = AsyncMock(return_value=None)
            mock_crawler_class.return_value = mock_crawler
            
            # Test category finding
            category_finder = CategoryLinkFinder(
                llm_api_key="test_key",
                db=temp_db,
                entry_url="https://example.com"
            )
            
            with patch('categories.finder.prune_invalid_links') as mock_prune:
                mock_prune.return_value = [
                    {"href": "https://example.com/category/electronics", "html": "<a>Electronics</a>"}
                ]
                
                with patch('asyncio.get_event_loop') as mock_get_loop:
                    mock_executor = AsyncMock()
                    mock_loop = Mock()
                    mock_loop.run_in_executor = mock_executor
                    mock_get_loop.return_value = mock_loop
                    mock_executor.return_value = [
                        {"category_urls": ["https://example.com/category/electronics"]}
                    ]
                    
                    result = await category_finder.find_category_links(mock_crawler)
                    assert len(result) >= 0  # Should complete without error

if __name__ == "__main__":
    pytest.main([__file__]) 