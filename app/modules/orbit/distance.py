"""
Distance calculation utility for Orbit

Uses Haversine formula to calculate distance between coordinates.
"""

import math


def calculate_distance(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float
) -> float:
    """
    Calculate distance between two points using Haversine formula
    
    Args:
        lat1, lon1: First point coordinates
        lat2, lon2: Second point coordinates
        
    Returns:
        Distance in kilometers, rounded to 2 decimal places
    """
    # Earth's radius in kilometers
    R = 6371.0
    
    # Convert to radians
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)
    
    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    distance = R * c
    return round(distance, 2)


def format_distance(distance_km: float) -> str:
    """
    Format distance for display
    
    Args:
        distance_km: Distance in kilometers
        
    Returns:
        Formatted string (e.g., "400 m away", "2 km away")
    """
    if distance_km < 1.0:
        # Convert to meters
        meters = int(distance_km * 1000)
        return f"{meters} m away"
    else:
        return f"{distance_km} km away"
