import json
import hashlib
import os
import asyncio
import aiofiles
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import torch
from torch.utils.data import Dataset
import pandas as pd


@dataclass
class PLPSample:
    """Data class representing a single PLP sample with HTML content and label."""
    url: str
    html_content: str
    is_plp: int  # 0 or 1
    timestamp: str
    domain: str
    content_hash: str
    cleaned_html: Optional[str] = None
    
    def to_dict(self) -> Dict:
        return asdict(self)


class PLPDataManager:
    """
    Manages storage and retrieval of PLP labeling data in a format optimized for PyTorch training.
    """
    
    def __init__(self, data_dir: str = "plp_data"):
        self.data_dir = Path(data_dir)
        self.html_dir = self.data_dir / "html_files"
        self.labels_file = self.data_dir / "labels.jsonl"
        self.metadata_file = self.data_dir / "metadata.json"
        
        # Create directories if they don't exist
        self.data_dir.mkdir(exist_ok=True)
        self.html_dir.mkdir(exist_ok=True)
        
        # Initialize metadata
        self._load_metadata()
    
    def _load_metadata(self):
        """Load or initialize metadata about the dataset."""
        if self.metadata_file.exists():
            with open(self.metadata_file, 'r') as f:
                self.metadata = json.load(f)
        else:
            self.metadata = {
                "created_at": datetime.utcnow().isoformat(),
                "total_samples": 0,
                "domains": {},
                "label_distribution": {"0": 0, "1": 0}
            }
            self._save_metadata()
    
    def _save_metadata(self):
        """Save metadata to disk."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
    
    def _get_content_hash(self, content: str) -> str:
        """Generate a hash for the HTML content to detect duplicates."""
        return hashlib.md5(content.encode('utf-8')).hexdigest()
    
    def _get_domain(self, url: str) -> str:
        """Extract domain from URL."""
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace('www.', '')
    
    async def save_sample(self, url: str, html_content: str, is_plp: int, cleaned_html: Optional[str] = None) -> bool:
        """
        Save a labeled sample to the dataset.
        
        Args:
            url: The URL of the page
            html_content: Raw HTML content
            is_plp: Label (0 for not PLP, 1 for PLP)
            cleaned_html: Optional cleaned HTML content
            
        Returns:
            bool: True if saved successfully, False if duplicate
        """
        content_hash = self._get_content_hash(html_content)
        domain = self._get_domain(url)
        
        # Check for duplicates
        if await self._is_duplicate(content_hash):
            print(f"Duplicate content detected for {url}, skipping...")
            return False
        
        # Create sample
        sample = PLPSample(
            url=url,
            html_content="",  # We'll store this separately
            is_plp=is_plp,
            timestamp=datetime.utcnow().isoformat(),
            domain=domain,
            content_hash=content_hash,
            cleaned_html=""  # We'll store this separately too
        )
        
        # Save HTML content to separate file
        html_filename = f"{content_hash}.html"
        html_path = self.html_dir / html_filename
        
        async with aiofiles.open(html_path, 'w', encoding='utf-8') as f:
            await f.write(html_content)
        
        # Save cleaned HTML if provided
        if cleaned_html:
            cleaned_filename = f"{content_hash}_cleaned.html"
            cleaned_path = self.html_dir / cleaned_filename
            async with aiofiles.open(cleaned_path, 'w', encoding='utf-8') as f:
                await f.write(cleaned_html)
        
        # Append to labels file
        async with aiofiles.open(self.labels_file, 'a', encoding='utf-8') as f:
            await f.write(json.dumps(sample.to_dict()) + '\n')
        
        # Update metadata
        self.metadata["total_samples"] += 1
        self.metadata["label_distribution"][str(is_plp)] += 1
        if domain not in self.metadata["domains"]:
            self.metadata["domains"][domain] = 0
        self.metadata["domains"][domain] += 1
        self._save_metadata()
        
        print(f"Saved sample: {url} -> {is_plp} (hash: {content_hash})")
        return True
    
    async def _is_duplicate(self, content_hash: str) -> bool:
        """Check if content with this hash already exists."""
        if not self.labels_file.exists():
            return False
        
        async with aiofiles.open(self.labels_file, 'r', encoding='utf-8') as f:
            async for line in f:
                if line.strip():
                    sample_data = json.loads(line.strip())
                    if sample_data.get('content_hash') == content_hash:
                        return True
        return False
    
    def load_samples(self) -> List[PLPSample]:
        """Load all samples from the dataset."""
        samples = []
        if not self.labels_file.exists():
            return samples
        
        with open(self.labels_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    sample_data = json.loads(line.strip())
                    samples.append(PLPSample(**sample_data))
        
        return samples
    
    def get_html_content(self, content_hash: str, cleaned: bool = False) -> Optional[str]:
        """Retrieve HTML content by hash."""
        suffix = "_cleaned.html" if cleaned else ".html"
        html_path = self.html_dir / f"{content_hash}{suffix}"
        
        if html_path.exists():
            with open(html_path, 'r', encoding='utf-8') as f:
                return f.read()
        return None
    
    def get_dataset_stats(self) -> Dict:
        """Get statistics about the current dataset."""
        return {
            "total_samples": self.metadata["total_samples"],
            "plp_samples": self.metadata["label_distribution"]["1"],
            "non_plp_samples": self.metadata["label_distribution"]["0"],
            "domains": self.metadata["domains"],
            "balance_ratio": self.metadata["label_distribution"]["1"] / max(1, self.metadata["total_samples"])
        }
    
    def export_to_pytorch_dataset(self) -> 'PLPDataset':
        """Export data as a PyTorch Dataset."""
        return PLPDataset(self)


class PLPDataset(Dataset):
    """PyTorch Dataset for PLP classification."""
    
    def __init__(self, data_manager: PLPDataManager, use_cleaned: bool = True):
        self.data_manager = data_manager
        self.use_cleaned = use_cleaned
        self.samples = data_manager.load_samples()
    
    def __len__(self):
        return len(self.samples)
    
    def __getitem__(self, idx):
        sample = self.samples[idx]
        
        # Get HTML content
        html_content = self.data_manager.get_html_content(
            sample.content_hash, 
            cleaned=self.use_cleaned
        )
        
        # If cleaned version not available, fall back to raw
        if html_content is None and self.use_cleaned:
            html_content = self.data_manager.get_html_content(
                sample.content_hash, 
                cleaned=False
            )
        
        return {
            'url': sample.url,
            'html_content': html_content or "",
            'label': sample.is_plp,
            'domain': sample.domain,
            'timestamp': sample.timestamp
        }
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert dataset to pandas DataFrame for analysis."""
        data = []
        for i in range(len(self)):
            item = self[i]
            data.append({
                'url': item['url'],
                'label': item['label'],
                'domain': item['domain'],
                'timestamp': item['timestamp'],
                'html_length': len(item['html_content'])
            })
        return pd.DataFrame(data) 