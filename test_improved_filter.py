#!/usr/bin/env python3

import sys
import os
sys.path.append('.')

from util.universal_content_filter import UniversalProductFilter

def test_filter_on_html(html_file, label):
    # Read the HTML
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    print(f"=== Testing Improved UniversalProductFilter on {label} ===\n")
    
    # Test with the new improved filter
    filter_new = UniversalProductFilter(
        keep_top_n=15,
        retention_ratio=0.8,
        verbose=True,
        preserve_product_diversity=True
    )
    
    results = filter_new.filter_content(html_content)
    
    print(f"\nFound {len(results)} product elements")
    
    if results:
        print("\n" + "="*80 + "\n")
        
        # Show first few results to see the diversity
        for i, result in enumerate(results[:3]):
            print(f"ELEMENT {i+1} (length: {len(result)}):")
            print("-" * 40)
            # Show more text to understand what we're getting
            if len(result) > 800:
                print(result[:400] + "\n...\n" + result[-400:])
            else:
                print(result)
            print("\n")
    else:
        print("No results found!")

def test_filter_on_qvc():
    test_filter_on_html('test_html_outputs/qvc_com_raw.html', 'QVC HTML')

def test_filter_on_hsn():
    test_filter_on_html('test_html_outputs/hsn_com_cleaned.html', 'HSN HTML')

if __name__ == "__main__":
    test_filter_on_hsn()
    print("\n" + "="*100 + "\n")
    test_filter_on_qvc() 