import fnmatch
from typing import Iterable
from crawl4ai import PruningContentFilter

from bs4 import BeautifulSoup

from util.ecommerce_content_filter import EcommerceContentFilter
from util.universal_content_filter import UniversalProductFilter

def clean_tags(html: str, tags: list) -> str:
    """
    Removes all passed tags from the HTML string.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in tags:
        for t in soup.find_all(tag):
            t.decompose()
    return str(soup)

def clean_attributes(html: str, attributes: Iterable[str]) -> str:
    """
    Remove attributes from every element in html.

    attributes may contain exact names (e.g. "class") or shell-style wildcards (e.g. "data-*", "aria-??").
    """
    soup = BeautifulSoup(html, "html.parser")

    # Split requested attributes into exact names and wildcard patterns
    exact_names   = {a for a in attributes if "*" not in a and "?" not in a}
    wildcard_pats = [a for a in attributes if a not in exact_names]

    for tag in soup.find_all(True):
        # Work on a copy of tag.attrs so we can delete safely while iterating
        for attr in list(tag.attrs):
            if (
                attr in exact_names
                or any(fnmatch.fnmatch(attr, pat) for pat in wildcard_pats)
            ):
                del tag.attrs[attr]

    return str(soup)

def prettify_html(html: str) -> str:
    """
    Prettify the HTML string.
    """
    soup = BeautifulSoup(html, "html.parser")
    return soup.prettify()


def clean_html_for_llm(html: str) -> str:
    """
    Cleans HTML by removing unwanted tags and attributes and pruning content.
    """

    prune_filter = UniversalProductFilter(
        # Lower → more content retained, higher → more content pruned
        keep_top_n=200,
        retention_ratio=0.2,
        user_query="$ USD CAD AUD EUR GBP JPY INR price cost sale buy add to cart checkout order product item size color"
    )

    pruned_html = prune_filter.filter_content(html)
    filtered_html = "\n".join(pruned_html)

    tags_to_remove = ['style', 'script', 'form', 'header', 'footer', 'noscript']
    attributes_to_remove = [
        'style', 
        'aria-??',
        'role', 
        'data-pct-off-codes', 
        'data-module-*', 
        'tab-index',
        'data-testid',
        'data-test-id',
    ]

    filtered_html = clean_tags(filtered_html, tags_to_remove)
    filtered_html = clean_attributes(filtered_html, attributes_to_remove)

    filtered_html = prettify_html(filtered_html)

    return filtered_html