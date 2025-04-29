import re
from collections import deque
from dataclasses import dataclass
from typing import List, Tuple, Set, Optional
import copy


from bs4 import BeautifulSoup, Tag, Comment, NavigableString


@dataclass
class _ScoredNode:
    order: int
    score: float
    node: Tag


class UniversalProductFilter:
    """
    Prunes raw e-commerce HTML down to *deduplicated* “price-card” fragments
    that an LLM can safely chunk and embed.  All heuristics are retailer-agnostic
    and tunable via the constructor.
    """

    # ------------------------------------------------------------------ regexes
    PRICE_RX        = re.compile(
        r"""(?<!\w)(?:[$€£¥₹]|USD|CAD|AUD|EUR|GBP|JPY|INR)\s*
            \d{1,3}(?:[,\s]\d{3})*(?:[.,]\d{2})?(?!\w)""",
        re.I | re.X,
    )
    PRICE_ATTR_RX   = re.compile(r"(price|amount|cost|value)", re.I)
    NEG_CLASS_RX    = re.compile(
        r"(?:nav|header|footer|aside|sidebar|banner|ads?|coupon|newsletter|"
        r"promo|upsell|social|share|breadcrumb|filter|facet|sort)",
        re.I,
    )
    NEG_TEXT_RX     = re.compile(
        r"\b(?:sale|discount|percent off|save \d|free shipping)\b", re.I
    )

    # Default tag weights – higher ⇒ potentially more information–dense
    TAG_W = {
        "h1": 1.4, "h2": 1.3, "h3": 1.2,
        "p":  1.1, "li": 1.0,
        "section": 1.3, "article": 1.3,
        "div": 0.6, "span": 0.4,
    }

    STRIP_TAGS = {"script", "style", "svg", "iframe", "form", "noscript"}

    # ----------------------------------------------------------------- ctor
    def __init__(
        self,
        *,
        keep_top_n: int = 40,
        retention_ratio: float = 0.5,
        min_words: int = 2,
        max_chars: int = 800,
        user_query: str | None = None,
        verbose: bool = False,
    ):
        """
        keep_top_n      : hard ceiling on number of fragments returned
        retention_ratio : fraction of *sorted* candidates to preserve
                          (ignored if keep_top_n is hit first)
        min_words       : reject nodes with fewer words unless they look like a price
        max_chars       : trim candidate cards to this length (↑ = more context)
        user_query      : optional search-query similarity boost
        """
        self.keep_top_n = keep_top_n
        self.retention_ratio = max(0.0, min(retention_ratio, 1.0))
        self.min_words = min_words
        self.max_chars = max_chars
        self.user_query = (user_query or "").lower()
        self.verbose = verbose

        #    W_PRICE | W_QUERY | W_DENS | W_TAG
        self.W = (2.6, 1.0, 0.6, 0.3)

    # ============================================================  public
    def filter_content(self, html: str) -> List[str]:
        """Return a list of HTML snippets suitable for an LLM vectoriser."""
        if not html:
            return []

        soup = self._make_soup(html)

        # -- A/B) strip obvious junk + wrapper elements in one DFS pass
        for node in list(soup.body.descendants):
            if node is None:
                continue
            # if isinstance(node, Comment):
            #     node.extract()
            #     continue
            if node.name in self.STRIP_TAGS:
                node.decompose()
                continue
            if isinstance(node, Tag) and self._is_junk_wrapper(node):
                node.decompose()

        # -- C) candidate discovery + scoring
        candidates: list[_ScoredNode] = []
        order = 0
        for tag in soup.body.descendants:
            if not isinstance(tag, Tag):
                continue
            if tag.name not in self.TAG_W:
                continue

            txt = tag.get_text(" ", strip=True)
            if not txt:
                continue
            # allow short nodes *only* if they clearly look like a price
            if not self._looks_like_price(txt, tag) and len(txt.split()) < self.min_words:
                continue

            candidates.append(
                _ScoredNode(order, self._score(tag, txt), tag)
            )
            order += 1

        if not candidates:
            return []

        # Optional retention-ratio pre-prune (cheap way to drop tail)
        candidates.sort(key=lambda x: x.score, reverse=True)
        keep_count = min(
            self.keep_top_n,
            max(1, int(len(candidates) * self.retention_ratio)),
        )
        candidates = candidates[:keep_count]

        # ---------------------------------------------------- D/E/F) compact, dedupe
        accepted: list[Tag] = []
        covered: list[Tuple[int, int]] = []       # (start_line, end_line)
        for cand in sorted(candidates, key=lambda c: (-c.score, c.order)):
            if len(accepted) >= self.keep_top_n:
                break
            card = self._compact_to_card(cand.node)
            if self._is_subrange(card, covered):
                continue
            accepted.append(self._wrap_with_ancestry(card))
            covered.append(self._node_range(card))

        unique_html: Set[str] = set()
        result: List[str] = []
        for n in sorted(accepted, key=lambda n: n.sourceline or 0):
            h = str(n)
            if h not in unique_html:
                unique_html.add(h)
                result.append(h)

        if self.verbose:
            print(f"[UniversalProductFilter] returned {len(result)} fragments")
        return result

    # =====================================================  internal helpers

    def _wrap_with_ancestry(self, node: Tag) -> Tag:
        """
        Clone `node` and every ancestor up to <body>, but
        *only* keep the single child that leads to `node` on each level.
        This preserves structural context without re-introducing siblings.
        """
        soup = BeautifulSoup("", "lxml")
        # shallow-copy the card (no parents) first
        clone = copy.copy(node)
        clone.clear()
        # deep-copy its *contents* to retain children exactly as they are
        for child in node.contents:
            clone.append(copy.copy(child))

        parent = node.parent
        child_clone = clone
        # walk upwards until <body>, re-creating the chain
        while parent and parent.name != "body":
            parent_clone = copy.copy(parent)
            parent_clone.clear()
            parent_clone.append(child_clone)
            child_clone = parent_clone
            parent = parent.parent

        return child_clone

    # ---------- price & promo checks
    def _looks_like_price(self, text: str, node: Tag) -> bool:
        if self.PRICE_RX.search(text):
            return True
        for attr in ("class", "id", "itemprop", "data-price", "aria-label"):
            v = node.get(attr)
            if not v:
                continue
            if isinstance(v, list):
                v = " ".join(v)
            if self.PRICE_ATTR_RX.search(str(v)):
                return True
        return False

    def _is_junk_wrapper(self, node: Tag) -> bool:
        # tag name already filtered in STRIP_TAGS, here we look at class/id/text
        attrs = ""
        if node.attrs is not None:
            attrs = " ".join(
                filter(None, [" ".join(node.get("class", [])), node.get("id", "")])
            )
        if self.NEG_CLASS_RX.search(attrs):
            return True
        head = node.get_text(" ", strip=True)[:120]
        return bool(self.NEG_TEXT_RX.search(head))

    # ---------- scoring
    def _score(self, node: Tag, text: str) -> float:
        has_price = self._looks_like_price(text, node)
        html_len  = len(node.encode_contents())
        dens      = len(text) / html_len if html_len else 0.0
        q_sim     = self._query_similarity(text)
        tag_w     = self.TAG_W.get(node.name, 0.5)
        w_price, w_query, w_dens, w_tag = self.W

        return (
            w_price * int(has_price)
            + w_query * q_sim
            + w_dens  * dens
            + w_tag   * tag_w
        )

    def _query_similarity(self, text: str) -> float:
        if not self.user_query:
            return 0.0
        q_tokens = set(self.user_query.split())
        t_tokens = set(text.lower().split())
        return len(q_tokens & t_tokens) / len(q_tokens) if q_tokens else 0.0

    # ---------- compaction / deduplication
    def _compact_to_card(self, node: Tag) -> Tag:
        current = node
        while current.parent and current.parent.name != "body":
            par = current.parent
            if len(par.get_text(" ", strip=True)) > self.max_chars:
                break
            # Stop climbing if the *parent* no longer contains the price token
            if not self._looks_like_price(par.get_text(" ", strip=True), par):
                break
            current = par

        # Deep-clean promo descendants inside the kept block
        for d in list(current.descendants):
            if isinstance(d, Tag) and self._is_junk_wrapper(d):
                d.decompose()

        return current

    def _is_subrange(self, node: Tag, ranges: List[Tuple[int, int]]) -> bool:
        n_start, n_end = self._node_range(node)
        return any(s <= n_start and n_end <= e for s, e in ranges)

    @staticmethod
    def _node_range(node: Tag) -> Tuple[int, int]:
        start = getattr(node, "sourceline", 0) or 0
        txt_lines = len(str(node).splitlines())
        return start, start + txt_lines

    # ---------- soup
    @staticmethod
    def _make_soup(html: str) -> BeautifulSoup:
        soup = BeautifulSoup(html, "lxml")
        if not soup.body:
            # fragment – wrap in <body> so .body.descendants works
            soup = BeautifulSoup(f"<body>{html}</body>", "lxml")
        return soup
