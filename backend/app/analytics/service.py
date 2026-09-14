"""Service routines for formatting and generating analytics exports."""
from __future__ import annotations

import csv
import io
from typing import Generator, Sequence

from backend.app.classifiers.categories import CATEGORY_META, Category


def enrich_category_metrics(raw_metrics: list[dict]) -> list[dict]:
    """Add human-readable labels, theme colors, and icons to category summaries."""
    enriched = []
    for item in raw_metrics:
        cat_name = item["category"]
        try:
            cat_enum = Category(cat_name)
        except ValueError:
            cat_enum = Category.UNCATEGORIZED

        meta = CATEGORY_META.get(cat_enum, CATEGORY_META[Category.UNCATEGORIZED])
        enriched.append({
            "category": cat_name,
            "label": meta["label"],
            "color": meta["color"],
            "icon": meta["icon"],
            "query_count": item["query_count"],
            "distinct_domains": item["distinct_domains"],
            "percentage": item["percentage"],
        })
    return enriched


def generate_csv_stream(records: Sequence[dict]) -> Generator[str, None, None]:
    """Generate CSV rows iteratively for streaming HTTP download."""
    if not records:
        yield "id,occurred_at,source_ip,device_id,device_name,domain,category,query_type,response_status,dns_visibility\n"
        return

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id",
            "occurred_at",
            "source_ip",
            "device_id",
            "device_name",
            "domain",
            "category",
            "query_type",
            "response_status",
            "dns_visibility",
        ],
    )
    writer.writeheader()
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    for row in records:
        writer.writerow(row)
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
