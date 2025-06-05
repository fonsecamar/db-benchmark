param(
    [Parameter(Mandatory = $true)]
    [string]$ResourceGroupName,
    [Parameter(Mandatory = $true)]
    [string]$Location,
    [Parameter(Mandatory = $false)]
    [string]$AksName = $null,
    [Parameter(Mandatory = $false)]
    [string]$StorageAccountName = $null,
    [Parameter(Mandatory = $false)]
    [string]$AcrName = $null,
    [Parameter(Mandatory = $false)]
    [string]$Suffix = $null
)

$ImageName = "opdbbenchmark:latest"

# 1. Create the resource group
az group create --name $ResourceGroupName --location $Location

$paramArgs = @("location=$Location")
if ($Suffix) { $paramArgs += "suffix=$Suffix" }
if ($AksName) { $paramArgs += "aksName=$AksName" }
if ($StorageAccountName) { $paramArgs += "storageAccountName=$StorageAccountName" }
if ($AcrName) { $paramArgs += "acrName=$AcrName" }

# 2. Deploy the Bicep template
$bicepOutput = az deployment group create `
    --resource-group $ResourceGroupName `
    --template-file ../infra/deploy.bicep `
    --parameters $paramArgs `
    --query "properties.outputs" -o json | ConvertFrom-Json

$AksName = $bicepOutput.aksName.value
$StorageAccountName = $bicepOutput.storageAccountName.value
$ContainerName = $bicepOutput.containerName.value
$AcrLogin = $bicepOutput.acrLogin.value

$AccountKey = az storage account keys list `
    --resource-group $ResourceGroupName `
    --account-name $StorageAccountName `
    --query "[0].value" -o tsv

az storage blob upload `
    --account-name $StorageAccountName `
    --account-key $AccountKey `
    --container-name $ContainerName `
    --name "config.json" `
    --file "../config/config.json" `
    --overwrite

# 3. Get AKS credentials
az aks get-credentials --resource-group $ResourceGroupName --name $AksName --overwrite-existing

az acr build --registry $AcrLogin --image $ImageName ../src/.

kubectl delete secret azure-blob-secret --ignore-not-found
kubectl create secret generic azure-blob-secret `
    --from-literal=azurestorageaccountname=$StorageAccountName `
    --from-literal=azurestorageaccountkey=$AccountKey `
    --type=Opaque

# 4. Deploy master-service, master pod, and workers
kubectl apply -f ../deploy/master-service.yaml

(Get-Content ../deploy/config-volume.yaml) `
    -replace '\$\{RESOURCE_GROUP\}', $ResourceGroupName `
    -replace '\$\{STORAGE_ACCOUNT\}', $StorageAccountName `
    -replace '\$\{CONTAINER_NAME\}', $ContainerName | `
kubectl apply -f -

(Get-Content ../deploy/master-deployment.yaml) `
    -replace '\$\{IMAGE_NAME\}', "$AcrLogin/$ImageName" | `
kubectl apply -f -

(Get-Content ../deploy/worker-deployment.yaml) `
    -replace '\$\{IMAGE_NAME\}', "$AcrLogin/$ImageName" | `
kubectl apply -f -

Write-Host "Deployment complete. AKS cluster '$AksName' is ready and workloads are deployed."

kubectl port-forward service/master 8089:8089