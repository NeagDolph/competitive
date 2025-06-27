import os
import glob
from llama_index.core import Document
from llama_index.llms.openrouter import OpenRouter
from llama_index.core import Settings
import asyncio
from dotenv import load_dotenv

# It's a good practice to set the API key from an environment variable
# Make sure to set OPENAI_API_KEY in your environment
load_dotenv()

# List of models to test
MODELS_TO_TEST = [
    "deepseek/deepseek-chat-v3-0324",
    "openai/gpt-4.1",
    "anthropic/claude-sonnet-4",
    "google/gemini-2.5-pro",
]

# The prompt to determine if the page is a PLP
PLP_PROMPT = """
Analyze the following HTML content and determine if it represents a Product Listing Page (PLP).
A Product Listing Page typically displays multiple products in a grid or list format.
Look for repeating patterns of product containers, each with elements like product images, names, prices, and links to product detail pages.
Respond with only 'True' if it is a PLP and 'False' if it is not.

HTML Content:
{html_content}
"""

async def is_plp(llm, html_content: str) -> bool:
    """
    Uses the given LLM to determine if the HTML content is a Product Listing Page.
    """
    try:
        response = await llm.acomplete(PLP_PROMPT.format(html_content=html_content))
        result = response.text.strip().lower()
        return 'true' in result
    except Exception as e:
        print(f"An error occurred: {e}")
        return False

async def main():
    """
    Main function to run the PLP detection tests.
    """
    html_files = glob.glob("test_html_outputs/*_cleaned.html")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

    for model_name in MODELS_TO_TEST:
        print(f"--- Testing Model: {model_name} ---")
        # Configure the LLM for the current model
        llm = OpenRouter(model=model_name, api_key=openrouter_api_key)

        for html_file in html_files:
            with open(html_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # To stay within token limits, we might need to truncate the content
            # A better approach for very large files would be to summarize or chunk them
            max_chars = 16000 # A safe limit for gpt-3.5-turbo context window
            if len(content) > max_chars:
                content = content[:max_chars]

            is_plp_result = await is_plp(llm, content)
            
            print(f"File: {os.path.basename(html_file)} -> Is PLP? {is_plp_result}")
        print("\\n")

if __name__ == "__main__":
    # To run the async main function
    asyncio.run(main()) 