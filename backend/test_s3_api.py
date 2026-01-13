#!/usr/bin/env python3
"""Test S3 destination via API endpoint."""

import json

import requests

# Configuration
API_URL = "http://localhost:8000"  # Change if your backend runs on a different port
API_TOKEN = None  # Set this if you need authentication

# Test configuration
config = {
    "role_arn": "arn:aws:iam::050451371276:role/airweave-s3-writer",
    "external_id": "airweave~IlvSW21jXvGmynFvXD6b9ZY",
    "bucket_name": "airweave-test-bucket-1768301352",
    "bucket_prefix": "airweave/",
    "aws_region": "us-east-1",
}


def test_s3_connection():
    """Test S3 connection via API."""
    print("🧪 Testing S3 destination via API...")
    print()
    print("Configuration:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    print()

    headers = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"

    try:
        # Test connection endpoint
        response = requests.post(
            f"{API_URL}/api/v1/s3/test", json=config, headers=headers, timeout=30
        )

        print(f"Status Code: {response.status_code}")
        print()

        if response.status_code == 200:
            result = response.json()
            print("✅ Connection test successful!")
            print()
            print("Response:")
            print(json.dumps(result, indent=2))
            return True
        else:
            print("❌ Connection test failed")
            print()
            print("Response:")
            print(response.text)
            return False

    except Exception as e:
        print(f"❌ Request failed: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("Make sure your backend is running:")
    print("  cd /Users/raufakdemir/Documents/code/airweave-ai/airweave/backend")
    print("  source test-s3-local.sh")
    print("  python local.py")
    print("=" * 60)
    print()

    success = test_s3_connection()
    exit(0 if success else 1)
