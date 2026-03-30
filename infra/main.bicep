targetScope = 'resourceGroup'

@description('Name of the Azure OpenAI resource')
param openAiAccountName string

@description('Azure region')
param location string = resourceGroup().location

@description('Realtime model deployment name')
param realtimeDeploymentName string = 'gpt-4o-realtime'

@description('Realtime model name')
@allowed([
  'gpt-4o-realtime-preview'
  'gpt-realtime'
  'gpt-realtime-1.5'
])
param realtimeModelName string = 'gpt-4o-realtime-preview'

@description('Model version')
param realtimeModelVersion string = '2024-12-17'

@description('Deployment capacity (TPM in thousands)')
@minValue(1)
param deploymentCapacity int = 1

resource openAiAccount 'Microsoft.CognitiveServices/accounts@2025-12-01' = {
  name: openAiAccountName
  location: location
  kind: 'OpenAI'
  identity: { type: 'SystemAssigned' }
  properties: {
    customSubDomainName: openAiAccountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
  sku: { name: 'S0' }
}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${openAiAccountName}-law'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: '${openAiAccountName}-appi'
  location: location
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
  }
}

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

output openAiEndpoint string = openAiAccount.properties.endpoint
output openAiAccountName string = openAiAccount.name
output realtimeDeploymentName string = realtimeDeployment.name
output principalId string = openAiAccount.identity.principalId
output applicationInsightsConnectionString string = appInsights.properties.ConnectionString
