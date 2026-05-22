"""Federated multi-search backends — reusable direct functions.

Each backend exports a single function taking (query, limit) -> list[dict].
Backends that fail (no API key, network error, rate limit) return [] silently
so the orchestrator can continue with other sources.

## By region/specialization:
- DuckDuckGo: global privacy search
- Wikipedia: encyclopedic knowledge
- Brave: US independent web index
- Mojeek: UK independent web index
- Semantic Scholar: CS/engineering papers
- CrossRef: DOI scholarly metadata
- PubMed (NIH): biomedical literature
- OpenAlex: 250M+ scholarly works, all disciplines
- Internet Archive: historical web (Wayback Machine)
"""
