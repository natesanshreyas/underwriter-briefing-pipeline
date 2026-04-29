#!/bin/bash
set -e

# Wait for environment
until az containerapp env show -n underwriter-env -g lab- &>/dev/null; do
  echo "Waiting for environment..."
  sleep 5
done

echo "✅ Environment ready. Deploying apps..."

# Get secrets
CLIENT_ID=$(jq -r '.CLIENT_ID' secrets.json)
LANGUAGE_ENDPOINT=$(jq -r '.LANGUAGE_ENDPOINT' secrets.json)
LANGUAGE_KEY=$(jq -r '.LANGUAGE_KEY' secrets.json)
OPENAI_API_KEY=$(jq -r '.OPENAI_API_KEY' secrets.json)
OPENAI_ENDPOINT=$(jq -r '.OPENAI_ENDPOINT' secrets.json)
OPENAI_MODEL=$(jq -r '.OPENAI_MODEL' secrets.json)
COSMOS_ENDPOINT=$(jq -r '.COSMOS_ENDPOINT' secrets.json)
COSMOS_KEY=$(jq -r '.COSMOS_KEY' secrets.json)

# Get ACR creds
ACR_USERNAME=$(az acr credential show -n acrtibke7spoognw --query username -o tsv)
ACR_PASSWORD=$(az acr credential show -n acrtibke7spoognw --query "passwords[0].value" -o tsv)

# Deploy agent
echo "🤖 Deploying agent..."
az containerapp create \
  --name underwriter-agent \
  --resource-group lab- \
  --environment underwriter-env \
  --image acrtibke7spoognw.azurecr.io/underwriter-agent:latest \
  --target-port 8080 \
  --ingress external \
  --registry-server acrtibke7spoognw.azurecr.io \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --cpu 0.5 \
  --memory 1Gi \
  --min-replicas 1 \
  --max-replicas 3 \
  --env-vars \
    "AZURE_FUNCTIONS_BASE_URL=https://underwriter-briefing-api.azurewebsites.net/api" \
    "OPENAI_API_KEY=$OPENAI_API_KEY" \
    "OPENAI_ENDPOINT=$OPENAI_ENDPOINT" \
    "OPENAI_MODEL=$OPENAI_MODEL"

AGENT_URL=$(az containerapp show -n underwriter-agent -g lab- --query properties.configuration.ingress.fqdn -o tsv)

# Deploy batch job
echo "⏰ Deploying batch job..."
az containerapp job create \
  --name underwriter-batch-job \
  --resource-group lab- \
  --environment underwriter-env \
  --trigger-type "Schedule" \
  --cron-expression "0 */6 * * *" \
  --image acrtibke7spoognw.azurecr.io/underwriter-batch:latest \
  --registry-server acrtibke7spoognw.azurecr.io \
  --registry-username "$ACR_USERNAME" \
  --registry-password "$ACR_PASSWORD" \
  --cpu 1.0 \
  --memory 2Gi \
  --replica-timeout 3600 \
  --replica-retry-limit 1 \
  --parallelism 1 \
  --replica-completion-count 1 \
  --env-vars \
    "CLIENT_ID=$CLIENT_ID" \
    "LANGUAGE_ENDPOINT=$LANGUAGE_ENDPOINT" \
    "LANGUAGE_KEY=$LANGUAGE_KEY" \
    "OPENAI_API_KEY=$OPENAI_API_KEY" \
    "OPENAI_ENDPOINT=$OPENAI_ENDPOINT" \
    "OPENAI_MODEL=$OPENAI_MODEL" \
    "COSMOS_ENDPOINT=$COSMOS_ENDPOINT" \
    "COSMOS_KEY=$COSMOS_KEY" \
    "REPORT_WINDOW_DAYS=90"

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Deployment complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Resources:"
echo "  • Agent URL:    https://$AGENT_URL"
echo "  • Batch Job:    Runs every 6 hours"
echo ""
echo "🧪 Test:"
echo "  curl https://$AGENT_URL"
echo ""
echo "▶️  Run batch manually:"
echo "  az containerapp job start -n underwriter-batch-job -g lab-"
echo ""
