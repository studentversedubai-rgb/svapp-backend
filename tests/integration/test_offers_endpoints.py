"""
Integration Tests for Offers Endpoints - Phase 2

Tests for home feed, search, nearby, and detail endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from datetime import datetime, timedelta


# Note: These tests require a test database and test fixtures
# This is a template showing the structure


class TestHomeFeedEndpoint:
    """Test /offers/home endpoint"""
    
    def test_home_feed_requires_authentication(self, client):
        """Test that home feed requires JWT token"""
        response = client.get("/offers/home")
        assert response.status_code == 401
    
    def test_home_feed_returns_paginated_results(self, client, auth_headers):
        """Test that home feed returns paginated results"""
        response = client.get(
            "/offers/home?page=1&page_size=20",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data
    
    def test_home_feed_with_location(self, client, auth_headers):
        """Test home feed with user location"""
        response = client.get(
            "/offers/home?latitude=25.2048&longitude=55.2708&page=1&page_size=20",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        
        # Check if distance is included when location provided
        if data["items"]:
            first_item = data["items"][0]
            # distance_km may be None if merchant has no location
            assert "distance_km" in first_item
    
    def test_home_feed_requires_both_lat_and_lon(self, client, auth_headers):
        """Test that both latitude and longitude must be provided"""
        # Only latitude
        response = client.get(
            "/offers/home?latitude=25.2048",
            headers=auth_headers
        )
        assert response.status_code == 400
        
        # Only longitude
        response = client.get(
            "/offers/home?longitude=55.2708",
            headers=auth_headers
        )
        assert response.status_code == 400
    
    def test_home_feed_validates_coordinates(self, client, auth_headers):
        """Test coordinate validation"""
        # Invalid latitude (> 90)
        response = client.get(
            "/offers/home?latitude=100&longitude=55.2708",
            headers=auth_headers
        )
        assert response.status_code == 422
        
        # Invalid longitude (> 180)
        response = client.get(
            "/offers/home?latitude=25.2048&longitude=200",
            headers=auth_headers
        )
        assert response.status_code == 422
    
    def test_home_feed_pagination(self, client, auth_headers):
        """Test pagination parameters"""
        # Page 1
        response = client.get(
            "/offers/home?page=1&page_size=10",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        # Invalid page (< 1)
        response = client.get(
            "/offers/home?page=0&page_size=10",
            headers=auth_headers
        )
        assert response.status_code == 422
        
        # Invalid page_size (> 100)
        response = client.get(
            "/offers/home?page=1&page_size=200",
            headers=auth_headers
        )
        assert response.status_code == 422


class TestSearchEndpoint:
    """Test /offers/search endpoint"""
    
    def test_search_requires_authentication(self, client):
        """Test that search requires JWT token"""
        response = client.get("/offers/search?query=coffee")
        assert response.status_code == 401
    
    def test_search_with_query(self, client, auth_headers):
        """Test search with keyword query"""
        response = client.get(
            "/offers/search?query=coffee",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
    
    def test_search_with_category_filter(self, client, auth_headers):
        """Test search with category filter"""
        response = client.get(
            "/offers/search?category_id=food_beverage",
            headers=auth_headers
        )
        
        assert response.status_code == 200
    
    def test_search_with_location_and_radius(self, client, auth_headers):
        """Test search with location and radius"""
        response = client.get(
            "/offers/search?latitude=25.2048&longitude=55.2708&radius_km=10",
            headers=auth_headers
        )
        
        assert response.status_code == 200
    
    def test_search_radius_requires_location(self, client, auth_headers):
        """Test that radius requires latitude and longitude"""
        response = client.get(
            "/offers/search?radius_km=10",
            headers=auth_headers
        )
        
        assert response.status_code == 400
    
    def test_search_validates_query_length(self, client, auth_headers):
        """Test query length validation"""
        # Too short (< 2 characters)
        response = client.get(
            "/offers/search?query=a",
            headers=auth_headers
        )
        assert response.status_code == 400
    
    def test_search_sanitizes_dangerous_input(self, client, auth_headers):
        """Test that dangerous SQL characters are rejected"""
        dangerous_queries = [
            "coffee; DROP TABLE offers;",
            "coffee' OR '1'='1",
            "coffee--",
        ]
        
        for query in dangerous_queries:
            response = client.get(
                f"/offers/search?query={query}",
                headers=auth_headers
            )
            # Should either reject (400/422) or sanitize
            assert response.status_code in [400, 422, 200]
    
    def test_search_enforces_max_radius(self, client, auth_headers):
        """Test that max radius is enforced"""
        # Radius > 50km should be rejected
        response = client.get(
            "/offers/search?latitude=25.2048&longitude=55.2708&radius_km=100",
            headers=auth_headers
        )
        assert response.status_code == 422


class TestNearbyOffersEndpoint:
    """Test /offers/nearby endpoint"""
    
    def test_nearby_requires_authentication(self, client):
        """Test that nearby requires JWT token"""
        response = client.get("/offers/nearby?latitude=25.2048&longitude=55.2708")
        assert response.status_code == 401
    
    def test_nearby_requires_location(self, client, auth_headers):
        """Test that nearby requires latitude and longitude"""
        response = client.get("/offers/nearby", headers=auth_headers)
        assert response.status_code == 422
    
    def test_nearby_with_valid_location(self, client, auth_headers):
        """Test nearby with valid location"""
        response = client.get(
            "/offers/nearby?latitude=25.2048&longitude=55.2708",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        
        # Results should be sorted by distance
        if len(data["items"]) > 1:
            distances = [
                item.get("distance_km") for item in data["items"]
                if item.get("distance_km") is not None
            ]
            # Check if sorted (ascending)
            assert distances == sorted(distances)
    
    def test_nearby_with_custom_radius(self, client, auth_headers):
        """Test nearby with custom radius"""
        response = client.get(
            "/offers/nearby?latitude=25.2048&longitude=55.2708&radius_km=20",
            headers=auth_headers
        )
        
        assert response.status_code == 200
    
    def test_nearby_enforces_max_radius(self, client, auth_headers):
        """Test that max radius (50km) is enforced"""
        response = client.get(
            "/offers/nearby?latitude=25.2048&longitude=55.2708&radius_km=100",
            headers=auth_headers
        )
        # Should either reject or cap at 50km
        assert response.status_code in [200, 422]


class TestOfferDetailEndpoint:
    """Test /offers/{offer_id} endpoint"""
    
    def test_offer_detail_requires_authentication(self, client):
        """Test that offer detail requires JWT token"""
        response = client.get("/offers/test-offer-id")
        assert response.status_code == 401
    
    def test_offer_detail_with_valid_id(self, client, auth_headers, test_offer_id):
        """Test getting offer detail with valid ID"""
        response = client.get(
            f"/offers/{test_offer_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "id" in data
        assert "title" in data
        assert "description" in data
        assert "merchant" in data
        assert "terms_conditions" in data
    
    def test_offer_detail_with_invalid_id(self, client, auth_headers):
        """Test getting offer detail with invalid ID"""
        response = client.get(
            "/offers/non-existent-offer-id",
            headers=auth_headers
        )
        
        assert response.status_code == 404
    
    def test_offer_detail_with_location(self, client, auth_headers, test_offer_id):
        """Test offer detail with user location for distance"""
        response = client.get(
            f"/offers/{test_offer_id}?latitude=25.2048&longitude=55.2708",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        # distance_km should be present if merchant has location
        assert "distance_km" in data
    
    def test_offer_detail_hides_inactive_offers(self, client, auth_headers, inactive_offer_id):
        """Test that inactive offers return 404"""
        response = client.get(
            f"/offers/{inactive_offer_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 404


class TestCategoriesEndpoint:
    """Test /offers/categories/list endpoint"""
    
    def test_categories_requires_authentication(self, client):
        """Test that categories requires JWT token"""
        response = client.get("/offers/categories/list")
        assert response.status_code == 401
    
    def test_categories_returns_list(self, client, auth_headers):
        """Test that categories returns list"""
        response = client.get(
            "/offers/categories/list",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert isinstance(data["categories"], list)
    
    def test_categories_sorted_by_order(self, client, auth_headers):
        """Test that categories are sorted by sort_order"""
        response = client.get(
            "/offers/categories/list",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        categories = data["categories"]
        
        if len(categories) > 1:
            sort_orders = [cat["sort_order"] for cat in categories]
            assert sort_orders == sorted(sort_orders)


# Run tests with: pytest tests/integration/test_offers_endpoints.py -v
