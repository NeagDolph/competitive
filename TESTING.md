# Testing Documentation

This document describes the comprehensive test suite for the competitive analysis project.

## Overview

The test suite covers all major components of the application including:
- **Playwright/Crawl4AI integration** - Mocked async web crawling functionality
- **Utility functions** - URL helpers, HTML cleaning, content filtering
- **Product extraction** - Both LLM and schema-based extraction methods
- **Category finding** - CSS scraping + LLM classification workflow
- **Database operations** - All CRUD operations and data integrity
- **Main application workflow** - End-to-end testing with mocked dependencies

## Test Structure

### Test Categories

1. **Unit Tests** (`@pytest.mark.unit`)
   - Individual function and method testing
   - Fast execution, no external dependencies
   - Covers utility functions, data processing, validation

2. **Integration Tests** (`@pytest.mark.integration`)
   - Component interaction testing
   - Mocked external services (LLM APIs, web crawling)
   - Database integration testing

3. **Playwright Integration Tests**
   - AsyncWebCrawler configuration and usage
   - Extraction strategy testing
   - Mocked browser automation workflows

## Installation

Install testing dependencies:

```bash
pip install -r test_requirements.txt
```

## Running Tests

### Run All Tests
```bash
pytest test_competitive_analysis.py
```

### Run with Coverage Report
```bash
pytest test_competitive_analysis.py --cov=. --cov-report=html
```

### Run Specific Test Categories
```bash
# Unit tests only
pytest test_competitive_analysis.py -m unit

# Integration tests only
pytest test_competitive_analysis.py -m integration

# Skip slow tests
pytest test_competitive_analysis.py -m "not slow"
```

### Run Specific Test Classes
```bash
# Test URL helpers only
pytest test_competitive_analysis.py::TestURLHelpers

# Test database operations only
pytest test_competitive_analysis.py::TestDatabase

# Test product extraction only
pytest test_competitive_analysis.py::TestProductExtractor
```

### Verbose Output
```bash
pytest test_competitive_analysis.py -v -s
```

## Test Coverage

The test suite covers the following modules and functionality:

### `util/` Module Tests
- **`url_helpers.py`**
  - `get_base_domain()` - Domain extraction from URLs
  - `normalize_url()` - Relative to absolute URL conversion
  - `prune_invalid_links()` - Link filtering and validation

- **`clean_html.py`**
  - `clean_tags()` - HTML tag removal
  - `clean_attributes()` - Attribute stripping
  - `prettify_html()` - HTML formatting
  - `clean_html_for_llm()` - Comprehensive HTML cleaning

- **`ecommerce_content_filter.py`**
  - `EcommerceContentFilter` class initialization
  - Price detection and filtering
  - Content scoring and ranking

- **`universal_content_filter.py`**
  - `UniversalProductFilter` class initialization  
  - Product content extraction
  - HTML fragment deduplication

### `products/` Module Tests
- **`extractor.py`**
  - `ProductExtractor` initialization and configuration
  - `clean_invalid_products()` - Product validation
  - JSON cache operations
  - LLM-based product extraction (`_extract_with_llm()`)
  - Schema-based product extraction (`_extract_with_schema()`)
  - Both extraction modes in `extract_products_from_category()`

### `categories/` Module Tests
- **`finder.py`**
  - `CategoryLinkFinder` initialization
  - HTML anchor tag cleaning
  - Complete category finding workflow
  - CSS extraction + LLM classification pipeline

### Database Tests (`db.py`)
- Domain creation and retrieval
- Category link CRUD operations
- Product CRUD operations
- Schema storage and retrieval
- Category link crawling status management
- Database session management and transactions

### Main Application Tests (`main.py`)
- `extract_categories()` workflow
- `extract_products()` workflow  
- Command-line argument handling
- Different execution modes (categories, products, both)

### Playwright/Crawl4AI Integration
- AsyncWebCrawler configuration
- CrawlerRunConfig setup
- Extraction strategy creation
- Mocked browser automation workflows
- Error handling and result processing

## Mocking Strategy

The test suite extensively uses mocking to avoid external dependencies:

- **AsyncWebCrawler**: Mocked to return controlled HTML content
- **LLM API calls**: Mocked to return predictable responses
- **File system operations**: Temporary files and directories
- **Database**: In-memory SQLite databases for each test
- **Network requests**: No actual HTTP requests made

## Test Data

Test fixtures provide realistic sample data:
- Sample HTML with product listings
- Mock category links with various formats
- Product data with valid/invalid entries
- Database records for testing CRUD operations

## Coverage Goals

The test suite aims for:
- **>90% line coverage** across all modules
- **100% function coverage** for public APIs
- **Complete error path testing** for exception handling
- **Async operation testing** for all concurrent functionality

## Continuous Integration

The tests are designed to:
- Run quickly (typically <30 seconds for full suite)
- Be deterministic and reproducible
- Require no external services or network access
- Clean up all temporary resources

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure all dependencies are installed via `test_requirements.txt`
2. **Async Test Failures**: Check that `pytest-asyncio` is installed and `asyncio_mode = auto` is set
3. **Database Locks**: Tests use temporary databases that are cleaned up automatically
4. **Mock Failures**: Verify that mock patches target the correct module paths

### Debug Mode
```bash
# Run with maximum verbosity and no coverage
pytest test_competitive_analysis.py -vvv -s --no-cov

# Run single test with debugging
pytest test_competitive_analysis.py::TestDatabase::test_domain_creation -vvv -s --pdb
```

## Contributing

When adding new functionality:

1. Add corresponding unit tests
2. Ensure >90% coverage for new code
3. Mock all external dependencies  
4. Add integration tests for component interactions
5. Update this documentation if needed

## Performance

Test execution times:
- Unit tests: ~5-10 seconds
- Integration tests: ~15-20 seconds
- Full suite: ~25-35 seconds

For faster iteration during development, use:
```bash
pytest test_competitive_analysis.py -x --ff
```

This stops on first failure (`-x`) and runs failed tests first (`--ff`). 