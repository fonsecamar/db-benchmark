# Azure Cosmos DB Workload Configuration Guide

## Overview

This guide covers workload configuration for Azure Cosmos DB NoSQL API. For generic configuration concepts, see [WORKLOAD_CONFIG_GUIDE](./WORKLOAD_CONFIG_GUIDE.md).

## Connection Configuration

Before starting the benchmarks, provide the following parameter in the Custom Parameters section in the UI.

> **📝 Note**: You can use the connection string directly from the Azure Portal (Keys section) and optionally append the custom parameters below to control region preferences and multi-master behavior.

### Connection String Format

```
AccountEndpoint=<endpoint>;AccountKey=<key>;Regions=<region1>,<region2>;MultipleWriteLocations=<True|False>
```

**Required Parameters**:
- `AccountEndpoint`: Your Cosmos DB account URI (e.g., `https://myaccount.documents.azure.com:443/`)
- `AccountKey`: Primary or secondary key for authentication

**Optional Custom Parameters**:
- `Regions`: Comma-separated list of Azure regions for preferred read/write routing and failover priority
  - Single region: `Regions=UK South`
  - Multiple regions: `Regions=UK South,West Europe,East US`
  - The order defines the **priority** for routing operations and failover
  - **Behavior depends on account topology**:
    - **Single-region write accounts**: Regions are used for **read preferences only**. Writes always go to the write region.
    - **Multi-region write accounts** (with `MultipleWriteLocations=True`): Regions are used for **both read and write preferences**. Operations are routed to the preferred region.
  - First region in list = highest priority

- `MultipleWriteLocations`: Enable multi-master writes (default: `False`)
  - `MultipleWriteLocations=True`: Enable writes to any configured region (requires account to have multi-region writes enabled)
  - `MultipleWriteLocations=False`: Writes go only to the designated write region
  - **Important**: This must match your Cosmos DB account configuration. If your account doesn't have multi-region writes enabled, setting this to `True` will have no effect.

### Connection String Examples

**Portal Connection String (unmodified)**:
```
AccountEndpoint=https://myaccount.documents.azure.com:443/;AccountKey=ABC123...
```
- Uses SDK's automatic region discovery
- Works for all account topologies

**Single Region Read Preference**:
```
AccountEndpoint=https://myaccount.documents.azure.com:443/;AccountKey=ABC123...;Regions=UK South
```
- Prefer reading from UK South
- Writes go to designated write region (single-region write accounts)

**Multi-Region with Read Preferences** (single-region write account):
```
AccountEndpoint=https://myaccount.documents.azure.com:443/;AccountKey=ABC123...;Regions=UK South,West Europe,East US
```
- Reads prefer UK South → West Europe → East US (in order)
- Writes always go to the account's write region
- Automatic failover for reads if preferred region is unavailable

**Multi-Master Configuration** (multi-region write account):
```
AccountEndpoint=https://myaccount.documents.azure.com:443/;AccountKey=ABC123...;Regions=UK South,West Europe,East US;MultipleWriteLocations=True
```
- **Both reads and writes** prefer UK South → West Europe → East US
- Enables lowest latency for global applications
- Automatic failover for both reads and writes
- Requires account to have multi-region writes enabled in Azure Portal

### Understanding Region Topology

**Single-Region Write Accounts** (default):
- One write region, multiple read regions
- `Regions` parameter controls **read routing only**
- All writes go to designated write region regardless of `Regions`
- Lower cost, simpler conflict resolution

**Multi-Region Write Accounts** (Multi-Master):
- Multiple write regions, multiple read regions
- `Regions` parameter controls **both read and write routing**
- Requires `MultipleWriteLocations=True` in connection string
- Higher availability, lower global write latency
- Requires conflict resolution policy
- Higher cost

**To enable multi-region writes**: Configure in Azure Portal → Cosmos DB Account → Replicate data globally → Enable Multi-region Writes

### Multi-Region Benefits

When using preferred regions in the connection string:

✅ **Automatic Failover**: Client automatically fails over to next region if preferred region becomes unavailable

✅ **Read Optimization**: Reads are routed to closest/preferred region for lower latency (all account types)

✅ **Write Optimization** (Multi-Master only): Writes are routed to closest/preferred region when `MultipleWriteLocations=True`

✅ **High Availability**: Continues operating even if a region experiences issues

✅ **Predictable Performance**: Control which regions handle your workload

