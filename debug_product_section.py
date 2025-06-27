#!/usr/bin/env python3

import sys
import os
sys.path.append('.')

from util.universal_content_filter import UniversalProductFilter
from bs4 import BeautifulSoup

def test_product_section():
    # Read QVC HTML
    with open('test_html_outputs/qvc_com_raw.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract just the product listing section
    soup = BeautifulSoup(content, 'lxml')
    product_section = soup.find('div', {'data-total-products': True})
    
    if not product_section:
        print("Could not find product section!")
        return
        
    print(f"Found product section with {product_section.get('data-total-products')} products")
    
    # Find individual gallery items first
    gallery_items = product_section.find_all('div', class_=lambda x: x and 'galleryItem' in x)
    print(f"Found {len(gallery_items)} gallery items directly")
    
    # Show first few gallery items
    for i, item in enumerate(gallery_items[:3]):
        print(f"\n--- GALLERY ITEM {i+1} ---")
        item_id = item.get('data-item-id', 'no-id')
        print(f"Item ID: {item_id}")
        
        # Look for product name
        product_desc = item.find('p', class_='productDesc')
        if product_desc:
            print(f"Product: {product_desc.get_text(strip=True)}")
            
        # Look for price
        price_elem = item.find(['span', 'p'], class_=lambda x: x and 'price' in x.lower())
        if price_elem:
            print(f"Price: {price_elem.get_text(strip=True)}")
            
        print(f"Content length: {len(str(item))}")
    
    print("\n" + "="*60)
    print("Now testing filter on this section...")
    
    # Test filter on just this section
    filter_test = UniversalProductFilter(
        keep_top_n=10,
        retention_ratio=0.9,
        verbose=True,
        preserve_product_diversity=True,
        max_chars=500  # Limit tree climbing
    )
    
    results = filter_test.filter_content(str(product_section))
    
    print(f"\n=== FILTER RESULTS ===")
    print(f"Found {len(results)} fragments")
    
    for i, result in enumerate(results):
        print(f"\n--- FILTERED FRAGMENT {i+1} (length: {len(result)}) ---")
        
        # Parse and analyze
        soup = BeautifulSoup(result, 'html.parser')
        
        # Check if it's a gallery item
        gallery_item = soup.find('div', class_=lambda x: x and 'galleryItem' in x)
        if gallery_item:
            item_id = gallery_item.get('data-item-id', 'no-id')
            print(f"✓ Gallery Item ID: {item_id}")
            
            # Product name
            product_desc = gallery_item.find('p', class_='productDesc')
            if product_desc:
                print(f"✓ Product: {product_desc.get_text(strip=True)}")
                
            # Price
            price_elem = gallery_item.find(['span', 'p'], class_=lambda x: x and 'price' in x.lower())
            if price_elem:
                print(f"✓ Price: {price_elem.get_text(strip=True)[:50]}")
        else:
            # Check if it contains gallery items as children
            child_gallery_items = soup.find_all('div', class_=lambda x: x and 'galleryItem' in x)
            if child_gallery_items:
                print(f"✓ Contains {len(child_gallery_items)} gallery items as children")
                for idx, child in enumerate(child_gallery_items[:2]):
                    item_id = child.get('data-item-id', 'no-id')
                    product_desc = child.find('p', class_='productDesc')
                    product_name = product_desc.get_text(strip=True) if product_desc else "no name"
                    print(f"  Child {idx+1}: {item_id} - {product_name[:40]}")
            else:
                print("✗ Not a gallery item and contains no gallery item children")
                print(f"Content: {result[:200]}...")

if __name__ == "__main__":
    test_product_section() 