# Research: Azure Bicep IaC for OpenAI Realtime Model Deployment

## Research Topics

1. Azure OpenAI Bicep Resource Types
2. Realtime Model Deployment Configuration
3. Complete Bicep Template Example
4. Supporting Resources for Observability

## Status: Complete

---

## 1. Azure OpenAI Bicep Resource Types

### Account Resource

- **Resource type**: `Microsoft.CognitiveServices/accounts`
- **Latest stable API version**: `2025-12-01`
- **AVM module API version**: `2025-06-01` (used by Azure Verified Modules)
- **Required properties**:
  - `name`: string (2-64 chars, pattern `^[a-zA-Z0-9][a-zA-Z0-9_.-]*$`)
  - `kind`: `'OpenAI'` for dedicated OpenAI, or `'AIServices'` for multi-service (recommended by AVM)
  - `sku`: object with `name` (required, typically `'S0'`) and optional `tier` (`'Standard'`)
  - `location`: string (Azure region)
  - `properties`: `AccountProperties` object
- **Key optional properties**:
  - `identity`: Managed identity (SystemAssigned, UserAssigned, or both)
  - `properties.customSubDomainName`: Required for token-based auth, private endpoints, and network ACLs
  - `properties.publicNetworkAccess`: `'Enabled'` or `'Disabled'`
  - `properties.disableLocalAuth`: bool (recommended `true` for security)
  - `properties.networkAcls`: Network access rules

### Deployment Resource

- **Resource type**: `Microsoft.CognitiveServices/accounts/deployments`
- **Latest stable API version**: `2025-12-01`
- **AVM module API version**: `2025-06-01`
- **Required properties**:
  - `name`: string (deployment name)
  - `parent`: reference to account resource
  - `properties.model`: DeploymentModel object
- **DeploymentModel properties**:
  - `format`: `'OpenAI'` (required for Azure OpenAI models)
  - `name`: model name string (e.g., `'gpt-4o-realtime-preview'`)
  - `version`: model version string (e.g., `'2024-12-17'`)
  - `publisher`: optional
- **SKU on deployment** (separate from account SKU):
  - `name`: `'GlobalStandard'`, `'Standard'`, `'ProvisionedManaged'`, etc.
  - `capacity`: int (TPM in thousands, e.g., `1` = 1K TPM)
- **Other deployment properties**:
  - `versionUpgradeOption`: `'NoAutoUpgrade'`, `'OnceCurrentVersionExpired'`, `'OnceNewDefaultVersionAvailable'`
  - `raiPolicyName`: content filter policy name
  - `deploymentState`: `'Running'` or `'Paused'`

### References

- https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts (Bicep pivot)
- https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts/deployments (Bicep pivot)

---

## 2. Realtime Model Deployment

### Available Realtime Models (as of March 2026)

| Model Name | Version | Status | Input Tokens | Output Tokens | Training Data |
|---|---|---|---|---|---|
| `gpt-4o-realtime-preview` | `2024-12-17` | Preview | 16,000 | 4,096 | Oct 2023 |
| `gpt-4o-realtime-preview` | `2025-06-03` | Preview | 32,000 | 4,096 | Oct 2023 |
| `gpt-4o-mini-realtime-preview` | `2024-12-17` | Preview | 128,000 | 4,096 | Oct 2023 |
| `gpt-realtime` | `2025-08-28` | **GA** | 32,000 | 4,096 | Oct 2023 |
| `gpt-realtime-mini` | `2025-10-06` | GA | 32,000 | 4,096 | Oct 2023 |
| `gpt-realtime-mini` | `2025-12-15` | GA | 32,000 | 4,096 | Oct 2023 |
| `gpt-realtime-1.5` | `2026-02-23` | Latest | 32,000 | 4,096 | Sep 2024 |

### Recommended Model for New Deployments

- **`gpt-realtime-1.5`** (version `2026-02-23`) is the latest realtime model
- **`gpt-realtime`** (version `2025-08-28`) is the first GA realtime model
- **`gpt-4o-realtime-preview`** (version `2024-12-17`) is still widely used but is preview
- For stability, use `gpt-realtime` (GA) or `gpt-realtime-1.5` (latest)

