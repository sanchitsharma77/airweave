#!/bin/bash
set -euo pipefail

# Deploy Vespa application package to config server
# Usage: ./deploy.sh [config_server_url]

CONFIG_SERVER="${1:-http://localhost:19071}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Waiting for config server to be ready at ${CONFIG_SERVER}..."
until curl -s "${CONFIG_SERVER}/state/v1/health" | grep -q '"up"'; do
    echo "  Config server not ready, waiting..."
    sleep 5
done
echo "Config server is ready!"

echo ""
echo "Creating application package zip..."
cd "${SCRIPT_DIR}"
rm -f app.zip
zip -r app.zip hosts.xml services.xml schemas/ -x ".*" -x "deploy.sh" -x "app.zip"

echo ""
echo "Deploying application package..."
curl -s --header "Content-Type:application/zip" \
    --data-binary @app.zip \
    "${CONFIG_SERVER}/application/v2/tenant/default/prepareandactivate" | jq .

echo ""
echo "Deployment complete!"
echo ""
echo "Waiting for application to be ready..."
sleep 10

echo ""
echo "Checking cluster status..."
curl -s "${CONFIG_SERVER}/application/v2/tenant/default/application/default/environment/prod/region/default/instance/default/serviceconverge" | jq .

echo ""
echo "=== Vespa is ready! ==="
echo ""
echo "Test document API:"
echo "  curl http://localhost:8081/document/v1/airweave/chunk/docid/test1"
echo ""
