#!/bin/sh
# Vespa application deployment script for Docker init container
# This script waits for Vespa to be ready and deploys the application package
set -e

# Install required packages (curl and zip)
apk add --no-cache curl zip > /dev/null 2>&1 || true

CONFIG_SERVER="${VESPA_CONFIG_SERVER:-http://vespa:19071}"
APP_DIR="/app"
MAX_RETRIES=60
RETRY_INTERVAL=5

echo "=== Vespa Init Container ==="
echo "Config server: ${CONFIG_SERVER}"
echo "Application directory: ${APP_DIR}"

# Wait for config server to be ready
echo ""
echo "Waiting for Vespa config server to be ready..."
retries=0
until curl -sf "${CONFIG_SERVER}/state/v1/health" | grep -q '"up"'; do
    retries=$((retries + 1))
    if [ $retries -ge $MAX_RETRIES ]; then
        echo "ERROR: Config server not ready after $((MAX_RETRIES * RETRY_INTERVAL)) seconds"
        exit 1
    fi
    echo "  Config server not ready, waiting... (attempt ${retries}/${MAX_RETRIES})"
    sleep $RETRY_INTERVAL
done
echo "Config server is ready!"

# Check if application is already deployed
echo ""
echo "Checking if application is already deployed..."
status_code=$(curl -sf -o /dev/null -w "%{http_code}" "${CONFIG_SERVER}/application/v2/tenant/default/application/default" || echo "000")
if [ "$status_code" = "200" ]; then
    echo "Application already deployed, checking if update is needed..."
fi

# Create application package zip
echo ""
echo "Creating application package from ${APP_DIR}..."
cd "${APP_DIR}"
rm -f /tmp/app.zip
zip -rq /tmp/app.zip . -x ".*" -x "__MACOSX/*"
echo "Application package created: $(ls -lh /tmp/app.zip | awk '{print $5}')"

# Deploy application package
echo ""
echo "Deploying application package..."
deploy_response=$(curl -s -w "\n%{http_code}" --header "Content-Type:application/zip" \
    --data-binary @/tmp/app.zip \
    "${CONFIG_SERVER}/application/v2/tenant/default/prepareandactivate" 2>&1)
http_code=$(echo "${deploy_response}" | tail -1)
body=$(echo "${deploy_response}" | sed '$d')

if [ "$http_code" != "200" ]; then
    echo "ERROR: Deployment failed with HTTP ${http_code}"
    echo "Response: ${body}"
    exit 1
fi
echo "Deployment response:"
echo "${body}" | head -20

# Wait for application to converge (all services started)
echo ""
echo "Waiting for application to converge..."
retries=0
while [ $retries -lt $MAX_RETRIES ]; do
    converge_status=$(curl -sf "${CONFIG_SERVER}/application/v2/tenant/default/application/default/environment/prod/region/default/instance/default/serviceconverge" 2>/dev/null || echo '{"converged":false}')

    if echo "${converge_status}" | grep -q '"converged":true'; then
        echo "Application converged successfully!"
        break
    fi

    retries=$((retries + 1))
    if [ $retries -ge $MAX_RETRIES ]; then
        echo "WARNING: Application did not converge within timeout, but deployment was accepted"
        echo "Last status: ${converge_status}"
        break
    fi

    echo "  Waiting for convergence... (attempt ${retries}/${MAX_RETRIES})"
    sleep $RETRY_INTERVAL
done

# Verify document API is accessible
echo ""
echo "Verifying document API is accessible..."
retries=0
until curl -sf "http://vespa:8081/state/v1/health" | grep -q '"up"'; do
    retries=$((retries + 1))
    if [ $retries -ge 30 ]; then
        echo "WARNING: Document API not responding, but deployment completed"
        break
    fi
    echo "  Document API not ready, waiting... (attempt ${retries}/30)"
    sleep 2
done

if curl -sf "http://vespa:8081/state/v1/health" | grep -q '"up"'; then
    echo "Document API is ready!"
fi

echo ""
echo "=== Vespa initialization complete ==="
