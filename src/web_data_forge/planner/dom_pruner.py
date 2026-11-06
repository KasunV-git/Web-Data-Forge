"""
DOM Pruner and Token Optimizer for AI Extraction Planning.
Prepares web page HTML for LLM analysis by stripping noisy tags,
filtering non-essential attributes, enforcing token budgets, and
wrapping content in prompt-injection containment delimiters.
"""

from typing import List, Optional, Set
from bs4 import BeautifulSoup, Comment


# Tags to strip entirely (tag and contents)
STRIP_TAGS: Set[str] = {
    "script",
    "style",
    "svg",
    "noscript",
    "meta",
    "link",
    "iframe",
    "embed",
    "object",
    "canvas",
    "audio",
    "video",
    "source",
    "track",
}

# Attributes valuable for CSS selector generation and content extraction
ALLOWED_ATTRS: Set[str] = {
    "id",
    "class",
    "name",
    "role",
    "href",
    "src",
    "alt",
    "title",
    "aria-label",
    "data-testid",
    "data-id",
    "data-product-id",
    "data-item-id",
    "itemprop",
    "itemtype",
    "itemscope",
}

MAX_ATTR_VALUE_LENGTH = 150
DEFAULT_MAX_CHARS = 35000


def prune_html_for_llm(
    html: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    focus_selector: Optional[str] = None,
) -> str:
    """
    Clean and prune HTML content to produce a compact, token-efficient representation
    suitable for LLM CSS selector reasoning and extraction planning.

    Args:
        html: Raw HTML string of the target page.
        max_chars: Maximum character limit for the output pruned HTML string.
        focus_selector: Optional CSS selector to focus on (e.g. 'main', '#content').

    Returns:
        Pruned, formatted HTML string with prompt injection containment delimiters.
    """
    if not html or not html.strip():
        return "<untrusted_dom_context>\n<!-- Empty page -->\n</untrusted_dom_context>"

    # 0. Prompt Injection Defense: Escape any embedded delimiter tags in raw input
    safe_input = (
        html.replace("</untrusted_dom_context>", "&lt;/untrusted_dom_context&gt;")
        .replace("<untrusted_dom_context>", "&lt;untrusted_dom_context&gt;")
    )

    soup = BeautifulSoup(safe_input, "html.parser")

    # 1. Remove comments
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # 2. Decompose noisy, non-content tags
    for tag in soup.find_all(list(STRIP_TAGS)):
        tag.decompose()

    # 3. If a focus selector is given, try to restrict to that container
    target_root = soup
    if focus_selector:
        focused = soup.select_one(focus_selector)
        if focused:
            target_root = focused
    elif soup.body:
        target_root = soup.body

    # 4. Clean attributes on remaining tags
    for tag in target_root.find_all(True):
        attrs = dict(tag.attrs)
        new_attrs = {}
        for k, v in attrs.items():
            k_lower = k.lower()
            if k_lower in ALLOWED_ATTRS:
                if isinstance(v, list):
                    # class is typically a list of class names
                    v_str = " ".join(v).strip()
                else:
                    v_str = str(v).strip()

                # Filter out base64 / data URIs in href/src
                if k_lower in {"href", "src"} and v_str.startswith("data:"):
                    continue

                # Truncate overly long attribute values
                if len(v_str) > MAX_ATTR_VALUE_LENGTH:
                    v_str = v_str[:MAX_ATTR_VALUE_LENGTH] + "..."

                new_attrs[k] = v_str
        tag.attrs = new_attrs

    # 5. Format and bound string length
    cleaned_html = target_root.decode_contents() if target_root != soup else str(soup)

    # Normalize excessive newlines and spaces
    lines = [line.strip() for line in cleaned_html.splitlines() if line.strip()]
    compact_html = "\n".join(lines)

    if len(compact_html) > max_chars:
        compact_html = (
            compact_html[:max_chars]
            + "\n<!-- [TRUNCATED DUE TO SIZE LIMIT: Structural repetition continues...] -->"
        )

    # 6. Prompt Injection Defense: Escape any attempted closing delimiters
    safe_content = compact_html.replace("</untrusted_dom_context>", "<\\/untrusted_dom_context>")

    return f"<untrusted_dom_context>\n{safe_content}\n</untrusted_dom_context>"
