from __future__ import annotations

from enum import Enum


class Category(str, Enum):
    """Standard domain classification categories."""
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    STREAMING_VIDEO = "STREAMING_VIDEO"
    GAMING = "GAMING"
    EDUCATION = "EDUCATION"
    PRODUCTIVITY = "PRODUCTIVITY"
    ADULT_CONTENT = "ADULT_CONTENT"
    ADS_TRACKING = "ADS_TRACKING"
    TECH_INFRASTRUCTURE = "TECH_INFRASTRUCTURE"
    NEWS_MEDIA = "NEWS_MEDIA"
    SHOPPING = "SHOPPING"
    UNCATEGORIZED = "UNCATEGORIZED"


# Metadata for each category
CATEGORY_META: dict[Category, dict[str, str]] = {
    Category.SOCIAL_MEDIA: {
        "label": "Social Media & Messaging",
        "description": "Social networks, messaging, and photo sharing platforms.",
        "color": "#e91e8c",
        "icon": "chat",
    },
    Category.STREAMING_VIDEO: {
        "label": "Streaming & Video",
        "description": "Video streaming, music, and on-demand content services.",
        "color": "#e53935",
        "icon": "play_circle",
    },
    Category.GAMING: {
        "label": "Gaming & Virtual Worlds",
        "description": "Online gaming platforms, game stores, and gaming services.",
        "color": "#7b1fa2",
        "icon": "sports_esports",
    },
    Category.EDUCATION: {
        "label": "Education & Reference",
        "description": "Educational services, encyclopaedias, learning platforms, and academic tools.",
        "color": "#1976d2",
        "icon": "school",
    },
    Category.PRODUCTIVITY: {
        "label": "Productivity & Communication",
        "description": "Email, office suites, calendars, and collaboration tools.",
        "color": "#0097a7",
        "icon": "work",
    },
    Category.ADULT_CONTENT: {
        "label": "Adult Content",
        "description": "Adult content, gambling, and age-restricted services. Triggers Phase 6 safety alerts.",
        "color": "#b71c1c",
        "icon": "warning",
    },
    Category.ADS_TRACKING: {
        "label": "Advertising & Telemetry",
        "description": "Ad networks, trackers, analytics, and crash reporting services.",
        "color": "#f57c00",
        "icon": "analytics",
    },
    Category.TECH_INFRASTRUCTURE: {
        "label": "Tech & Cloud Infrastructure",
        "description": "CDN, cloud services, connectivity checks, and platform infrastructure.",
        "color": "#455a64",
        "icon": "cloud",
    },
    Category.NEWS_MEDIA: {
        "label": "News & Current Events",
        "description": "News outlets, journalism, and current affairs publishers.",
        "color": "#5d4037",
        "icon": "newspaper",
    },
    Category.SHOPPING: {
        "label": "Shopping & E-Commerce",
        "description": "Online retailers, marketplaces, and commercial booking services.",
        "color": "#388e3c",
        "icon": "shopping_cart",
    },
    Category.UNCATEGORIZED: {
        "label": "Uncategorized",
        "description": "Domains not yet matched by any classification rule.",
        "color": "#9e9e9e",
        "icon": "help_outline",
    },
}
