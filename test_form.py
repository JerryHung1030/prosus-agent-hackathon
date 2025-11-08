# FILE: ./test_form.py

import datetime

# Make sure you are importing the *new tool name* if you changed it
# My code above keeps the name 'pararius_form_tool' for the instance
from src.tools.pararius_form_tool import pararius_form_tool


def run_test():
    print("Starting standalone tool test...")
    # Use the instance exported from your tool file
    tool = pararius_form_tool

    # --- 1. Mock Data ---

    # --- !! YOUR HARD-CODED LOGIN !! ---
    # Put your real Pararius login credentials here
    test_username = "chiehlee.hung@gmail.com"
    test_password = "Systemadmin!@3"
    # ------------------------------------

    # This is the target URL we want to go to *after* logging in
    test_url = "https://www.pararius.com/contact/7f4d9e8c-04e6-5146-9a5b-ea41303203db"

    test_msg = (
        f"Dear Landlord,\n\n[HACKATHON TEST - PLEASE DISREGARD]\n"
        f"This message is an automated test for our project.\n"
        f"Test ID: {datetime.datetime.now().isoformat()}"
    )

    # Static Profile Data (Mocked)
    mock_profile = {
        "salutation": "0",  # "Sir"
        "employment_status": "3",  # "Student"
        "gross_income": "[1000,1500]",
        "guarantor": "3",  # "Guarantor living abroad"
        "living_situation": "1",  # "No" (moving in alone)
        "has_pets": False,
        "start_date": "2025-12-01",
        "rental_duration": "5",  # "1 - 2 years"
        "current_situation": "i_dont_rent_or_own_a_roof_yet",
    }

    # Check if credentials are set
    if "YOUR_EMAIL" in test_username or "YOUR_PASSWORD" in test_password:
        print("=" * 50)
        print("ERROR: Please update test_username and test_password in test_form.py")
        print("=" * 50)
        return

    # --- 2. Run the Tool ---
    result = tool._run(
        # Pass login credentials
        username=test_username,
        password=test_password,
        # Pass form data
        listing_url=test_url,
        message_body=test_msg,
        salutation=mock_profile["salutation"],
        employment_status=mock_profile["employment_status"],
        gross_income=mock_profile["gross_income"],
        guarantor=mock_profile["guarantor"],
        living_situation=mock_profile["living_situation"],
        has_pets=mock_profile["has_pets"],
        start_date=mock_profile["start_date"],
        rental_duration=mock_profile["rental_duration"],
        current_situation=mock_profile["current_situation"],
    )

    print("\n--- Test Finished ---")
    print(f"Result: {result}")


if __name__ == "__main__":
    run_test()
