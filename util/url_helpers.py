from urllib.parse import urlparse, urljoin

from util.types import Link

def get_base_domain(domain: str) -> str:
    """
    Retrieve the base domain of a URL, subdomain agnostically.
    """
    base = urlparse(domain).netloc
    if base.startswith("www."):
        return base[4:]
    return base

def normalize_url(url: str, base_url: str) -> str:
    """
        Normalize a URL path to be relative to passed base URL.
    """
    parsed = urlparse(url)
    if not parsed.netloc:
        return urljoin(base_url, url)
    return url


def prune_invalid_links(links: list[Link], entry_url: str) -> list[Link]:
    """
    Reduce links to only valid, internal, absolute links.
    Removes:
    - mailto: and tel: links
    - links that are just '#' or start with '#'
    - external links
    Ensures all links are absolute.
    """
    base_domain = get_base_domain(entry_url)
    reduced = []
    seen = set()
    for r in links:
        href = r.get("href")
        if not href:
            continue
        href = href.strip()
        # Remove mailto: and tel:
        if href.startswith("mailto:") or href.startswith("tel:"):
            continue
        # Remove links that are just '#' or start with '#'
        if href == "#" or href.startswith("#"):
            continue

        full_url = normalize_url(href, entry_url)

        # Remove external links
        if get_base_domain(full_url) != base_domain:
            continue

        # Remove duplicates
        if full_url in seen:
            continue

        r["href"] = full_url
        seen.add(full_url)
        reduced.append(r)
    return reduced
