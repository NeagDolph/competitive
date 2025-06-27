# PLP Labeling Tool

A comprehensive GUI-based tool for labeling Product Listing Pages (PLPs) to create training data for machine learning models. This tool uses Playwright to render web pages and provides an intuitive interface for manual labeling.

## Features

- **Visual Page Rendering**: Uses Playwright to load and display actual web pages
- **Efficient Labeling Interface**: Simple keyboard shortcuts for rapid labeling
- **Data Deduplication**: Automatically detects and skips duplicate content
- **PyTorch Integration**: Stores data in PyTorch-compatible format
- **Multiple Data Sources**: Load URLs from database, text files, or JSON
- **Progress Tracking**: Shows labeling progress and dataset statistics
- **HTML Cleaning**: Automatically cleans HTML content for better model training

## Installation

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Install Playwright browsers:
```bash
playwright install chromium
```

3. If you want to use the content filter, install NLP dependencies:
```bash
pip install -r ../requirements_nlp.txt
```

## Usage

### Basic Usage

Start the labeling tool with a sample of URLs from your database:
```bash
python main.py --sample-size 50
```

### Command Line Options

- `--db-path`: Path to the database file (default: ../crawler_data.db)
- `--data-dir`: Directory to store labeled data (default: plp_data)
- `--domain`: Filter URLs by specific domain
- `--limit`: Limit number of URLs to process
- `--sample-size`: Create balanced sample of specified size
- `--urls-file`: Load URLs from text file (one per line)
- `--json-file`: Load URLs from JSON file
- `--continue-labeling`: Skip already labeled URLs
- `--stats`: Show dataset statistics and exit

### Examples

Label URLs from a specific domain:
```bash
python main.py --domain example.com --limit 20
```

Load URLs from a text file:
```bash
python main.py --urls-file my_urls.txt
```

Continue previous labeling session:
```bash
python main.py --continue-labeling --sample-size 100
```

Show dataset statistics:
```bash
python main.py --stats
```

## Keyboard Shortcuts

- **0**: Label current page as "Not PLP"
- **1**: Label current page as "PLP"
- **Left/Right Arrow**: Navigate between pages
- **Space**: Skip current page
- **Enter**: Load/Reload current page

## Data Format

The tool stores data in a format optimized for machine learning:

### Directory Structure
```
plp_data/
├── html_files/           # Raw and cleaned HTML files
│   ├── abc123.html       # Raw HTML content
│   └── abc123_cleaned.html # Cleaned HTML content
├── labels.jsonl          # Labels and metadata (one JSON per line)
└── metadata.json         # Dataset statistics
```

### Labels Format (JSONL)
Each line in `labels.jsonl` contains:
```json
{
  "url": "https://example.com/category",
  "html_content": "",
  "is_plp": 1,
  "timestamp": "2024-01-01T12:00:00",
  "domain": "example.com",
  "content_hash": "abc123...",
  "cleaned_html": ""
}
```

## PyTorch Integration

Load the labeled data for training:

```python
from data_manager import PLPDataManager

# Load data manager
data_manager = PLPDataManager("plp_data")

# Get PyTorch dataset
dataset = data_manager.export_to_pytorch_dataset()

# Use with DataLoader
from torch.utils.data import DataLoader
dataloader = DataLoader(dataset, batch_size=32, shuffle=True)

# Convert to pandas for analysis
df = dataset.to_dataframe()
print(df.head())
```

## Integration with Universal Content Filter

The labeled data can be used to test and improve the Universal Content Filter:

```python
from util.universal_content_filter import UniversalProductFilter
from plp_labeling_tool.data_manager import PLPDataManager

# Load labeled data
data_manager = PLPDataManager("plp_data")
dataset = data_manager.export_to_pytorch_dataset()

# Test filter performance
filter = UniversalProductFilter()
correct = 0
total = 0

for sample in dataset:
    html_content = sample['html_content']
    actual_label = sample['label']
    
    # Use filter to extract products
    products = filter.filter_content(html_content)
    predicted_label = 1 if len(products) > 0 else 0
    
    if predicted_label == actual_label:
        correct += 1
    total += 1

accuracy = correct / total
print(f"Filter accuracy: {accuracy:.2%}")
```

## Architecture

### Components

1. **`data_manager.py`**: Handles data storage and retrieval
   - `PLPDataManager`: Main class for managing labeled data
   - `PLPDataset`: PyTorch Dataset implementation
   - `PLPSample`: Data class for individual samples

2. **`gui_labeler.py`**: GUI application for labeling
   - `PLPLabelerGUI`: Main GUI class using tkinter and Playwright

3. **`url_loader.py`**: Utility for loading URLs from various sources
   - `URLLoader`: Loads URLs from database, files, or JSON

4. **`main.py`**: Command-line interface and main entry point

### Data Flow

1. URLs are loaded from database, file, or JSON
2. Playwright loads each page in a browser
3. HTML content is extracted and cleaned
4. User labels each page through the GUI
5. Labels and HTML are stored with deduplication
6. Data can be exported to PyTorch format for training

## Tips for Effective Labeling

### What is a Product Listing Page (PLP)?

A PLP typically contains:
- Multiple product tiles/cards in a grid or list
- Product images, names, and prices
- Pagination or infinite scroll
- Filter/sort options
- Category breadcrumbs

### What is NOT a PLP?

- Single product detail pages
- Homepage with featured products
- Account/login pages
- Information pages (About, Contact, etc.)
- Search result pages (unless they show products)

### Labeling Guidelines

1. Load each page and examine the content
2. Look for repeating product containers
3. Consider the primary purpose of the page
4. When in doubt, label as "Not PLP" (be conservative)
5. Use keyboard shortcuts for faster labeling

## Troubleshooting

### Browser Issues
If Playwright fails to start:
```bash
playwright install chromium
```

### Memory Issues
For large datasets, consider:
- Using `--limit` to process smaller batches
- Increasing system memory
- Processing by domain using `--domain`

### Database Connection
Ensure the database path is correct:
```bash
python main.py --db-path /path/to/your/crawler_data.db
```

## Contributing

1. Add new URL sources in `url_loader.py`
2. Improve HTML cleaning in the data manager
3. Add new export formats for different ML frameworks
4. Enhance the GUI with additional features

## License

This tool is part of the competitive analysis project. 