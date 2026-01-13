#!/bin/bash
# Load AWS credentials from Azure Key Vault for local testing

echo "📥 Loading AWS credentials from Azure Key Vault..."

export AWS_S3_DESTINATION_ACCESS_KEY_ID=$(az keyvault secret show --vault-name airweave-core-dev-kv --name aws-iam-access-key-id --query value -o tsv 2>/dev/null)
export AWS_S3_DESTINATION_SECRET_ACCESS_KEY=$(az keyvault secret show --vault-name airweave-core-dev-kv --name aws-iam-secret-access-key --query value -o tsv 2>/dev/null)

if [ -z "$AWS_S3_DESTINATION_ACCESS_KEY_ID" ] || [ -z "$AWS_S3_DESTINATION_SECRET_ACCESS_KEY" ]; then
    echo "❌ Failed to load credentials from Key Vault"
    echo "   Make sure you're logged in: az login"
    exit 1
fi

echo "✅ AWS credentials loaded!"
echo "   Access Key ID: ${AWS_S3_DESTINATION_ACCESS_KEY_ID:0:20}..."
echo ""
echo "🚀 Now run: python local.py"
