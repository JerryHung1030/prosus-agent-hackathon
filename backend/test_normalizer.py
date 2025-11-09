#!/usr/bin/env python3
"""
Quick test script for criteria normalization
Run from project root: python backend/test_normalizer.py
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))

from api import _normalize_criteria_input

def test_normalizer():
    print("Testing _normalize_criteria_input...\n")
    
    # Test 1: expected_criteria wrapper
    print("Test 1: expected_criteria wrapper")
    input1 = {"expected_criteria": {"budget": "€1200", "location": "Leiden"}}
    result1 = _normalize_criteria_input(input1)
    print(f"Input:  {input1}")
    print(f"Output: {result1}")
    assert "max_price" in result1 or "budget" in result1
    assert "city" in result1 or "location" in result1
    print("✅ PASS\n")
    
    # Test 2: extracted_criteria with synonyms
    print("Test 2: extracted_criteria with synonyms")
    input2 = {"extracted_criteria": {"price_max": 2000, "area": "Amsterdam", "min_area": 50}}
    result2 = _normalize_criteria_input(input2)
    print(f"Input:  {input2}")
    print(f"Output: {result2}")
    assert result2.get("max_price") == 2000
    assert result2.get("city") == "Amsterdam"
    assert result2.get("min_size") == 50
    print("✅ PASS\n")
    
    # Test 3: Direct criteria
    print("Test 3: Direct criteria (no wrapper)")
    input3 = {"city": "Rotterdam", "max_price": "3000", "commute": "Delft Station"}
    result3 = _normalize_criteria_input(input3)
    print(f"Input:  {input3}")
    print(f"Output: {result3}")
    assert result3["city"] == "Rotterdam"
    assert result3["max_price"] == 3000  # should be int
    assert result3["commute_target"] == "Delft Station"
    print("✅ PASS\n")
    
    # Test 4: Empty input
    print("Test 4: Empty input")
    input4 = {}
    result4 = _normalize_criteria_input(input4)
    print(f"Input:  {input4}")
    print(f"Output: {result4}")
    assert result4 == {}
    print("✅ PASS\n")
    
    # Test 5: None input
    print("Test 5: None input")
    input5 = None
    result5 = _normalize_criteria_input(input5)
    print(f"Input:  {input5}")
    print(f"Output: {result5}")
    assert result5 == {}
    print("✅ PASS\n")
    
    # Test 6: Mixed canonical and synonyms
    print("Test 6: Mixed canonical and synonym keys")
    input6 = {"city": "Utrecht", "budget": "1800", "size_min": 45, "extra_field": "keep me"}
    result6 = _normalize_criteria_input(input6)
    print(f"Input:  {input6}")
    print(f"Output: {result6}")
    assert result6["city"] == "Utrecht"
    assert result6["max_price"] == 1800
    assert result6["min_size"] == 45
    assert result6.get("extra_field") == "keep me"  # pass-through
    print("✅ PASS\n")
    
    print("=" * 60)
    print("All tests passed! ✅")
    print("=" * 60)

if __name__ == "__main__":
    test_normalizer()
