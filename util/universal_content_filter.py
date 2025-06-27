import re
import torch
from dataclasses import dataclass
from typing import List
import numpy as np
from bs4 import BeautifulSoup, Tag
from pathlib import Path

# --- Model Loading ---
# Load models once when the module is imported. This is efficient for scripts
# that instantiate the filter multiple times.
try:
    import spacy
    from optimum.onnxruntime import ORTModelForFeatureExtraction
    from transformers import AutoTokenizer
    from sklearn.metrics.pairwise import cosine_similarity

    print("Loading NLP models (this may take a moment on first run)...")
    _nlp_model = spacy.load('en_core_web_sm')
    
    # --- Optimized ONNX Model Loading ---
    # This block checks for a local ONNX version of the model. If not found,
    # it converts the model and caches it for future, faster startups.
    _st_model_id = 'sentence-transformers/all-MiniLM-L6-v2'
    _onnx_path = Path("onnx_models") / _st_model_id.split('/')[-1]

    if _onnx_path.exists():
        print(f"-> Loading cached ONNX model from: {_onnx_path}")
        _embedding_model = ORTModelForFeatureExtraction.from_pretrained(_onnx_path, provider="CPUExecutionProvider")
        _tokenizer = AutoTokenizer.from_pretrained(_onnx_path)
    else:
        print(f"-> ONNX model not found locally. Converting and caching '{_st_model_id}'...")
        _embedding_model = ORTModelForFeatureExtraction.from_pretrained(_st_model_id, export=True, provider="CPUExecutionProvider")
        _tokenizer = AutoTokenizer.from_pretrained(_st_model_id)
        
        # Save the converted ONNX model for the next run
        print(f"-> Saving ONNX model to: {_onnx_path}")
        _onnx_path.mkdir(parents=True, exist_ok=True)
        _embedding_model.save_pretrained(_onnx_path)
        _tokenizer.save_pretrained(_onnx_path)
        print("-> Model caching complete.")
    # --- End Optimized ONNX Model Loading ---

    MODELS_AVAILABLE = True
    print("NLP models loaded successfully.")
except (ImportError, OSError) as e:
    _nlp_model, _embedding_model, _tokenizer = None, None, None
    MODELS_AVAILABLE = False
    print(f"Warning: NLP models not available. Please run 'pip install -r requirements_nlp.txt'. Error: {e}")
# --- End Model Loading ---

@dataclass
class _ScoredNode:
    """A simple data class to hold a DOM node and its calculated score."""
    score: float
    node: Tag

