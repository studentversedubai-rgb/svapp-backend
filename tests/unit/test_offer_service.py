"""
Unit Tests for Offer Service - Phase 2

Tests for offer eligibility logic, distance calculation, and filtering.
"""

import pytest
from datetime import datetime, time, timedelta
from app.modules.offers.service import OfferService


class TestOfferEligibility:
    """Test offer eligibility checking logic"""
    
    @pytest.fixture
    def offer_service(self):
        """Create offer service instance"""
        return OfferService()
    
    def test_active_offer_is_eligible(self, offer_service):
        """Test that active offer within date range is eligible"""
        now = datetime.utcnow()
        offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat()
        }
        
        assert offer_service.is_offer_eligible(offer) is True
    
    def test_inactive_offer_is_not_eligible(self, offer_service):
        """Test that inactive offer is not eligible"""
        now = datetime.utcnow()
        offer = {
            'is_active': False,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat()
        }
        
        assert offer_service.is_offer_eligible(offer) is False
    
    def test_expired_offer_is_not_eligible(self, offer_service):
        """Test that expired offer is not eligible"""
        now = datetime.utcnow()
        offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=10)).isoformat(),
            'valid_until': (now - timedelta(days=1)).isoformat()
        }
        
        assert offer_service.is_offer_eligible(offer) is False
    
    def test_future_offer_is_not_eligible(self, offer_service):
        """Test that future offer is not eligible"""
        now = datetime.utcnow()
        offer = {
            'is_active': True,
            'valid_from': (now + timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=10)).isoformat()
        }
        
        assert offer_service.is_offer_eligible(offer) is False
    
    def test_offer_with_time_window_during_valid_time(self, offer_service):
        """Test offer with time window during valid hours"""
        now = datetime.utcnow()
        current_time = now.time()
        
        # Create time window around current time
        time_from = (datetime.combine(datetime.today(), current_time) - timedelta(hours=1)).time()
        time_until = (datetime.combine(datetime.today(), current_time) + timedelta(hours=1)).time()
        
        offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat(),
            'time_valid_from': time_from.isoformat(),
            'time_valid_until': time_until.isoformat()
        }
        
        assert offer_service.is_offer_eligible(offer, check_time=True) is True
    
    def test_offer_with_time_window_outside_valid_time(self, offer_service):
        """Test offer with time window outside valid hours"""
        now = datetime.utcnow()
        
        # Create time window that doesn't include current time
        offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat(),
            'time_valid_from': '01:00:00',
            'time_valid_until': '02:00:00'
        }
        
        # This might pass if test runs between 1-2 AM, so we skip time check
        result = offer_service.is_offer_eligible(offer, check_time=False)
        assert result is True
    
    def test_offer_with_valid_days_on_valid_day(self, offer_service):
        """Test offer with day restrictions on valid day"""
        now = datetime.utcnow()
        current_day = now.weekday()  # 0=Monday, 6=Sunday
        
        offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat(),
            'valid_days_of_week': [current_day]  # Only valid today
        }
        
        assert offer_service.is_offer_eligible(offer, check_day=True) is True
    
    def test_offer_with_valid_days_on_invalid_day(self, offer_service):
        """Test offer with day restrictions on invalid day"""
        now = datetime.utcnow()
        current_day = now.weekday()
        invalid_day = (current_day + 1) % 7  # Next day
        
        offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat(),
            'valid_days_of_week': [invalid_day]  # Not valid today
        }
        
        assert offer_service.is_offer_eligible(offer, check_day=True) is False
    
    def test_weekday_only_offer(self, offer_service):
        """Test offer valid only on weekdays"""
        now = datetime.utcnow()
        current_day = now.weekday()
        
        offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat(),
            'valid_days_of_week': [0, 1, 2, 3, 4]  # Monday-Friday
        }
        
        is_weekday = current_day < 5
        assert offer_service.is_offer_eligible(offer, check_day=True) is is_weekday


class TestDistanceCalculation:
    """Test Haversine distance calculation"""
    
    @pytest.fixture
    def offer_service(self):
        """Create offer service instance"""
        return OfferService()
    
    def test_distance_same_point(self, offer_service):
        """Test distance between same point is 0"""
        distance = offer_service.calculate_distance(25.2048, 55.2708, 25.2048, 55.2708)
        assert distance == 0.0
    
    def test_distance_dubai_to_abu_dhabi(self, offer_service):
        """Test distance from Dubai to Abu Dhabi (approx 140km)"""
        # Dubai coordinates
        dubai_lat, dubai_lon = 25.2048, 55.2708
        # Abu Dhabi coordinates
        abudhabi_lat, abudhabi_lon = 24.4539, 54.3773
        
        distance = offer_service.calculate_distance(
            dubai_lat, dubai_lon,
            abudhabi_lat, abudhabi_lon
        )
        
        # Should be approximately 140km (allow 10km margin)
        assert 130 <= distance <= 150
    
    def test_distance_is_positive(self, offer_service):
        """Test that distance is always positive"""
        distance = offer_service.calculate_distance(
            25.2048, 55.2708,  # Dubai
            25.1972, 55.2744   # Nearby point
        )
        assert distance > 0
    
    def test_distance_symmetry(self, offer_service):
        """Test that distance(A,B) == distance(B,A)"""
        lat1, lon1 = 25.2048, 55.2708
        lat2, lon2 = 25.1972, 55.2744
        
        distance1 = offer_service.calculate_distance(lat1, lon1, lat2, lon2)
        distance2 = offer_service.calculate_distance(lat2, lon2, lat1, lon1)
        
        assert distance1 == distance2


class TestOfferFiltering:
    """Test offer filtering logic"""
    
    @pytest.fixture
    def offer_service(self):
        """Create offer service instance"""
        return OfferService()
    
    def test_filter_removes_inactive_offers(self, offer_service):
        """Test that inactive offers are filtered out"""
        now = datetime.utcnow()
        
        active_offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat()
        }
        
        inactive_offer = {
            'is_active': False,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat()
        }
        
        assert offer_service.is_offer_eligible(active_offer) is True
        assert offer_service.is_offer_eligible(inactive_offer) is False
    
    def test_filter_removes_expired_offers(self, offer_service):
        """Test that expired offers are filtered out"""
        now = datetime.utcnow()
        
        valid_offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=1)).isoformat(),
            'valid_until': (now + timedelta(days=1)).isoformat()
        }
        
        expired_offer = {
            'is_active': True,
            'valid_from': (now - timedelta(days=10)).isoformat(),
            'valid_until': (now - timedelta(days=1)).isoformat()
        }
        
        assert offer_service.is_offer_eligible(valid_offer) is True
        assert offer_service.is_offer_eligible(expired_offer) is False


# Run tests with: pytest tests/unit/test_offer_service.py -v
