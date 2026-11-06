"""
Heuristic fallback generator for extraction planning when LLM is unavailable.
Inspects HTML structure to detect common semantic patterns (e.g., product cards, tables).
"""

from typing import List, Optional
from bs4 import BeautifulSoup

from web_data_forge.models.contracts import DataType, ExtractionPlan, FieldContract


def generate_heuristic_plan(
    html: str,
    target_url: str,
    user_instruction: Optional[str] = None,
) -> ExtractionPlan:
    """
    Generate a basic heuristic ExtractionPlan by inspecting the HTML DOM
    for standard semantic structures (e.g. product cards, tables, lists).
    Useful when offline, missing API keys, or as a quick baseline plan.
    """
    soup = BeautifulSoup(html, "html.parser")

    # 1. Check for product cards or article cards
    card_candidates = [
        "article.product-card",
        "article.product_pod",
        "div.product-card",
        "div.product-item",
        "article",
        "div.card",
    ]

    for cand in card_candidates:
        items = soup.select(cand)
        if len(items) >= 2:
            # Found repeated card container!
            first_item = items[0]
            fields: List[FieldContract] = []

            # Look for title / heading
            for h in ["h1", "h2", "h3", ".title", ".product-title", "a"]:
                if first_item.select_one(h):
                    fields.append(
                        FieldContract(
                            name="title",
                            selector=h,
                            extract="text",
                            data_type=DataType.STRING,
                            required=True,
                        )
                    )
                    break

            # Look for price
            for p in [".price", ".product-price", ".price_color", "span.price"]:
                if first_item.select_one(p):
                    fields.append(
                        FieldContract(
                            name="price",
                            selector=p,
                            extract="text",
                            data_type=DataType.STRING,
                            required=False,
                        )
                    )
                    break

            # Look for link
            link_el = first_item.select_one("a[href]")
            if link_el:
                fields.append(
                    FieldContract(
                        name="link",
                        selector="a[href]",
                        extract="attr",
                        attr_name="href",
                        data_type=DataType.URL,
                        required=False,
                    )
                )

            if fields:
                return ExtractionPlan(
                    target_url=target_url,
                    container_selector=cand,
                    fields=fields,
                )

    # 2. Check for HTML tables
    table_rows = soup.select("table tbody tr")
    if len(table_rows) >= 2:
        first_row = table_rows[0]
        tds = first_row.find_all("td")
        if tds:
            fields = [
                FieldContract(
                    name=f"column_{i+1}",
                    selector=f"td:nth-child({i+1})",
                    extract="text",
                    data_type=DataType.STRING,
                    required=False,
                )
                for i in range(min(len(tds), 6))
            ]
            return ExtractionPlan(
                target_url=target_url,
                container_selector="table tbody tr",
                fields=fields,
            )

    # 3. Default single item fallback (e.g. article / detail page)
    default_fields = [
        FieldContract(
            name="title",
            selector="h1",
            extract="text",
            data_type=DataType.STRING,
            required=True,
        )
    ]
    if soup.select_one("p"):
        default_fields.append(
            FieldContract(
                name="description",
                selector="p",
                extract="text",
                data_type=DataType.STRING,
                required=False,
            )
        )

    return ExtractionPlan(
        target_url=target_url,
        container_selector=None,
        fields=default_fields,
    )

