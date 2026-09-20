"""Phase 19 — explicit web proxy capture (mitmproxy addon).

Sees full request/response metadata for devices configured to use this PC
as their HTTP(S) proxy (with the parental CA installed). Hard privacy
boundary: Cookie/Authorization headers and message bodies are never
stored — only metadata, page titles, and search keywords.
"""