### Deployment SKU for Realtime Models

- Realtime models are available for **global deployments** only
- SKU name: **`GlobalStandard`** is the primary deployment type
- Realtime models are NOT available in `Standard` (regional) deployments for most regions
- Capacity is specified in TPM (tokens per minute), minimum typically `1`

### Region Availability for Realtime Models

Realtime models have the broadest availability in:

- **eastus2** — Full availability across all model types
- **swedencentral** — Full availability across all model types
- Other regions with Global Standard support also have access through global routing

Key regions with confirmed realtime model support (via Global Standard):

- East US 2
- Sweden Central
- East US
- West US
- Central US
- France Central
- Canada Central
- North Central US

**Note**: Global Standard deployments route traffic globally, so any region that supports Global Standard can access realtime models.

### References

- https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/realtime-audio
- https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure (Audio models section)

---

## 3. Azure Verified Module (AVM)

### Module Reference

- **Registry**: `br/public:avm/res/cognitive-services/account:<version>`
- **GitHub**: Azure/bicep-registry-modules — `avm/res/cognitive-services/account`
- **API versions used**: `2025-06-01` for accounts and deployments

### Key AVM Features

The AVM module supports:

- Account creation with `kind`: `'OpenAI'` or `'AIServices'`
- Model deployments via `deployments` parameter array
- Private endpoints
- Managed identity (system and user-assigned)
- Diagnostic settings (Log Analytics, Event Hub, Storage Account)
- Role assignments (e.g., `Cognitive Services OpenAI User`)
- Key Vault secrets export
- Network ACLs
- Customer-managed keys
- Resource locks

### AVM Deployment Parameter Format

```bicep
deployments: [
  {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-11-20'
    }
    name: 'gpt-4o'
    sku: {
      capacity: 10
      name: 'Standard'
    }
  }
]
```

### No Separate AVM Module for Deployments

There is no standalone AVM module for `Microsoft.CognitiveServices/accounts/deployments`. Deployments are handled as a parameter within the account module.

---

## 4. Complete Bicep Template — Raw Resources (No AVM)

This template deploys an Azure OpenAI account with a realtime model and supporting resources.

```bicep
// main.bicep — Azure OpenAI with Realtime Model Deployment
targetScope = 'resourceGroup'

// ============================================================================
// Parameters
// ============================================================================

@description('Name of the Azure OpenAI resource')
param openAiAccountName string

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Name of the realtime model deployment')
param realtimeDeploymentName string = 'gpt-4o-realtime'

@description('Realtime model name')
@allowed([
  'gpt-4o-realtime-preview'
  'gpt-4o-mini-realtime-preview'
  'gpt-realtime'
  'gpt-realtime-mini'
  'gpt-realtime-1.5'
])
param realtimeModelName string = 'gpt-4o-realtime-preview'

@description('Realtime model version')
param realtimeModelVersion string = '2024-12-17'

@description('Deployment capacity (TPM in thousands)')
@minValue(1)
param deploymentCapacity int = 1

@description('Custom subdomain name for the OpenAI resource (required for token-based auth)')
param customSubDomainName string = openAiAccountName

@description('Tags for all resources')
param tags object = {}

// ============================================================================
// Azure OpenAI Account
// ============================================================================

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2025-12-01' = {
  name: openAiAccountName
  location: location
  kind: 'OpenAI'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: customSubDomainName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
  sku: {
    name: 'S0'
  }
  tags: tags
}

// ============================================================================
// Realtime Model Deployment
// ============================================================================

resource realtimeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-12-01' = {
  parent: openAiAccount
  name: realtimeDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: deploymentCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: realtimeModelName
      version: realtimeModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

// ============================================================================
// Outputs
// ============================================================================

output openAiAccountName string = openAiAccount.name
output openAiEndpoint string = openAiAccount.properties.endpoint
output openAiResourceId string = openAiAccount.id
output realtimeDeploymentName string = realtimeDeployment.name
output principalId string = openAiAccount.identity.principalId
```

