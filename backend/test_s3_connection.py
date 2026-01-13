#!/usr/bin/env python3
"""Quick test script for S3 destination connection."""

import asyncio
import os
from uuid import uuid4

# Set credentials
# Get from: az keyvault secret show --vault-name airweave-core-dev-kv --name aws-iam-access-key-id
os.environ["AWS_S3_DESTINATION_ACCESS_KEY_ID"] = os.getenv(
    "AWS_S3_DESTINATION_ACCESS_KEY_ID", "YOUR_AWS_ACCESS_KEY_ID_HERE"
)
os.environ["AWS_S3_DESTINATION_SECRET_ACCESS_KEY"] = os.getenv(
    "AWS_S3_DESTINATION_SECRET_ACCESS_KEY", "YOUR_AWS_SECRET_ACCESS_KEY_HERE"
)

from airweave.platform.configs.auth import S3AuthConfig
from airweave.platform.destinations.s3 import S3Destination


async def test_s3_connection():
    """Test S3 connection with role assumption."""
    print("🧪 Testing S3 destination connection...")
    print()

    # Test configuration
    auth_config = S3AuthConfig(
        role_arn="arn:aws:iam::050451371276:role/airweave-s3-writer",
        external_id="airweave~IlvSW21jXvGmynFvXD6b9ZY",
        bucket_name="airweave-test-bucket-1768301352",
        bucket_prefix="airweave/",
        aws_region="us-east-1",
    )

    print("Configuration:")
    print(f"  Role ARN:  {auth_config.role_arn}")
    print(f"  Bucket:    {auth_config.bucket_name}")
    print(f"  Prefix:    {auth_config.bucket_prefix}")
    print(f"  Region:    {auth_config.aws_region}")
    print()

    try:
        # Create destination
        destination = await S3Destination.create(
            credentials=auth_config,
            config={},
            collection_id=uuid4(),
            sync_id=uuid4(),
        )

        print("✅ Successfully created S3 destination")
        print("✅ Assumed IAM role")
        print("✅ Connected to S3 bucket")
        print()

        # List objects (test read access)
        session = destination._get_s3_client()
        async with session as s3:
            response = await s3.list_objects_v2(
                Bucket=auth_config.bucket_name, Prefix=auth_config.bucket_prefix, MaxKeys=5
            )

            object_count = response.get("KeyCount", 0)
            print(f"📦 Found {object_count} objects in bucket with prefix")

            if object_count > 0:
                print("\nRecent objects:")
                for obj in response.get("Contents", [])[:5]:
                    print(f"  - {obj['Key']} ({obj['Size']} bytes)")

        print()
        print("🎉 Connection test successful!")
        return True

    except Exception as e:
        print(f"❌ Connection test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_s3_connection())
    exit(0 if success else 1)
