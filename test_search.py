import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_search_laptop_returns_relevant_results():
    """Search queries for 'laptop' return matching titles and descriptions ranked by relevance."""
    response = client.get("/api/v1/search?q=laptop")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0
    # Top result should match 'laptop' in title or description
    top_item = data["results"][0]
    assert "laptop" in top_item["name"].lower() or "laptop" in (top_item.get("description") or "").lower()


def test_price_range_filtering():
    """Price range filtering properly excludes items outside bounds."""
    # Filter for products between 1,000 and 3,000 INR
    response = client.get("/api/v1/search?min_price=1000&max_price=3000")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] > 0

    for item in data["results"]:
        assert item["min_variant_price"] >= 1000.0
        assert item["min_variant_price"] <= 3000.0

    # High-end filter (over 40,000 INR) should only return the laptop
    laptop_res = client.get("/api/v1/search?min_price=40000")
    assert laptop_res.status_code == 200
    laptop_data = laptop_res.json()
    for item in laptop_data["results"]:
        assert item["min_variant_price"] >= 40000.0


def test_rating_filtering():
    """Minimum rating filter properly excludes lower rated products."""
    response = client.get("/api/v1/search?min_rating=4.5")
    assert response.status_code == 200
    data = response.json()
    for item in data["results"]:
        assert item["average_rating"] >= 4.5


def test_empty_search_no_results_message():
    """Non-matching search queries return helpful message and facets."""
    response = client.get("/api/v1/search?q=xyznonexistentterm999")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 0
    assert "No results found" in data["message"]
    assert "facets" in data


def test_auto_suggestions_endpoint():
    """Auto-suggestions endpoint returns debounced suggestions and category matches."""
    response = client.get("/api/v1/search/suggestions?q=lap")
    assert response.status_code == 200
    data = response.json()
    assert data["query"] == "lap"
    assert len(data["suggestions"]) > 0
    assert any("laptop" in s.lower() for s in data["suggestions"])


def test_search_sorting():
    """Sorting by price ascending and descending orders items correctly."""
    # Price ascending
    asc_res = client.get("/api/v1/search?sort=price_asc")
    assert asc_res.status_code == 200
    asc_items = asc_res.json()["results"]
    if len(asc_items) >= 2:
        for i in range(len(asc_items) - 1):
            assert asc_items[i]["min_variant_price"] <= asc_items[i + 1]["min_variant_price"]

    # Price descending
    desc_res = client.get("/api/v1/search?sort=price_desc")
    assert desc_res.status_code == 200
    desc_items = desc_res.json()["results"]
    if len(desc_items) >= 2:
        for i in range(len(desc_items) - 1):
            assert desc_items[i]["min_variant_price"] >= desc_items[i + 1]["min_variant_price"]
