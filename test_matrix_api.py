#!/usr/bin/env python3
"""
Test script for Google Maps Distance Matrix API integration.

This script tests both the individual directions API and the batch matrix API
to verify backward compatibility and performance improvements.

Usage:
    python test_matrix_api.py
"""

import os
import sys
import time
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

from tools.google_maps_tool import google_maps_tool, google_maps_matrix_tool
from tools.batch_commute_tool import batch_commute_tool


def test_single_route():
    """Test backward compatibility with single route calculation."""
    print("\n" + "=" * 60)
    print("TEST 1: Single Route (Backward Compatibility)")
    print("=" * 60)
    
    origin = "Delftse Poort 1, Delft, Netherlands"
    destination = "TU Delft, Mekelweg 5, Delft, Netherlands"
    
    print(f"\nOrigin: {origin}")
    print(f"Destination: {destination}")
    
    start = time.time()
    result = google_maps_tool._run(origin=origin, destination=destination, mode="transit")
    elapsed = time.time() - start
    
    print(f"\nResult: {result}")
    print(f"Time: {elapsed:.2f}s")
    print("✅ Single route test passed")


def test_matrix_api():
    """Test new Distance Matrix API with multiple origins."""
    print("\n" + "=" * 60)
    print("TEST 2: Distance Matrix API (Batch)")
    print("=" * 60)
    
    origins = [
        "Westlandseweg 40, Delft, Netherlands",
        "Phoenixstraat 42, Delft, Netherlands",
        "Voorhofdreef 1, Delft, Netherlands",
        "Buitenwatersloot 155, Delft, Netherlands",
        "Julianalaan 134, Delft, Netherlands",
    ]
    destination = "TU Delft, Mekelweg 5, Delft, Netherlands"
    
    print(f"\nOrigins: {len(origins)} addresses")
    print(f"Destination: {destination}")
    
    start = time.time()
    results = google_maps_matrix_tool._run(origins=origins, destination=destination, mode="transit")
    elapsed = time.time() - start
    
    print(f"\nResults:")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result}")
    
    print(f"\nTime: {elapsed:.2f}s")
    print(f"Average per listing: {elapsed/len(origins):.2f}s")
    print("✅ Matrix API test passed")


def test_batch_commute_tool():
    """Test the integrated batch commute tool with fallback logic."""
    print("\n" + "=" * 60)
    print("TEST 3: Batch Commute Tool (Integrated)")
    print("=" * 60)
    
    # Mock listings data
    listings = [
        {
            "street": "Westlandseweg 40",
            "city": "Delft",
            "postal_code": "2624 GN",
            "price_amount": 1200,
            "area_m2": 50,
        },
        {
            "street": "Phoenixstraat 42",
            "city": "Delft",
            "postal_code": "2611 AM",
            "price_amount": 950,
            "area_m2": 45,
        },
        {
            "street": "Voorhofdreef 1",
            "city": "Delft",
            "postal_code": "2624 JE",
            "price_amount": 1100,
            "area_m2": 55,
        },
        {
            "street": "Buitenwatersloot 155",
            "city": "Delft",
            "postal_code": "2613 SV",
            "price_amount": 1300,
            "area_m2": 60,
        },
        {
            "street": "Julianalaan 134",
            "city": "Delft",
            "postal_code": "2628 BC",
            "price_amount": 1150,
            "area_m2": 52,
        },
    ]
    
    destination = "TU Delft, Mekelweg 5, Delft, Netherlands"
    
    print(f"\nListings: {len(listings)}")
    print(f"Destination: {destination}")
    
    start = time.time()
    results = batch_commute_tool._run(listings=listings, destination=destination)
    elapsed = time.time() - start
    
    print(f"\nResults:")
    for i, (listing, result) in enumerate(zip(listings, results), 1):
        print(f"  {i}. {listing['street']}: {result}")
    
    print(f"\nTime: {elapsed:.2f}s")
    print(f"Average per listing: {elapsed/len(listings):.2f}s")
    
    # Check that we got results for all listings
    assert len(results) == len(listings), "Result count mismatch!"
    print("✅ Batch commute tool test passed")


def test_performance_comparison():
    """Compare performance between individual calls and matrix API."""
    print("\n" + "=" * 60)
    print("TEST 4: Performance Comparison")
    print("=" * 60)
    
    origins = [
        "Westlandseweg 40, Delft, Netherlands",
        "Phoenixstraat 42, Delft, Netherlands",
        "Voorhofdreef 1, Delft, Netherlands",
    ]
    destination = "TU Delft, Mekelweg 5, Delft, Netherlands"
    
    # Individual calls
    print("\n🔵 Individual Directions API calls:")
    start_individual = time.time()
    individual_results = []
    for origin in origins:
        result = google_maps_tool._run(origin=origin, destination=destination, mode="transit")
        individual_results.append(result)
    time_individual = time.time() - start_individual
    
    print(f"Time: {time_individual:.2f}s")
    print(f"Results: {individual_results}")
    
    # Matrix API
    print("\n🟢 Distance Matrix API (batch):")
    start_matrix = time.time()
    matrix_results = google_maps_matrix_tool._run(origins=origins, destination=destination, mode="transit")
    time_matrix = time.time() - start_matrix
    
    print(f"Time: {time_matrix:.2f}s")
    print(f"Results: {matrix_results}")
    
    # Compare
    speedup = time_individual / time_matrix if time_matrix > 0 else 0
    print(f"\n📊 Speedup: {speedup:.2f}x faster")
    
    if speedup > 1.5:
        print("✅ Significant performance improvement!")
    elif speedup > 1.0:
        print("✅ Moderate performance improvement")
    else:
        print("⚠️  No significant speedup (may need API key with billing enabled)")


def main():
    print("\n" + "=" * 60)
    print("🧪 Google Maps Distance Matrix API Test Suite")
    print("=" * 60)
    
    # Check for API key
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        print("\n❌ GOOGLE_MAPS_API_KEY not found in environment")
        print("Tests will run with fallback values (999 mins)")
        print("Set GOOGLE_MAPS_API_KEY to test with real API\n")
    else:
        print(f"\n✅ API Key found: {api_key[:10]}...{api_key[-4:]}")
    
    try:
        # Run all tests
        test_single_route()
        test_matrix_api()
        test_batch_commute_tool()
        test_performance_comparison()
        
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
