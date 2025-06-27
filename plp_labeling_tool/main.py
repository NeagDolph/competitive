#!/usr/bin/env python3
"""
PLP Labeling Tool - Main Entry Point

This tool provides a GUI interface for labeling Product Listing Pages (PLPs) 
to create training data for machine learning models.

Usage:
    python main.py [options]

Options:
    --db-path: Path to the database file (default: ../crawler_data.db)
    --data-dir: Directory to store labeled data (default: plp_data)
    --domain: Filter URLs by domain
    --limit: Limit number of URLs to process
    --sample-size: Create balanced sample of specified size
    --urls-file: Load URLs from text file instead of database
    --json-file: Load URLs from JSON file instead of database
"""

import argparse
import asyncio
import sys
from pathlib import Path
from typing import List, Optional

# Add current directory to path
sys.path.append(str(Path(__file__).parent))

from data_manager import PLPDataManager
from gui_labeler import PLPLabelerGUI
from url_loader import URLLoader


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="PLP Labeling Tool - Create training data for PLP classification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Label URLs from database
    python main.py --sample-size 50

    # Label URLs from specific domain
    python main.py --domain example.com --limit 20
    
    # Label URLs from text file
    python main.py --urls-file urls.txt
    
    # Label URLs from JSON file
    python main.py --json-file data.json
        """
    )
    
    parser.add_argument('--db-path', default='../crawler_data.db',
                        help='Path to the database file')
    parser.add_argument('--data-dir', default='plp_data',
                        help='Directory to store labeled data')
    parser.add_argument('--domain', 
                        help='Filter URLs by domain')
    parser.add_argument('--limit', type=int,
                        help='Limit number of URLs to process')
    parser.add_argument('--sample-size', type=int,
                        help='Create balanced sample of specified size')
    parser.add_argument('--urls-file',
                        help='Load URLs from text file (one per line)')
    parser.add_argument('--json-file',
                        help='Load URLs from JSON file')
    parser.add_argument('--url-key', default='url',
                        help='Key name for URL in JSON objects (default: url)')
    parser.add_argument('--continue-labeling', action='store_true',
                        help='Continue labeling, skipping already labeled URLs')
    parser.add_argument('--stats', action='store_true',
                        help='Show dataset statistics and exit')
    
    return parser.parse_args()


def load_urls(args) -> List[str]:
    """Load URLs based on command line arguments."""
    urls = []
    
    if args.urls_file:
        # Load from text file
        try:
            loader = URLLoader()
            urls = loader.load_urls_from_file(args.urls_file)
            print(f"Loaded {len(urls)} URLs from {args.urls_file}")
        except Exception as e:
            print(f"Error loading URLs from file: {e}")
            return []
    
    elif args.json_file:
        # Load from JSON file
        try:
            loader = URLLoader()
            urls = loader.load_urls_from_json(args.json_file, args.url_key)
            print(f"Loaded {len(urls)} URLs from {args.json_file}")
        except Exception as e:
            print(f"Error loading URLs from JSON: {e}")
            return []
    
    else:
        # Load from database
        try:
            loader = URLLoader(args.db_path)
            
            if args.sample_size:
                urls = loader.create_balanced_sample(args.sample_size)
                print(f"Created balanced sample of {len(urls)} URLs")
            else:
                urls = loader.load_category_urls(domain=args.domain, limit=args.limit)
                print(f"Loaded {len(urls)} URLs from database")
                
                if args.domain:
                    print(f"Filtered by domain: {args.domain}")
                if args.limit:
                    print(f"Limited to: {args.limit} URLs")
                    
        except Exception as e:
            print(f"Error loading URLs from database: {e}")
            return []
    
    # Filter out already labeled URLs if requested
    if args.continue_labeling:
        try:
            data_manager = PLPDataManager(args.data_dir)
            labeled_samples = data_manager.load_samples()
            labeled_urls = {sample.url for sample in labeled_samples}
            
            original_count = len(urls)
            urls = [url for url in urls if url not in labeled_urls]
            
            print(f"Filtered out {original_count - len(urls)} already labeled URLs")
            print(f"Remaining URLs to label: {len(urls)}")
            
        except Exception as e:
            print(f"Warning: Could not filter labeled URLs: {e}")
    
    return urls


def show_statistics(args):
    """Show dataset statistics."""
    try:
        # Database statistics
        loader = URLLoader(args.db_path)
        domain_stats = loader.get_domain_stats()
        
        print("=== Database Statistics ===")
        print(f"Total URLs in database: {sum(domain_stats.values())}")
        print(f"Number of domains: {len(domain_stats)}")
        print("\nURLs by domain:")
        for domain, count in sorted(domain_stats.items(), key=lambda x: x[1], reverse=True):
            print(f"  {domain}: {count}")
        
        # Labeled data statistics
        data_manager = PLPDataManager(args.data_dir)
        labeled_stats = data_manager.get_dataset_stats()
        
        print(f"\n=== Labeled Data Statistics ===")
        print(f"Total labeled samples: {labeled_stats['total_samples']}")
        print(f"PLP samples: {labeled_stats['plp_samples']}")
        print(f"Non-PLP samples: {labeled_stats['non_plp_samples']}")
        print(f"Balance ratio: {labeled_stats['balance_ratio']:.2%}")
        
        if labeled_stats['domains']:
            print("\nLabeled samples by domain:")
            for domain, count in sorted(labeled_stats['domains'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {domain}: {count}")
        
    except Exception as e:
        print(f"Error showing statistics: {e}")


async def main():
    """Main function."""
    args = parse_arguments()
    
    # Show statistics and exit if requested
    if args.stats:
        show_statistics(args)
        return
    
    # Load URLs
    urls = load_urls(args)
    
    if not urls:
        print("No URLs to process. Use --help for usage information.")
        return
    
    print(f"\nStarting PLP Labeling Tool with {len(urls)} URLs")
    print(f"Data directory: {args.data_dir}")
    print("\nKeyboard shortcuts:")
    print("  0 - Label as 'Not PLP'")
    print("  1 - Label as 'PLP'")
    print("  Left/Right arrows - Navigate")
    print("  Space - Skip current URL")
    print("  Enter - Load/Reload current page")
    print("\nStarting GUI...")
    
    # Initialize data manager
    data_manager = PLPDataManager(args.data_dir)
    
    # Create and run GUI
    gui = PLPLabelerGUI(urls, data_manager)
    gui.run()
    
    print("\nLabeling session completed!")
    
    # Show final statistics
    final_stats = data_manager.get_dataset_stats()
    print(f"Final dataset size: {final_stats['total_samples']} samples")
    print(f"PLP samples: {final_stats['plp_samples']}")
    print(f"Non-PLP samples: {final_stats['non_plp_samples']}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nLabeling interrupted by user.")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1) 