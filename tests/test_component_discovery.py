from services import component_discovery


def test_parse_component_candidates_accepts_fenced_json():
    result = component_discovery.parse_component_candidates(
        """```json
        {"components":[{"name":"MAX30102","category":"Sensor","description":"Optical pulse sensor","aliases":["pulse oximeter"],"library_ids":[],"search_query":"MAX30102 datasheet module"}]}
        ```"""
    )

    assert result == [{
        "name": "MAX30102",
        "category": "Sensor",
        "description": "Optical pulse sensor",
        "aliases": ["pulse oximeter"],
        "library_ids": [],
        "search_query": "MAX30102 datasheet module",
    }]


def test_web_enrichment_attaches_image_datasheet_source_and_vendor(monkeypatch):
    monkeypatch.setattr(component_discovery, "search_web", lambda query, num_results: [
        {"title": "MAX30102 datasheet", "url": "https://example.com/max30102.pdf", "snippet": "datasheet"},
        {"title": "Buy MAX30102", "url": "https://www.digikey.in/product/max30102", "snippet": ""},
    ])
    monkeypatch.setattr(component_discovery, "search_images", lambda query, num_results: [
        {"title": "MAX30102 module", "url": "https://example.com/product", "image": "https://example.com/max30102.jpg"},
    ])

    result = component_discovery.enrich_candidates_from_web([{
        "name": "MAX30102",
        "category": "Sensor",
        "description": "Optical pulse sensor",
        "aliases": [],
        "library_ids": [],
        "search_query": "MAX30102 module datasheet",
    }])[0]

    assert result["thumbnail"] == "https://example.com/max30102.jpg"
    assert result["datasheet_url"] == "https://example.com/max30102.pdf"
    assert result["source_url"] == "https://example.com/max30102.pdf"
    assert result["buy_links"] == [{
        "vendor": "DigiKey",
        "url": "https://www.digikey.in/product/max30102",
    }]