---

## 5. Complete Bicep Template — With AVM Module

Using the Azure Verified Module for a more complete, production-ready deployment:

```bicep
// main-avm.bicep — Using Azure Verified Module
targetScope = 'resourceGroup'

param openAiAccountName string
param location string = resourceGroup().location
param customSubDomainName string = openAiAccountName
param tags object = {}

module openAiAccount 'br/public:avm/res/cognitive-services/account:<version>' = {
  name: 'openAiAccountDeployment'
  params: {
    kind: 'OpenAI'
    name: openAiAccountName
    location: location
    customSubDomainName: customSubDomainName
    sku: 'S0'
    managedIdentities: {
      systemAssigned: true
    }
    deployments: [
      {
        model: {
          format: 'OpenAI'
          name: 'gpt-4o-realtime-preview'
          version: '2024-12-17'
        }
        name: 'gpt-4o-realtime'
        sku: {
          capacity: 1
          name: 'GlobalStandard'
        }
      }
    ]
    disableLocalAuth: false
    publicNetworkAccess: 'Enabled'
    tags: tags
  }
}

output openAiEndpoint string = openAiAccount.outputs.endpoint
output openAiResourceId string = openAiAccount.outputs.resourceId
output openAiPrincipalId string = openAiAccount.outputs.systemAssignedMIPrincipalId
```

---

## 6. Complete Template — With Observability Resources

Full deployment including Application Insights, Key Vault, and Managed Identity:

```bicep
// main-full.bicep — Full IaC with observability
targetScope = 'resourceGroup'

// ============================================================================
// Parameters
// ============================================================================

@description('Base name for resources')
param baseName string

@description('Azure region')
param location string = resourceGroup().location

@description('Realtime model to deploy')
param realtimeModelName string = 'gpt-4o-realtime-preview'

@description('Realtime model version')
param realtimeModelVersion string = '2024-12-17'

@description('Tags')
param tags object = {}

// ============================================================================
// Variables
// ============================================================================

var openAiName = '${baseName}-openai'
var logAnalyticsName = '${baseName}-logs'
var appInsightsName = '${baseName}-appinsights'
var keyVaultName = replace('${baseName}-kv', '-', '')

// ============================================================================
// Log Analytics Workspace
// ============================================================================

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
  tags: tags
}

// ============================================================================
// Application Insights
// ============================================================================

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
  tags: tags
}

// ============================================================================
// Key Vault
// ============================================================================

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
  }
  tags: tags
}

// ============================================================================
// Azure OpenAI Account
// ============================================================================

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2025-12-01' = {
  name: openAiName
  location: location
  kind: 'OpenAI'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    customSubDomainName: openAiName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: false
  }
  sku: {
    name: 'S0'
  }
  tags: tags
}

// ============================================================================
// Diagnostic Settings for OpenAI
// ============================================================================

resource openAiDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: '${openAiName}-diagnostics'
  scope: openAiAccount
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      {
        categoryGroup: 'allLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// ============================================================================
// Realtime Model Deployment
// ============================================================================

resource realtimeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-12-01' = {
  parent: openAiAccount
  name: 'gpt-4o-realtime'
  sku: {
    name: 'GlobalStandard'
    capacity: 1
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: realtimeModelName
      version: realtimeModelVersion
    }
    versionUpgradeOption: 'OnceCurrentVersionExpired'
  }
}

// ============================================================================
// Role Assignments
// ============================================================================

// Cognitive Services OpenAI User role for the managed identity
@description('Cognitive Services OpenAI User role definition ID')
var cognitiveServicesOpenAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource openAiRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAiAccount.id, openAiAccount.identity.principalId, cognitiveServicesOpenAiUserRoleId)
  scope: openAiAccount
  properties: {
    principalId: openAiAccount.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesOpenAiUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

// Key Vault Secrets User role for the managed identity
var keyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'

resource kvRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, openAiAccount.identity.principalId, keyVaultSecretsUserRoleId)
  scope: keyVault
  properties: {
    principalId: openAiAccount.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', keyVaultSecretsUserRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Outputs
// ============================================================================

output openAiAccountName string = openAiAccount.name
output openAiEndpoint string = openAiAccount.properties.endpoint
output openAiResourceId string = openAiAccount.id
output realtimeDeploymentName string = realtimeDeployment.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
output appInsightsInstrumentationKey string = appInsights.properties.InstrumentationKey
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output logAnalyticsWorkspaceId string = logAnalytics.id
output principalId string = openAiAccount.identity.principalId
```

