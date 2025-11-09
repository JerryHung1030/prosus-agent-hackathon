#!/usr/bin/env python3
"""
Screenshot Capture Diagnostic Script

This script checks if the screenshot storage system is configured correctly.
Run this to verify:
1. /images directory is writable
2. Database has application_screenshot_path column
3. Recent screenshots exist in /images
4. Database records are properly linked to screenshots
"""

import os
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

# Add backend to path
backend_path = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_path))

from db import get_connection, DB_PATH

def check_directory_permissions():
    """Check if /images directory exists and is writable."""
    print("\n📁 Checking directory permissions...")
    
    images_dir = Path("/images")
    if not images_dir.exists():
        print(f"❌ /images directory does not exist!")
        print(f"   Creating it now...")
        try:
            images_dir.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created /images directory")
        except Exception as e:
            print(f"❌ Failed to create /images: {e}")
            return False
    else:
        print(f"✅ /images directory exists")
    
    # Check writable
    test_file = images_dir / ".test_write"
    try:
        test_file.write_text("test")
        test_file.unlink()
        print(f"✅ /images is writable")
        return True
    except Exception as e:
        print(f"❌ /images is not writable: {e}")
        return False

def check_database_schema():
    """Check if database has required columns."""
    print("\n🗄️  Checking database schema...")
    
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(listings)")
            columns = {row[1] for row in cur.fetchall()}
            
            required = ["application_status", "application_screenshot_path"]
            for col in required:
                if col in columns:
                    print(f"✅ Column '{col}' exists")
                else:
                    print(f"❌ Column '{col}' missing!")
                    return False
        return True
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def check_recent_screenshots():
    """Check if any screenshots exist in /images."""
    print("\n📸 Checking for recent screenshots...")
    
    images_dir = Path("/images")
    if not images_dir.exists():
        print("❌ /images directory not found")
        return
    
    # Find all PNG files
    screenshots = list(images_dir.rglob("*.png"))
    
    if not screenshots:
        print("⚠️  No screenshots found in /images")
        return
    
    print(f"✅ Found {len(screenshots)} screenshot(s):")
    for screenshot in screenshots[:10]:  # Show first 10
        rel_path = screenshot.relative_to(images_dir.parent)
        size = screenshot.stat().st_size / 1024  # KB
        print(f"   - {rel_path} ({size:.1f} KB)")
    
    if len(screenshots) > 10:
        print(f"   ... and {len(screenshots) - 10} more")

def check_database_records():
    """Check database records with screenshot paths."""
    print("\n💾 Checking database records...")
    
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            
            # Count total listings
            cur.execute("SELECT COUNT(*) FROM listings")
            total = cur.fetchone()[0]
            print(f"📊 Total listings: {total}")
            
            # Count with screenshots
            cur.execute(
                "SELECT COUNT(*) FROM listings WHERE application_screenshot_path IS NOT NULL"
            )
            with_screenshots = cur.fetchone()[0]
            print(f"📊 Listings with screenshots: {with_screenshots}")
            
            # Show recent applications
            cur.execute(
                """
                SELECT external_id, application_status, application_screenshot_path, updated_at
                FROM listings
                WHERE application_status != 'none' OR application_screenshot_path IS NOT NULL
                ORDER BY updated_at DESC
                LIMIT 5
                """
            )
            
            rows = cur.fetchall()
            if rows:
                print(f"\n📋 Recent applications:")
                for row in rows:
                    external_id, status, screenshot, updated = row
                    status_emoji = "✅" if screenshot else "❌"
                    print(f"   {status_emoji} {external_id}")
                    print(f"      Status: {status}")
                    print(f"      Screenshot: {screenshot or '(none)'}")
                    print(f"      Updated: {updated}")
            else:
                print("⚠️  No application records found")
                
    except Exception as e:
        print(f"❌ Database query error: {e}")

def verify_screenshot_paths():
    """Verify that screenshot paths in DB actually exist on disk."""
    print("\n🔍 Verifying screenshot paths...")
    
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT external_id, application_screenshot_path
                FROM listings
                WHERE application_screenshot_path IS NOT NULL
                """
            )
            
            rows = cur.fetchall()
            if not rows:
                print("⚠️  No records with screenshot paths found")
                return
            
            valid = 0
            invalid = 0
            
            for external_id, screenshot_path in rows:
                # Convert relative path to absolute
                full_path = Path("/") / screenshot_path
                
                if full_path.exists():
                    valid += 1
                    print(f"✅ {external_id}: {screenshot_path}")
                else:
                    invalid += 1
                    print(f"❌ {external_id}: {screenshot_path} (FILE NOT FOUND)")
            
            print(f"\n📊 Summary: {valid} valid, {invalid} invalid")
            
    except Exception as e:
        print(f"❌ Verification error: {e}")

def main():
    print("=" * 60)
    print("🔍 Screenshot Capture Diagnostic Tool")
    print("=" * 60)
    
    print(f"\n📂 Database path: {os.path.abspath(DB_PATH)}")
    
    # Run all checks
    checks = [
        check_directory_permissions,
        check_database_schema,
        check_recent_screenshots,
        check_database_records,
        verify_screenshot_paths,
    ]
    
    for check in checks:
        try:
            check()
        except Exception as e:
            print(f"❌ Check failed: {e}")
    
    print("\n" + "=" * 60)
    print("✅ Diagnostic complete")
    print("=" * 60)

if __name__ == "__main__":
    main()
