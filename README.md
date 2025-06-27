# E-Commerce Product Scraper

A sophisticated web scraping system designed to extract product listings and category information from e-commerce websites. This tool uses NLP techniques and machine learning to automatically identify and extract product information across various e-commerce platforms.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Components](#components)
- [How It Works](#how-it-works)
- [Testing](#testing)
- [Database Schema](#database-schema)
- [Troubleshooting](#troubleshooting)

## Features

- **Category Discovery**: Automatically finds product category links from e-commerce homepages
- **Schema-based Product Extraction**: Generates and uses custom extraction schemas for each website
- **LLM-powered Extraction**: Alternative extraction method using pure LLM processing
- **Universal Content Filter**: NLP-based filtering to identify product content
- **Database Storage**: SQLite database for storing categories, products, and extraction schemas
- **Caching**: Efficient caching system to avoid re-crawling pages
- **PLP Labeling Tool**: GUI tool for manually labeling Product Listing Pages for ML training

## Architecture

```
competitive/
├── main.py                 # Main entry point
├── db.py                   # Database models and operations
├── categories/             # Category link discovery
│   ├── finder.py          # CategoryLinkFinder class
├── products/              # Product extraction
│   ├── extractor.py       # ProductExtractor class
├── util/                  # Utility functions
│   ├── clean_html.py      # HTML cleaning utilities
│   ├── ecommerce_content_filter.py  # E-commerce specific filtering
│   ├── universal_content_filter.py  # Universal NLP-based filter
│   ├── url_helpers.py     # URL manipulation utilities
│   └── types.py           # Type definitions
├── plp_labeling_tool/     # GUI tool for labeling PLPs
└── crawler_data.db        # SQLite database
```

## Requirements

### System Requirements
- Python 3.8+

### Python Dependencies

**Core Dependencies:**
```bash
crawl4ai>=0.3.0
beautifulsoup4>=4.12.0
lxml>=4.9.0
sqlalchemy>=2.0.0
python-dotenv>=1.0.0
```

**NLP Dependencies (for content filtering):**
```bash
scikit-learn>=1.3.0
numpy<2.0.0,>=1.21.0
torch>=1.11.0
spacy>=3.0.0
optimum[onnxruntime]>=1.16.0
sentence-transformers>=2.2.2
```

## Installation

1. **Clone the repository:**
```bash
git clone <repository-url>
cd competitive
```

2. **Create a virtual environment:**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install core dependencies:**
```bash
pip install crawl4ai beautifulsoup4 lxml sqlalchemy python-dotenv
```

4. **Install NLP dependencies (optional but recommended):**
```bash
pip install -r requirements_nlp.txt
python -m spacy download en_core_web_sm
```

5. **Install Playwright (for PLP labeling tool):**
```bash
pip install playwright
playwright install chromium
```

## Configuration

**Create a `.env` file in the project root:**
```bash
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

## Usage

### Basic Usage

**Extract both categories and products from a website:**
```bash
python main.py https://www.example-store.com
```

**Extract only categories:**
```bash
python main.py https://www.example-store.com --mode categories
```

**Extract only products (requires categories to be extracted first):**
```bash
python main.py https://www.example-store.com --mode products
```

**Enable debug mode for verbose output:**
```bash
python main.py https://www.example-store.com --debug
```

### Advanced Usage

**Run full test on multiple jewelry/lifestyle websites:**
```bash
python test_full_run.py
```

**Test specific websites:**
```bash
python test_full_run.py --sites https://www.kay.com https://www.zales.com
```

### PLP Labeling Tool

The PLP (Product Listing Page) labeling tool helps create training data for improving the scraper:

```bash
cd plp_labeling_tool
python main.py --sample-size 50
```

See [plp_labeling_tool/README.md](plp_labeling_tool/README.md) for detailed documentation.

## Components

### 1. Category Finder (`categories/finder.py`)

Discovers product category links from e-commerce homepages using a three-step process:

1. **CSS Extraction**: Extracts all links from the page
2. **Heuristic Filtering**: Filters out non-category links (login, about, etc.)
3. **LLM Classification**: Uses AI to identify actual category links

### 2. Product Extractor (`products/extractor.py`)

Extracts product information from category pages using two methods:

- **Schema-based**: Generates a custom extraction schema for each domain
- **LLM-based**: Uses Large Language Models for flexible extraction

Key features:
- Automatic schema generation and caching
- Product validation and cleaning
- HTML content cleaning for better extraction

### 3. Database (`db.py`)

Database with tables for:
- **Domains**: E-commerce websites
- **CategoryLinks**: Product category URLs
- **Products**: Individual product information
- **ProductSchemas**: Extraction schemas per domain

### 4. Content Filters

- **UniversalProductFilter**: NLP-based filter using spaCy and sentence transformers to extract HTML relevant for schema generation
- **EcommerceContentFilter**: Heuristic keyword-matching filter for e-commerce content

### 5. Utilities

- **HTML Cleaning**: Removes unwanted tags, attributes, and formatting
- **URL Helpers**: Domain extraction, URL normalization, link validation

## How It Works

### Workflow Overview

1. **Category Discovery Phase:**
   - Load the homepage of an e-commerce site
   - Extract all links using CSS selectors
   - Filter links to identify product categories
   - Store category links in the database

2. **Product Extraction Phase:**
   - Retrieve uncrawled category links from database
   - For each category page:
     - Generate or retrieve extraction schema using large-context LLM
        - Clean HTML content using UniversalContentFilter to avoid excesively large input prompts
     - Extract product information (name, price, etc.)
     - Validate and deduplicate products
     - Store products in database

3. **Data Storage:**
   - All data is stored in SQLite database
   - Crawled pages are cached to avoid redundant requests
   - Schemas are cached and refreshed periodically

### Schema Generation

The scraper automatically generates extraction schemas for each domain:

```python
# Example generated schema
{
  "name": "Products",
  "baseSelector": "div.product-item",
  "fields": [
    {"name": "name", "selector": "h3.product-title", "type": "text"},
    {"name": "price", "selector": "span.price", "type": "text"},
    {"name": "image_url", "selector": "img", "type": "attribute", "attribute": "src"}
  ]
}
```

## Testing

Run the test suite:
```bash
python -m pytest test_competitive_analysis.py -v
```

Run specific test categories:
```bash
# Test URL helpers
python -m pytest test_competitive_analysis.py::TestURLHelpers -v

# Test database operations
python -m pytest test_competitive_analysis.py::TestDatabase -v

# Test product extraction
python -m pytest test_competitive_analysis.py::TestProductExtractor -v
```

## Database Schema

### Domains Table
- `id`: Primary key
- `name`: Domain name (e.g., "example.com")

### CategoryLinks Table
- `id`: Primary key
- `url`: Category page URL
- `found_at`: Timestamp when discovered
- `link_html`: Original HTML of the link
- `last_crawled_at`: Last extraction timestamp
- `domain_id`: Foreign key to Domains

### Products Table
- `id`: Primary key
- `name`: Product name
- `price`: Product price
- `original_price`: Original price (if on sale)
- `discount`: Discount information
- `image_url`: Product image URL
- `url`: Product page URL
- `category_link_id`: Foreign key to CategoryLinks
- `domain_id`: Foreign key to Domains
- `found_at`: Timestamp when extracted

### ProductSchemas Table
- `id`: Primary key
- `domain_id`: Foreign key to Domains
- `schema_json`: JSON extraction schema
- `generated_at`: Schema generation timestamp

## Troubleshooting

### Common Issues

1. **"NLP models not available" error:**
   ```bash
   pip install -r requirements_nlp.txt
   python -m spacy download en_core_web_sm
   ```

2. **OpenRouter API errors:**
   - Verify your API key in `.env`
   - Check your OpenRouter credit balance
   - Ensure the API key has proper permissions

3. **No products extracted:**
   - Check if categories were extracted first
   - Enable debug mode to see detailed logs
   - Verify the website structure hasn't changed, if so regenerate schemas

4. **Database errors:**
   - Delete `crawler_data.db` if database schema is updated or database is corrupted
   - Check file permissions for the database file


## Contributing

1. Run tests before submitting PR
2. Add tests for new functionality
3. Update documentation as needed
4. Follow existing code style

## License

This project is licensed under the GNU General Public License v3.0 (GPLv3). You are free to use, modify, and distribute this software under the terms of the GPLv3. See the LICENSE.md file for full details.