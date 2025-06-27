import re, math
from abc import ABC
from collections import deque
from typing import List, Optional, Tuple, Set

from bs4 import BeautifulSoup, Tag, Comment, NavigableString

class EcommerceContentFilter(ABC):
    """
    Generic product / price extractor that returns *deduplicated* HTML fragments
    suitable for an LLM.  It is self-contained – no external BM25 import needed.
    """

    # -------------------------------------------------------- REGEX CONSTANTS
    _PRICE_RE = re.compile(
        r"""(?<![a-z0-9])([$€£]|USD|CAD|EUR|GBP)\s*\d[\d.,]*(?:[.,]\d{2})?(?!\w)""",
        re.I
    )
    _PRICE_ATTR_RE = re.compile(r"(price|amount|cost|value)", re.I)
    _NEG_CLASS_ID_RE = re.compile(
        r"nav|footer|header|sidebar|ads?|banner|coupon|newsletter|"
        r"promo|upsell|social|share|review|shipping|clearance",
        re.I
    )
    _NEG_TEXT_RE = re.compile(
        r"\b(sale|discount|percent off|save \d|free shipping)\b", re.I
    )

    # -------------------------------------------------------- CONSTRUCTOR
    def __init__(
        self,
        retention_threshold: float = 0.3,
        min_word_threshold: int = 2,
        verbose: bool = False,
    ):
        """
        retention_threshold: ratio of low-scoring candidates to delete
        verbose: bool = False,
        """
        self.retention_threshold = retention_threshold
        self.max_chars = 800
        self.min_word_threshold = min_word_threshold
        self.verbose = verbose

        # Scoring weights
        self.W_PRICE = 2.5
        self.W_QUERY = 1.0
        self.W_DENS  = 0.6
        self.W_TAG   = 0.3

        self.TAG_W = {  # base usefulness of a tag
            "h1": 1.4, "h2": 1.3, "h3": 1.2,
            "p": 1.1, "li": 1.0,
            "article": 1.5, "section": 1.3,
            "div": 0.6,
            "span": 0.3,
        }

    # -------------------------------------------------------- PUBLIC API
    def filter_content(self, html: str) -> List[str]:
        """
        Parse `html` and return up to `keep_top_n` HTML snippets that contain
        product name/price pairs, with duplicates and promos removed.
        """
        if not html:
            return []

        soup = BeautifulSoup(html, "lxml")
        if not soup.body:
            soup = BeautifulSoup(f"<body>{html}</body>", "lxml")

        # --- 1) strip obvious junk
        for c in soup(text=lambda t: isinstance(t, Comment)):
            c.extract()
        for bad in soup(["script", "style", "noscript", "svg", "iframe", "form"]):
            bad.decompose()

        # --- 2) depth-first walk, collect scored candidates
        candidates: list[tuple[int, float, Tag]] = []  # (order, score, node)
        order = 0
        for node in soup.body.descendants:
            if node is None:
                continue
            if not isinstance(node, Tag):
                continue
            if node.name not in self.TAG_W:
                continue

            # reject promo wrappers early
            if self._is_promo(node):
                continue

            text = node.get_text(" ", strip=True)
            if not text:
                continue

            # keep tiny price nodes, but otherwise need >= min words
            if not self._looks_like_price(text, node) and len(text.split()) < self.min_word_threshold:
                continue

            # compute score
            score = self._score(node, text)
            candidates.append((order, score, node))
            order += 1

        if not candidates:
            return []

        # --- 3) sort & select best, but deduplicate along the way
        candidates.sort(key=lambda t: (-t[1], t[0]))   # score desc, doc order asc

        accepted: list[Tag] = []
        covered_ranges: list[tuple[int, int]] = []  # (start_line, end_line)

        for _, _, node in candidates:
            if node is None or node.attrs is None:
                continue
            if len(accepted) >= self.keep_top_n:
                break
            if self._covered_by_accepted(node, covered_ranges):
                continue

            block = self._crop_to_price_card(node)  # guarantee price+title+compact
            start, end = self._node_source_range(block)
            covered_ranges.append((start, end))
            accepted.append(block)

        # de-dupe identical HTML strings (edge cases)
        seen_html: Set[str] = set()
        result: List[str] = []
        for node in sorted(accepted, key=lambda n: n.sourceline or 0):
            html_txt = str(node)
            if html_txt in seen_html:
                continue
            seen_html.add(html_txt)
            result.append(html_txt)

        return result

    # ========================================================  helpers
    # ---------------- price / promo detectors
    def _looks_like_price(self, text: str, node: Tag) -> bool:
        if self._PRICE_RE.search(text):
            return True
        for attr in ("class", "id", "itemprop", "data-price", "aria-label"):
            v = node.get(attr)
            if not v:
                continue
            if isinstance(v, list):
                v = " ".join(v)
            if self._PRICE_ATTR_RE.search(str(v)):
                return True
        return False

    def _is_promo(self, node: Tag) -> bool:
        class_id = " ".join(
            filter(None, [" ".join(node.get("class", [])), node.get("id", "")])
        )
        if self._NEG_CLASS_ID_RE.search(class_id):
            return True
        head = node.get_text(" ", strip=True)[:120]
        return bool(self._NEG_TEXT_RE.search(head))

    # ---------------- scoring
    def _score(self, node: Tag, text: str) -> float:
        has_price = self._looks_like_price(text, node)
        tag_len   = len(node.encode_contents())
        dens      = len(text) / tag_len if tag_len else 0
        sim       = self._query_sim(text)

        score = (
            self.W_PRICE * (1.0 if has_price else 0.0)
            + self.W_QUERY * sim
            + self.W_DENS  * dens
            + self.W_TAG   * self.TAG_W.get(node.name, 0.5)
        )
        return score

    def _query_sim(self, text: str) -> float:
        if not self.user_query:
            return 0.0
        q_tokens = set(self.user_query.split())
        t_tokens = set(text.lower().split())
        if not q_tokens:
            return 0.0
        return len(q_tokens & t_tokens) / len(q_tokens)

    # ---------------- compacting / dedup logic
    def _crop_to_price_card(self, node: Tag) -> Tag:
        """
        Starting from `node` (which already contains a price), climb until we
        hit max_chars or we lose the price, whichever comes first, then strip
        promo descendants.  The returned Tag is *the* snippet we keep.
        """
        current = node
        while current.parent and current.parent.name != "body":
            parent = current.parent
            txt = parent.get_text(" ", strip=True)
            if len(txt) > self.max_chars:
                break
            if not self._looks_like_price(txt, parent):
                break  # climbed too far
            current = parent

        # finally, delete promo elements inside the block
        for desc in list(current.descendants):
            if desc is None:
                continue
            if isinstance(desc, Tag) and desc.attrs is not None and self._is_promo(desc):
                desc.decompose()
        return current

    def _covered_by_accepted(self, node: Tag, ranges: List[tuple[int, int]]) -> bool:
        """
        True if `node` lies completely inside any already-accepted block.
        Requires the parser to have set sourceline/sourcepos (lxml does).
        """
        start, end = self._node_source_range(node)
        for s, e in ranges:
            if s <= start and end <= e:
                return True
        return False

    @staticmethod
    def _node_source_range(node: Tag) -> Tuple[int, int]:
        """
        Returns (start_line, end_line).  When line numbers are missing
        we return a conservative synthetic range.
        """

        try:
            start = node.sourceline or 0
        except AttributeError:
            start = 0

        # `sourcepos` is not always set; approximate by text length
        txt_len = len(str(node).splitlines())
        return (start, start + txt_len)
