@description('Resource group location')
param location string = resourceGroup().location

@minLength(2)
@maxLength(13)
param suffix string = uniqueString(resourceGroup().id)

@description('Name of the AKS cluster')
@maxLength(63)
param aksName string = 'aks-${suffix}'

@description('Name of the storage account')
@minLength(3)
@maxLength(24)
param storageAccountName string = 'blob${suffix}'

@description('Name of the container registry')
@minLength(5)
@maxLength(50)
param acrName string = 'acr${suffix}'

param aksVMSku string = 'Standard_D8as_v5'

resource acr 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: acrName
  sku: {
    name: 'Basic'
  }
  location: location
  properties: {
    adminUserEnabled: true
  }
}

resource storageAccount 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: 'Allow'
    }
  }
}

resource fileServices 'Microsoft.Storage/storageAccounts/fileServices@2024-01-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    shareDeleteRetentionPolicy: {
      enabled: false
    }
  }
}

resource configShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2024-01-01' = {
  parent: fileServices
  name: 'config'
  properties: {
    accessTier: 'Hot'
    enabledProtocols: 'SMB'
  }
}

// AKS Cluster with 2 node pools
resource aks 'Microsoft.ContainerService/managedClusters@2025-03-01' = {
  name: aksName
  location: location
  sku: {
    name: 'Base'
    tier: 'Standard'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    kubernetesVersion: '1.32.4'
    dnsPrefix: '${aksName}-dns'
    agentPoolProfiles: [
      // System node pool
      {
        name: 'systempool'
        count: 1
        vmSize: aksVMSku
        osDiskSizeGB: 128
        osDiskType: 'Managed'
        kubeletDiskType: 'OS'
        osType: 'Linux'
        osSKU: 'Ubuntu'
        mode: 'System'
        type: 'VirtualMachineScaleSets'
        enableAutoScaling: false
        nodeLabels: {
          app: 'system'
        }
        securityProfile: {
          enableVTPM: false
          enableSecureBoot: false
        }
        
      }
      // User node pool
      {
        name: 'locustworker'
        count: 2
        vmSize: aksVMSku
        osDiskSizeGB: 128
        osDiskType: 'Managed'
        kubeletDiskType: 'OS'
        type: 'VirtualMachineScaleSets'
        enableAutoScaling: false
        mode: 'User'
        osType: 'Linux'
        osSKU: 'Ubuntu'
        nodeLabels: {
          app: 'locust-worker'
        }
        securityProfile: {
          enableVTPM: false
          enableSecureBoot: false
        }
      }
    ]
    nodeResourceGroup: '${resourceGroup().name}-${aksName}'
    storageProfile: {
      blobCSIDriver: { 
        enabled: true
      }
    }
    networkProfile: {
      networkPlugin: 'azure'
      networkPolicy: 'azure'
      networkDataplane: 'azure'
      loadBalancerSku: 'Standard'
      loadBalancerProfile: {
        managedOutboundIPs: {
          count: 1
        }
        backendPoolType: 'nodeIPConfiguration'
      }
      serviceCidr: '10.1.0.0/16'
      dnsServiceIP: '10.1.0.10'
      outboundType: 'loadBalancer'
      serviceCidrs: [
        '10.1.0.0/16'
      ]
      ipFamilies: [
        'IPv4'
      ]
    }
    enableRBAC: true
  }
}

resource acrRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, 'acrpull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
    principalId: aks.properties.identityProfile.kubeletidentity.objectId
    principalType: 'ServicePrincipal'
  }
}

output aksName string = aks.name
output storageAccountName string = storageAccount.name
output shareName string = configShare.name
output acrLogin string = acr.properties.loginServer
