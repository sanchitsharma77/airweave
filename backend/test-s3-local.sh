#!/bin/bash
# Local S3 Destination Testing Setup
#
# Usage:
#   source test-s3-local.sh      # Export env vars
#   python local.py              # Start backend
#   python test_s3_api.py        # Test connection in another terminal

# Export AWS credentials for S3 destination (from dev account)
# Get these from: az keyvault secret show --vault-name airweave-core-dev-kv --name aws-iam-access-key-id
export AWS_S3_DESTINATION_ACCESS_KEY_ID="YOUR_AWS_ACCESS_KEY_ID_HERE"
export AWS_S3_DESTINATION_SECRET_ACCESS_KEY="YOUR_AWS_SECRET_ACCESS_KEY_HERE"

echo "✅ AWS S3 destination credentials exported"
echo ""
echo "📋 Test Configuration:"
echo "  IAM Role ARN:  arn:aws:iam::050451371276:role/airweave-s3-writer"
echo "  External ID:   airweave~IlvSW21jXvGmynFvXD6b9ZY"
echo "  Bucket:        airweave-test-bucket-1768301352"
echo "  Prefix:        airweave/"
echo "  Region:        us-east-1"
echo ""
echo "🚀 Next steps:"
echo "  1. Start backend:  python local.py"
echo "  2. Test via API:   python test_s3_api.py (in another terminal)"
echo "  3. Or use UI at:   http://localhost:8000"
echo ""
