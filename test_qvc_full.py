#!/usr/bin/env python3

import sys
import os
sys.path.append('.')

from util.universal_content_filter import UniversalProductFilter

def test_qvc_full():
    with open('test_html_outputs/qvc_com_raw.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    print("=== Testing Improved Filter on Full QVC HTML ===\n")
    
    filter_test = UniversalProductFilter(
        keep_top_n=20,
        verbose=True
    )
    
    results = filter_test.filter_content(html_content)
    
    print(f"\n=== RESULTS ===")
    print(f"Found {len(results)} fragments")
    
    for i, result in enumerate(results):
        print(f"\n--- FRAGMENT {i+1} (length: {len(result)}) ---")
        
        # Try to extract some key product info to see if it makes sense
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(result, 'html.parser')
        
        # Look for product names/descriptions
        product_desc = soup.find(['p', 'h1', 'h2', 'h3', 'h4'], class_=lambda x: x and 'product' in x.lower() and ('desc' in x.lower() or 'name' in x.lower() or 'title' in x.lower()))
        if product_desc:
            print(f"Product: {product_desc.get_text(strip=True)[:100]}")
        
        # Look for prices
        price_elem = soup.find(['span', 'p', 'div'], class_=lambda x: x and 'price' in x.lower())
        if price_elem:
            print(f"Price: {price_elem.get_text(strip=True)[:50]}")
        
        # Show first 200 chars
        print(f"Content preview: {result[:200]}...")
        print("-" * 60)

if __name__ == "__main__":
    test_qvc_full() 