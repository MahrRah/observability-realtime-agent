#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Default configuration — override any value via environment variables
###############################################################################
RESOURCE_GROUP="${RESOURCE_GROUP:-obs-realtime}"
LOCATION="${LOCATION:-swedencentral}"
OPENAI_ACCOUNT_NAME="${OPENAI_ACCOUNT_NAME:-oai-voice-agent-dev}"
BICEP_TEMPLATE="${BICEP_TEMPLATE:-infra/main.bicep}"
BICEP_PARAMS="${BICEP_PARAMS:-infra/main.bicepparam}"
ENV_FILE=".env"

###############################################################################
# Helpers
###############################################################################
info()  { printf "\033[1;34m▸ %s\033[0m\n" "$*"; }
ok()    { printf "\033[1;32m✔ %s\033[0m\n" "$*"; }
fail()  { printf "\033[1;31m✖ %s\033[0m\n" "$*" >&2; exit 1; }

###############################################################################
# Pre-flight checks
###############################################################################
command -v az >/dev/null 2>&1 || fail "Azure CLI (az) is not installed."
az account show >/dev/null 2>&1 || fail "Not logged in to Azure. Run 'az login' first."

###############################################################################
# 1. Resource Group — get or create
###############################################################################
info "Checking resource group '${RESOURCE_GROUP}' ..."

if az group show --name "$RESOURCE_GROUP" --output none 2>/dev/null; then
    ok "Resource group '${RESOURCE_GROUP}' already exists."
else
    info "Creating resource group '${RESOURCE_GROUP}' in '${LOCATION}' ..."
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none
    ok "Resource group '${RESOURCE_GROUP}' created."
fi

###############################################################################
# 2. Deploy infrastructure
###############################################################################
info "Deploying Bicep template ..."

TMPFILE=$(mktemp)
ERRFILE=$(mktemp)
trap 'rm -f "$TMPFILE" "$ERRFILE"' EXIT

if ! az deployment group create \
    --resource-group "$RESOURCE_GROUP" \
    --template-file "$BICEP_TEMPLATE" \
    --parameters "$BICEP_PARAMS" \
    --parameters openAiAccountName="$OPENAI_ACCOUNT_NAME" \
    --output json > "$TMPFILE" 2>"$ERRFILE"; then
    echo ""
    cat "$ERRFILE" >&2
    fail "Bicep deployment failed."
fi

# Show warnings (if any) but don't let them break JSON parsing
[[ -s "$ERRFILE" ]] && cat "$ERRFILE" >&2

# Extract outputs from the JSON (skip any non-JSON warning lines)
read -r AZURE_OPENAI_ENDPOINT OAI_ACCOUNT_NAME DEPLOYMENT_NAME APPINSIGHTS_CONN_STR < <(
    python3 -c "
import json, sys

# Find the first '{' to skip Bicep warnings printed before the JSON body
raw = open(sys.argv[1]).read()
start = raw.find('{')
if start == -1:
    print('Deployment output:', raw[:500], file=sys.stderr)
    sys.exit('No JSON found in deployment output')
data = json.loads(raw[start:])
outputs = data['properties']['outputs']
print(
    outputs['openAiEndpoint']['value'],
    outputs['openAiAccountName']['value'],
    outputs['realtimeDeploymentName']['value'],
    outputs['applicationInsightsConnectionString']['value'],
)
" "$TMPFILE"
) || fail "Failed to parse deployment outputs."

ok "Deployment complete — endpoint: ${AZURE_OPENAI_ENDPOINT}"

###############################################################################
# 3. Write .env file
###############################################################################
info "Writing ${ENV_FILE} ..."

cat > "$ENV_FILE" <<EOF
AZURE_OPENAI_ENDPOINT=${AZURE_OPENAI_ENDPOINT}
AZURE_OPENAI_DEPLOYMENT=${DEPLOYMENT_NAME}
AGENT_INSTRUCTIONS=You are a helpful voice assistant. Keep responses concise.
VOICE=ash
HOST=0.0.0.0
PORT=8000
APPLICATIONINSIGHTS_CONNECTION_STRING=${APPINSIGHTS_CONN_STR}
EOF

ok "${ENV_FILE} written successfully."
