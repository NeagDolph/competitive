import sys
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional
import json

# Add parent directory to path to import from main project
sys.path.append(str(Path(__file__).parent.parent))

from db import DB
from util.url_helpers import get_base_domain


class URLLoader:
    """
    Utility class to load URLs from various sources for the PLP labeling tool.
    """
    
    def __init__(self, db_path: str = "crawler_data.db"):
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            self.db_path = Path("..") / db_path
        
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        self.db = DB(str(self.db_path))
    
    def load_category_urls(self, domain: Optional[str] = None, limit: Optional[int] = None) -> List[str]:
        """
        Load category URLs from the database.
        
        Args:
            domain: Optional domain filter
            limit: Optional limit on number of URLs
            
        Returns:
            List of URLs
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Build query
            query = "SELECT url FROM category_links"
            params = []
            
            if domain:
                query += " WHERE domain = ?"
                params.append(domain)
            
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            cursor.execute(query, params)
            urls = [row[0] for row in cursor.fetchall()]
            
            conn.close()
            return urls
            
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return []
    
    def load_urls_from_file(self, file_path: str) -> List[str]:
        """
        Load URLs from a text file (one URL per line).
        
        Args:
            file_path: Path to the text file
            
        Returns:
            List of URLs
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        urls = []
        with open(file_path, 'r') as f:
            for line in f:
                url = line.strip()
                if url and not url.startswith('#'):  # Skip empty lines and comments
                    urls.append(url)
        
        return urls
    
    def load_urls_from_json(self, file_path: str, url_key: str = "url") -> List[str]:
        """
        Load URLs from a JSON file.
        
        Args:
            file_path: Path to the JSON file
            url_key: Key name for URL in JSON objects
            
        Returns:
            List of URLs
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        urls = []
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and url_key in item:
                    urls.append(item[url_key])
                elif isinstance(item, str):
                    urls.append(item)
        elif isinstance(data, dict):
            # Single object or nested structure
            if url_key in data:
                urls.append(data[url_key])
        
        return urls
    
    def get_domain_stats(self) -> Dict[str, int]:
        """
        Get statistics about URLs by domain.
        
        Returns:
            Dictionary mapping domain to URL count
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("SELECT domain, COUNT(*) FROM category_links GROUP BY domain")
            stats = dict(cursor.fetchall())
            
            conn.close()
            return stats
            
        except sqlite3.Error as e:
            print(f"Database error: {e}")
            return {}
    
    def get_unlabeled_urls(self, labeled_urls_file: str) -> List[str]:
        """
        Get URLs that haven't been labeled yet.
        
        Args:
            labeled_urls_file: Path to file containing already labeled URLs
            
        Returns:
            List of unlabeled URLs
        """
        all_urls = self.load_category_urls()
        
        # Load already labeled URLs
        labeled_urls = set()
        labeled_file = Path(labeled_urls_file)
        if labeled_file.exists():
            with open(labeled_file, 'r') as f:
                for line in f:
                    if line.strip():
                        try:
                            data = json.loads(line.strip())
                            labeled_urls.add(data.get('url', ''))
                        except json.JSONDecodeError:
                            continue
        
        # Return unlabeled URLs
        return [url for url in all_urls if url not in labeled_urls]
    
    def create_balanced_sample(self, total_count: int, by_domain: bool = True) -> List[str]:
        """
        Create a balanced sample of URLs for labeling.
        
        Args:
            total_count: Total number of URLs to sample
            by_domain: Whether to balance by domain
            
        Returns:
            List of sampled URLs
        """
        if not by_domain:
            urls = self.load_category_urls(limit=total_count)
            return urls
        
        # Get domain stats
        domain_stats = self.get_domain_stats()
        if not domain_stats:
            return []
        
        # Calculate URLs per domain
        num_domains = len(domain_stats)
        urls_per_domain = max(1, total_count // num_domains)
        
        balanced_urls = []
        for domain in domain_stats:
            domain_urls = self.load_category_urls(domain=domain, limit=urls_per_domain)
            balanced_urls.extend(domain_urls)
            
            if len(balanced_urls) >= total_count:
                break
        
        return balanced_urls[:total_count]


def main():
    """Example usage of URLLoader."""
    try:
        loader = URLLoader()
        
        # Show domain statistics
        print("Domain Statistics:")
        stats = loader.get_domain_stats()
        for domain, count in stats.items():
            print(f"  {domain}: {count} URLs")
        
        print("\nSample URLs:")
        urls = loader.create_balanced_sample(10)
        for i, url in enumerate(urls, 1):
            print(f"  {i}. {url}")
        
    except Exception as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    main() 