---

## 7. Key Discoveries

### Resource Types and API Versions

- **Account**: `Microsoft.CognitiveServices/accounts@2025-12-01` (latest stable)
- **Deployment**: `Microsoft.CognitiveServices/accounts/deployments@2025-12-01` (latest stable)
- **AVM uses**: `2025-06-01` for both resources
- The `kind` field can be `'OpenAI'` (dedicated) or `'AIServices'` (multi-service)
- The account SKU is always `'S0'` for OpenAI/AIServices (not configurable per deployment type)

### Realtime Model Names

- **Legacy/preview**: `gpt-4o-realtime-preview` (versions `2024-12-17`, `2025-06-03`)
- **GA**: `gpt-realtime` (version `2025-08-28`) — first GA realtime model
- **Latest**: `gpt-realtime-1.5` (version `2026-02-23`)
- **Mini variants**: `gpt-4o-mini-realtime-preview`, `gpt-realtime-mini`

### Deployment Configuration

- **SKU**: `GlobalStandard` is required for realtime models (global routing)
- **Format**: Always `'OpenAI'`
- **Capacity**: Specified as int on the deployment `sku.capacity` — represents TPM allocation
- **Version upgrade**: Use `'OnceCurrentVersionExpired'` for automatic version management

### Region Restrictions

- Realtime models require **Global Standard** deployment type
- Global Standard routes traffic globally — most Azure regions can submit deployments
- **East US 2** and **Sweden Central** have the broadest model availability
- Realtime models are NOT available as regional Standard deployments in most regions

---

## 8. Caveats and Important Notes

1. **Preview vs GA**: `gpt-4o-realtime-preview` is still preview. For production, prefer `gpt-realtime` (GA) or `gpt-realtime-1.5`.
2. **Custom subdomain is required** if using token-based authentication (Microsoft Entra ID), which is the recommended auth method.
3. **disableLocalAuth**: Set to `true` in production for security. Set to `false` during development for API key convenience.
4. **Deployment serialization**: Azure OpenAI deployments within the same account are processed sequentially. If deploying multiple models, Bicep handles this automatically with `dependsOn`, but CI/CD pipelines may need retry logic.
5. **Quota**: Realtime API has specific rate limits for audio tokens and concurrent sessions, separate from standard chat completions quotas.
6. **Session limits**: Realtime sessions have a maximum duration of 30 minutes.
7. **Endpoint format**: For Realtime API, use the GA endpoint with `/openai/v1` in the URL. Do NOT use date-based API versions.

---

## 9. Follow-on Questions (Out of Scope)

- Specific network security requirements (private endpoints, VNet integration) for the observability sample
- Whether the sample app needs additional model deployments (e.g., Whisper for transcription)
- CI/CD pipeline integration (GitHub Actions / Azure DevOps) for deploying the Bicep template
- Budget/cost estimation for realtime model usage

---

## References

- Microsoft.CognitiveServices/accounts Bicep reference: https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts
- Microsoft.CognitiveServices/accounts/deployments Bicep reference: https://learn.microsoft.com/en-us/azure/templates/microsoft.cognitiveservices/accounts/deployments
- Azure OpenAI models reference: https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure
- Realtime API documentation: https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/realtime-audio
- AVM Cognitive Services module: https://github.com/Azure/bicep-registry-modules/tree/main/avm/res/cognitive-services/account
- AVM module registry reference: `br/public:avm/res/cognitive-services/account:<version>`