class UniversalProductFilter:
    """
    Universal e-commerce product filter that extracts individual product elements
    using a simplified and robust NLP-based approach.
    """
    
    # Regex for pre-filtering navigation and junk sections to avoid expensive NLP processing
    NAV_PATTERNS = [
        r"(?:nav|navigation|menu|header|footer|sidebar|breadcrumb)",
        r"(?:filter|sort|pagination|paging)", r"(?:newsletter|signup|login)",
        r"(?:social|share|follow)", r"(?:banner|ad|promo|marketing)",
        r"(?:review|rating|testimonial)(?:s|_list|_section)",
        r"(?:recommended|suggestion|upsell|cross[_-]?sell)",
        r"(?:category|department)[_-]?(?:nav|menu|list)",
    ]
    NEG_CLASS_RX = re.compile("|".join(NAV_PATTERNS), re.I)
    
    JUNK_TEXT_PATTERNS = [
        r"\b(?:home|about|contact|help|support|faq|terms|privacy|policy)\b",
        r"\b(?:sign\s+up|log\s+in|register|account|profile|settings)\b",
        r"\b(?:free\s+shipping|return\s+policy|customer\s+service)\b",
    ]
    NEG_TEXT_RX = re.compile("|".join(JUNK_TEXT_PATTERNS), re.I)

    def __init__(
        self,
        *,
        keep_top_n: int = 20,
        min_chars: int = 75,
        max_chars: int = 3500,
        min_words: int = 5,
        similarity_threshold: float = 0.90, # Increased threshold for stricter deduplication
        verbose: bool = False,
    ):
        if not MODELS_AVAILABLE:
            raise RuntimeError("NLP models are not available. Please install dependencies from requirements_nlp.txt")
            
        self.keep_top_n = keep_top_n
        self.min_chars = min_chars
        self.max_chars = max_chars
        self.min_words = min_words
        self.similarity_threshold = similarity_threshold
        self.verbose = verbose
        
        self.nlp = _nlp_model
        self.embedder = _embedding_model
        self.tokenizer = _tokenizer

    def filter_content(self, html: str) -> List[str]:
        """The main function to extract product snippets from HTML."""
        if not html:
            return []

        soup = self._make_soup(html)
        
        # 1. Find and score all potential product candidates using NLP
        candidates = self._find_and_score_candidates(soup)
        if not candidates:
            if self.verbose: print("[UniversalProductFilter] No suitable candidates found.")
            return []
            
        # 2. Deduplicate candidates to get a diverse set of products
        unique_candidates = self._deduplicate_candidates(candidates)
        
        # 3. Sort by score and return the top N results
        top_candidates = sorted(unique_candidates, key=lambda c: c.score, reverse=True)[:self.keep_top_n]

        if self.verbose:
            print(f"Found {len(candidates)} potential candidates.")
            print(f"After deduplication: {len(unique_candidates)} unique candidates.")
            print(f"Returning top {len(top_candidates)} results.")
            
        return [str(c.node) for c in top_candidates]

    def _find_and_score_candidates(self, soup: BeautifulSoup) -> List[_ScoredNode]:
        """Iterate through all elements, scoring them based on NLP and heuristics."""
        candidates = []
        for tag in soup.find_all(True):
            if not isinstance(tag, Tag) or not tag.name:
                continue
            
            text = tag.get_text(" ", strip=True)
            
            # --- Fast pre-filtering based on simple heuristics ---
            if not (self.min_chars < len(text) < self.max_chars):
                continue
            if len(text.split()) < self.min_words:
                continue
            if self._is_navigation_element(tag, text):
                continue
                
            # --- Score the element using NLP if it passes pre-filters ---
            score = self._score_element_with_nlp(tag, text)
            if score > 0:
                candidates.append(_ScoredNode(score, tag))
                
        return candidates

    def _score_element_with_nlp(self, tag: Tag, text: str) -> float:
        """Scores an element based on NLP analysis of its text and structure."""
        doc = self.nlp(text[:self.nlp.max_length])
        score = 0.0

        # Score based on named entities found by spaCy
        entity_scores = {"MONEY": 2.5, "PRODUCT": 2.0, "ORG": 0.5}
        for ent in doc.ents:
            score += entity_scores.get(ent.label_, 0)

        # Score based on product-related keywords
        product_keywords = ["sale", "discount", "offer", "review", "rating", "brand", "sku", "model"]
        score += sum(0.25 for keyword in product_keywords if keyword in text.lower())

        # Structural and density bonuses
        if tag.find('img'): score += 0.5
        if tag.find(['button', 'a'], text=re.compile(r"add|buy|cart", re.I)): score += 1.0
        score += (len(text) / (len(str(tag)) + 1e-6))  # Text-to-HTML ratio to favor content-rich nodes

        return score

    def _deduplicate_candidates(self, candidates: List[_ScoredNode]) -> List[_ScoredNode]:
        """Deduplicates candidates using semantic similarity and DOM structure."""
        if not candidates:
            return []

        # Sort by score descending to prioritize better candidates
        candidates = sorted(candidates, key=lambda c: c.score, reverse=True)

        # 1. Remove candidates that are nested inside other higher-scoring candidates
        candidates = self._remove_nested_candidates(candidates)

        # 2. Use semantic similarity to remove near-duplicate products
        descriptions = [self._extract_product_description(c.node) for c in candidates]
        
        # --- ONNX-based Semantic Embedding ---
        inputs = self.tokenizer(descriptions, padding=True, truncation=True, max_length=128, return_tensors="pt")
        with torch.no_grad():
            outputs = self.embedder(**inputs)
        embeddings = self._mean_pooling(outputs, inputs['attention_mask'])
        embeddings = embeddings.cpu().numpy()
        # --- End ONNX-based Semantic Embedding ---

        unique_candidates: List[_ScoredNode] = []
        indices_to_discard = set()

        for i in range(len(candidates)):
            if i in indices_to_discard:
                continue
            
            unique_candidates.append(candidates[i])
            
            # Find and discard candidates that are too similar to the current one
            for j in range(i + 1, len(candidates)):
                if j in indices_to_discard:
                    continue
                
                similarity = cosine_similarity([embeddings[i]], [embeddings[j]])[0][0]
                if similarity > self.similarity_threshold:
                    indices_to_discard.add(j)
                    
        return unique_candidates

    def _mean_pooling(self, model_output, attention_mask):
        """Helper function for sentence-transformer models."""
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def _remove_nested_candidates(self, candidates: List[_ScoredNode]) -> List[_ScoredNode]:
        """Removes candidates that are children of other candidates in the list."""
        nodes = [c.node for c in candidates]
        non_nested_candidates = []
        for i, c in enumerate(candidates):
            is_child_of_another_candidate = any(c.node in other_node.parents for j, other_node in enumerate(nodes) if i != j)
            if not is_child_of_another_candidate:
                non_nested_candidates.append(c)
        return non_nested_candidates
        
    def _is_navigation_element(self, tag: Tag, text: str) -> bool:
        """Checks if an element is likely part of navigation, a header, or a footer."""
        if tag.name in ["nav", "header", "footer", "aside"]:
            return True
        attr_text = " ".join([tag.get("id", ""), " ".join(tag.get("class", [])), tag.get("role", "")]).lower()
        if self.NEG_CLASS_RX.search(attr_text):
            return True
        if self.NEG_TEXT_RX.search(text[:200]): # Check only the start of the text
            return True
        return False
        
    def _extract_product_description(self, tag: Tag) -> str:
        """Extracts a concise description from a node for semantic comparison."""
        return ' '.join(tag.get_text(" ", strip=True).split()[:30])

    @staticmethod
    def _make_soup(html: str) -> BeautifulSoup:
        """Creates a BeautifulSoup object, ensuring it has a body tag."""
        soup = BeautifulSoup(html, "lxml")
        return soup if soup.body else BeautifulSoup(f"<body>{html}</body>", "lxml")
