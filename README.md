# Database Benchmarking with Locust

## Objectives

This project enables comprehensive database benchmarking using your own custom payloads and queries, designed to reflect real-world performance comparisons.

It provides a consistent and repeatable way to measure and compare database throughput, latency, and scalability across different environments.

The benchmarking suite is built for easy deployment, supporting both local execution with Docker and scalable deployments on Azure Kubernetes Service (AKS).

Currently supported databases:
- Azure SQL Database (all), SQL Server
- Azure Cosmos DB for NoSQL
- Azure Cosmos DB for MongoDB (including native MongoDB)

## About Locust

[Locust](https://locust.io/) is an open-source load testing tool that allows you to define user behavior in Python code and simulate millions of concurrent users. Locust is highly scalable, distributed, and provides a web-based UI for monitoring test progress and results. For more details, see the [Locust documentation](https://docs.locust.io/en/stable/).

## Installation Requirements

- Python 3.8+
- Docker
- Azure CLI (for AKS deployment)
- kubectl (for AKS deployment)
- A pre-existing database for testing

Install Python dependencies:
```pwsh
pip install -r requirements.txt
```

## Configuration
Workload configuration files are located in the `config` directory.
You can edit these YAML files to define and customize benchmarking scenarios for Cosmos DB, MongoDB, or SQL databases.
Each YAML file appears as a user class in the Locust UI, allowing you to select and run different workloads.

When deploying to AKS, these configuration files are uploaded to the `config` File Share in Azure Blob Storage and should be updated there as needed.
For local runs, the `config` folder is mounted directly into the container, so no upload is required.

> [!NOTE]
>
> If you change a configuration file after Locust has started, you must restart the pods for changes to take effect.

## Local Deployment with Docker

1. Build the Docker image:
```pwsh
docker build -t dbbenchmark:latest ./src
```

2. Run the container:
```pwsh
docker run -p 8089:8089 -e LOCUST_OPTIONS="--class-picker" -v ${PWD}/config/:/app/config -d dbbenchmark:latest
```

## Deployment on Azure Kubernetes Service (AKS)

1. Setup Azure infrastructure:
```pwsh
./deploy/setupAKS.ps1 -ResourceGroupName <resource group name> -Location <location> [-AksName <aks name> -StorageAccountName <storage account> -AcrName <container registry> -Suffix <resource suffix> -AksVMSku <vm sku>]
```

> Resources created:
> - Resource group
> - Azure Blob Storage Standard and a File Share
> - Azure Container Registry Basic
> - Azure Kubernetes Services with 2 node pools
>
>> Database resources for performance testing are not created by this template.


2. Port-forward Locust master:
```pwsh
kubectl port-forward service/master 8089:8089
```

3. Access the Locust UI at http://localhost:8089. Select the workload profile, specify the number of users and ramp details, enter your database credentials in the `Custom` section and start the test.

### Useful commands

- Scale worker replicas:
```pwsh
kubectl scale deployment locust-worker --replicas <number of pods>
```

- Restart pods:
```pwsh
kubectl rollout restart deployment --namespace default
```