**Important**: All regions specified must be enabled in your Cosmos DB account configuration. See [Distribute data globally](https://learn.microsoft.com/azure/cosmos-db/distribute-data-globally) for setup instructions.

## Quick Start

```yaml
type: CosmosDB
runStartUpFrequency: <Not yet supported>
tasks:
  - taskName: insert
    taskWeight: 50
    command:
      operation: insert
      container: users
      parameters:
        - name: "@id"
          type: guid
        - name: "@name"
          type: faker.name
        - name: "@email"
          type: faker.email
        - name: "@partitionKey"
          type: random_int
          start: 1
          end: 100
```

## Configuration Structure

### Operations

Cosmos DB supports five core operations:

```yaml
command:
  operation: <operation_type>
  container: <container_name>
  parameters: [...]
  batchSize: <integer>  # Optional for bulk operations
```

#### Operation Types

**1. Insert** (Create document)
```yaml
operation: insert
container: cart
parameters:
  - name: "@id"
    type: guid
  - name: "@player_id"
    type: random_int
    start: 1
    end: 1000000
  - name: "@partitionKey"  # REQUIRED
    type: random_int
    start: 1
    end: 1000000
```
- Creates new document
- Requires unique `id` and `partitionKey`
- Fails if document with same `id` exists in same partition

**2. Upsert** (Create or replace)
```yaml
operation: upsert
container: cart
parameters:
  - name: "@id"
    type: guid
  - name: "@ticket_date"
    type: datetime
  - name: "@partitionKey"
    type: random_int
    start: 1
    end: 1000000
```
- Creates document if not exists
- Replaces entire document if exists
- Requires `id` and `partitionKey`

**3. Point Read** (Read by ID)
```yaml
operation: point_read
container: cart
partitionKey:
  - "@partitionKey"
id: "@id"
parameters:
  - name: "@id"
    type: guid
  - name: "@partitionKey"  # REQUIRED for efficient read
    type: random_int
    start: 1
    end: 1000000
```
- Most efficient read operation (lowest RU)
- Requires both `id` and `partitionKey`
- Returns single document
- **Costs ~1 RU** (most efficient)

**4. Select** (Query documents)
```yaml
operation: select
container: cart
query: SELECT * FROM c WHERE c.player_id = @player_id
parameters:
  - name: "@player_id"
    type: random_int
    start: 1
    end: 1000000
```
- Executes SQL-like query
- Can be cross-partition (expensive)
- Supports filters, projections, ORDER BY, etc.
- **Costs vary** based on query complexity and results

**5. Delete**
```yaml
operation: delete
container: cart
partitionKey:
  - "@partitionKey"
id: "@id"
parameters:
  - name: "@id"
    type: guid
  - name: "@partitionKey"  # REQUIRED
    type: random_int
    start: 1
    end: 1000000
```
- Deletes document by ID
- Requires both `id` and `partitionKey`


## Best Practices

### 1. Partition Key Design

**Critical Decision** - Cannot be changed after creation!

**Good Partition Keys**:
```yaml
# High cardinality, evenly distributed
partitionKey: /userId
partitionKey: /deviceId
partitionKey: /orderId
partitionKey: /tenantId
```

**Properties of Good Partition Keys**:
- High cardinality (many distinct values)
- Even distribution of reads/writes
- Naturally isolates related data
- Avoids hot partitions

**Anti-Patterns**:
```yaml
# ❌ Low cardinality
partitionKey: /country  # Few values

# ❌ Monotonic (time-based)
partitionKey: /date  # Creates hot partition

# ❌ Boolean
partitionKey: /isActive  # Only 2 values
```

**Partition Key Best Practices**: https://learn.microsoft.com/azure/cosmos-db/partitioning-overview

### 2. Query Optimization

**Single Partition Query** (Best):
```yaml
operation: select
query: SELECT * FROM c WHERE c.player_id = @player_id AND c.contest > 100
parameters:
  - name: "@player_id"
    type: random_int
    start: 1
    end: 1000000
```
- Filter includes partition key
- Query executes on single partition
- **Lowest RU cost**

**Cross-Partition Query** (May Be Expensive):
```yaml
operation: select
query: SELECT * FROM c WHERE c.contest > 100
# No partition key filter - scans ALL partitions
```
- Scans multiple/all partitions
- **High RU cost**
- Use only when necessary

**Tips**:
- Always include partition key in WHERE clause when possible
- Use point reads (`point_read`) instead of SELECT for single document
- Use `ORDER BY` cautiously (requires index)
- Limit result size with `TOP` or `OFFSET`/`LIMIT`. Prefer continuation token strategy for paging.

### 3. Indexing Policy

**Default Policy** (Index everything):
```yaml
indexingPolicy:
  indexingMode: consistent
  automatic: true
  includedPaths:
    - path: /*
```
- Good for unknown query patterns
- Higher write cost (indexes all properties)

**Optimized Policy** (Selective indexing):
```yaml
indexingPolicy:
  indexingMode: consistent
  automatic: true
  includedPaths:
    - path: /player_id/?
    - path: /ticket_date/?
    - path: /contest/?
  excludedPaths:
    - path: /*
```
- Lower write cost
- Only indexed paths can be queried efficiently
- Define based on known query patterns

**Composite Indexes** (For ORDER BY, range queries):
```yaml
indexingPolicy:
  compositeIndexes:
    - - path: /player_id
        order: ascending
      - path: /ticket_date
        order: descending
```

### 4. Request Units (RU) Optimization

**RU Costs** (approximate - unindexed):
| Operation | RU Cost |
|-----------|---------|
| Point Read (1 KB) | ~1 RU |
| Insert (1 KB) | ~5 RU |
| Update (1 KB) | ~10 RU |
| Delete | ~5 RU |
| Query | Variable |


**Reduce RU Consumption**:
- Use point reads instead of queries
- Query single partitions
- Project only needed fields: `SELECT c.id, c.name`
- Use smaller documents
- Optimize indexing policy
- Batch operations

**Monitor RUs**: https://learn.microsoft.com/en-us/azure/cosmos-db/monitor?tabs=resource-specific-diagnostics


### 5. Document Design

**Multiple design options** - https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/modeling-data

## Example Workloads

### OLTP Workload

```yaml
type: CosmosDB
tasks:
  - taskName: insert
    taskWeight: 30
    command:
      operation: insert
      container: cart
      parameters:
        - name: "@id"
          type: guid
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000
        - name: "@ticket_id"
          type: guid
        - name: "@ticket_date"
          type: datetime
        - name: "@contest"
          type: random_int
          start: 1
          end: 1000
        - name: "@numbers"
          type: constant
          value: "[1,2,3,4,5,6]"
          as: string

  - taskName: point_read
    taskWeight: 50
    command:
      operation: point_read
      container: cart
      partitionKey:
        - "@player_id"
      id: "@id"
      parameters:
        - name: "@id"
          type: guid
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000

  - taskName: query
    taskWeight: 15
    command:
      operation: select
      container: cart
      query: SELECT TOP 10 * FROM c WHERE c.player_id = @player_id ORDER BY c.ticket_date DESC
      parameters:
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000

  - taskName: delete
    taskWeight: 5
    command:
      operation: delete
      container: cart
      partitionKey:
        - "@player_id"
      id: "@id"
      parameters:
        - name: "@id"
          type: guid
        - name: "@player_id"
          type: random_int
          start: 1
          end: 150000000
```

## Performance Tips

### Throughput Configuration

**Manual Throughput**:
```yaml
throughput: 400  # Fixed 400 RU/s (minimum)
```
- Predictable cost
- Good for steady workloads
- Can scale up/down manually

**Autoscale Throughput**:
```yaml
autoscaleThroughput: 4000  # 400-4000 RU/s
```
- Scales based on usage
- Good for variable workloads

**Shared vs Dedicated**:
- **Database-level**: Share RUs across containers (cost-effective)
- **Container-level**: Dedicated RUs per container (predictable performance)

### Azure Cosmos DB Emulator

For local development:
```
https://localhost:8081
```

**Cosmos DB Emulator**: https://learn.microsoft.com/azure/cosmos-db/local-emulator

## Common Pitfalls

❌ **Don't**:
- Choose partition key without analysis
- Forget partition key in queries
- Use cross-partition queries frequently
- Index everything (high write cost)
- Use large documents (2 MB limit)
- Store binary data (use Blob storage)

✅ **Do**:
- Design partition key carefully
- Use point reads when possible
- Include partition key in WHERE clause
- Optimize indexing policy
- Monitor RU consumption

## Monitoring During Benchmarks

**Key Metrics**:
- Request Units consumed (RU/s)
- Request charge per operation
- Throttling rate (429 errors)
- Latency (p50, p95, p99)
- Storage usage
- Partition key distribution

**Azure Monitor**:
```
- Total Request Units (RU/s)
- Normalized RU Consumption (%)
- Total Requests
- Requests by Status Code
- Requests by Operation Type
```

**Diagnostic Settings**:
- Enable DataPlaneRequests
- Monitor throttling events
- Track RU consumption per operation


## References

- **Azure Cosmos DB Documentation**: https://learn.microsoft.com/azure/cosmos-db/
- **NoSQL API**: https://learn.microsoft.com/azure/cosmos-db/nosql/
- **Partitioning**: https://learn.microsoft.com/azure/cosmos-db/partitioning-overview
- **Request Units**: https://learn.microsoft.com/azure/cosmos-db/request-units
- **Query Optimization**: https://learn.microsoft.com/azure/cosmos-db/nosql/query/
- **Best Practices**: https://learn.microsoft.com/azure/cosmos-db/nosql/best-practice-dotnet

## See Also

- [Generic Workload Configuration Guide](./WORKLOAD_CONFIG_GUIDE.md)
- Example configuration: `config/cosmos_workload.yaml`
