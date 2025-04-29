#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

def count_whitespace_tokens(text: str) -> int:
    """Simple whitespace-based token count"""
    return len(text.split())

def count_gpt_tokens(text: str) -> int:
    """Count tokens using tiktoken (GPT tokenizer)"""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")  # GPT-4 encoder
        return len(enc.encode(text))
    except ImportError:
        print("Warning: tiktoken not installed. Run 'pip install tiktoken' for GPT token counting.")
        return 0

def main():
    parser = argparse.ArgumentParser(description='Count tokens in a file')
    parser.add_argument('file', type=str, help='Path to the file to analyze')
    parser.add_argument('--gpt', action='store_true', help='Use GPT tokenizer (requires tiktoken)')
    
    args = parser.parse_args()
    
    try:
        text = Path(args.file).read_text(encoding='utf-8')
        
        # Always show whitespace tokens
        ws_tokens = count_whitespace_tokens(text)
        print(f"Whitespace-based tokens: {ws_tokens:,}")
        
        # Show GPT tokens if requested
        if args.gpt:
            gpt_tokens = count_gpt_tokens(text)
            if gpt_tokens > 0:
                print(f"GPT tokens: {gpt_tokens:,}")
                
    except FileNotFoundError:
        print(f"Error: File '{args.file}' not found")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()