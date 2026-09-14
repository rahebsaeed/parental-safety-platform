"""Phase 2: DNS observation collector package.

Modules:
    log_parser  — parses raw dnsmasq query log lines into structured records
    ingester    — tails the log file and writes records to SQLite
    cli         — command-line interface (parental-monitor-dns)
"""
