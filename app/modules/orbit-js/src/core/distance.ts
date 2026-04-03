/**
 * Distance calculation utility for Orbit
 * 
 * Uses Haversine formula to calculate distance between coordinates.
 * Ported from Python distance.py
 */

/**
 * Calculate distance between two points using Haversine formula
 * 
 * @param lat1 - First point latitude
 * @param lon1 - First point longitude
 * @param lat2 - Second point latitude
 * @param lon2 - Second point longitude
 * @returns Distance in kilometers, rounded to 2 decimal places
 */
export function calculateDistance(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number
): number {
  // Earth's radius in kilometers
  const R = 6371.0;
  
  // Convert to radians
  const lat1Rad = toRadians(lat1);
  const lon1Rad = toRadians(lon1);
  const lat2Rad = toRadians(lat2);
  const lon2Rad = toRadians(lon2);
  
  // Haversine formula
  const dlat = lat2Rad - lat1Rad;
  const dlon = lon2Rad - lon1Rad;
  
  const a = Math.sin(dlat / 2) ** 2 + 
            Math.cos(lat1Rad) * Math.cos(lat2Rad) * Math.sin(dlon / 2) ** 2;
  const c = 2 * Math.asin(Math.sqrt(a));
  
  const distance = R * c;
  return round(distance, 2);
}

/**
 * Format distance for display
 * 
 * @param distanceKm - Distance in kilometers
 * @returns Formatted string (e.g., "400 m away", "2 km away")
 */
export function formatDistance(distanceKm: number): string {
  if (distanceKm < 1.0) {
    // Convert to meters
    const meters = Math.floor(distanceKm * 1000);
    return `${meters} m away`;
  } else {
    return `${distanceKm} km away`;
  }
}

/**
 * Convert degrees to radians
 */
function toRadians(degrees: number): number {
  return degrees * (Math.PI / 180);
}

/**
 * Round a number to specified decimal places
 */
function round(value: number, decimals: number): number {
  const factor = Math.pow(10, decimals);
  return Math.round(value * factor) / factor;
}

/**
 * Sort offers by distance from user location
 * 
 * @param offers - List of offers with distance_km property
 * @returns Sorted offers (closest first, null distances last)
 */
export function sortOffersByDistance<T extends { distance_km?: number | null }>(
  offers: T[]
): T[] {
  return [...offers].sort((a, b) => {
    // Put null/undefined distances at the end
    if (a.distance_km == null && b.distance_km == null) return 0;
    if (a.distance_km == null) return 1;
    if (b.distance_km == null) return -1;
    
    // Sort by distance (closest first)
    return a.distance_km - b.distance_km;
  });
}
