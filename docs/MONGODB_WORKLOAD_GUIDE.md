# MongoDB Workload Configuration Guide

## Overview

This guide covers workload configuration for MongoDB and Azure Cosmos DB for MongoDB vCore. For generic configuration concepts, see [WORKLOAD_CONFIG_GUIDE](./WORKLOAD_CONFIG_GUIDE.md).

## Connection Configuration

Before starting the benchmarks, provide the following parameter in the Custom Parameters section in the UI:
- `mongodb_connection_string`: Full MongoDB connection string - `Format: mongodb://username:password@host:port/database?options`

**Azure Example**:
```
mongodb+srv://<user>:<password>@<cluster name>.mongocluster.cosmos.azure.com/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000
```

## Quick Start

```yaml
type: MongoDB
runStartUpFrequency: Once
tasks:
  - taskName: insert_document
    taskWeight: 50
    command:
      type: insert
      database: mydb
      collection: users
      batchSize: 100
      parameters:
        - name: "@user_id"
          type: random_int
          start: 1
          end: 1000000
        - name: "@email"
          type: faker.email
      document:
        user_id: "@user_id"
        email: "@email"
        created_at: "@timestamp"
```

## Configuration Structure

### Command Types

MongoDB supports multiple operation types:

```yaml
command:
  type: <operation_type>
  database: <database_name>
  collection: <collection_name>
  # Operation-specific fields
```

#### Supported Operations
- `insert` - Insert documents
- `find` - Query documents
- `update` - Update documents
- `replace` - Replace entire document
- `delete` - Delete documents
- `aggregate` - Aggregation pipeline

### Insert Operation

```yaml
command:
  type: insert
  database: lab
  collection: cart
  batchSize: 100  # Use insert_many for bulk inserts
  parameters: [...]
  document:
    field1: "@param1"
    field2: "@param2"
    nested:
      field3: "@param3"
```

**Batch Insert**:
- `batchSize: 1` - `insert_one()`
- `batchSize: > 1` - `insert_many()` with `ordered=False` for performance

### Find Operation

```yaml
command:
  type: find
  database: lab
  collection: cart
  parameters: [...]
  filter:
    player_id: "@player_id"
  projection:  # Optional
    player_id: 1
    ticket_id: 1
    _id: 0
  limit: 10  # Optional
  sort:  # Optional
    - ["created_at", -1]
```

### Update Operation

```yaml
command:
  type: update
  database: lab
  collection: cart
  parameters: [...]
  filter:
    player_id: "@player_id"
  update:
    $set:
      status: "active"
      updated_at: "@timestamp"
```

### Replace Operation

```yaml
command:
  type: replace
  database: lab
  collection: cart
  parameters: [...]
  filter:
    player_id: "@player_id"
    ticket_id: "@ticket_id"
  replacement:
    player_id: "@player_id"
    ticket_id: "@ticket_id"
    status: "replaced"
```

### Delete Operation

```yaml
command:
  type: delete
  database: lab
  collection: cart
  parameters: [...]
  filter:
    player_id: "@player_id"
```

### Aggregation Pipeline

```yaml
command:
  type: aggregate
  database: lab
  collection: cart
  parameters: [...]
  pipeline:
    - { $match: { contest: { $gte: "@min", $lte: "@max" } } }
    - { $group: { _id: "$contest", total: { $sum: 1 } } }
    - { $sort: { total: -1 } }
    - { $limit: 10 }
```

## Startup Script

Create `config/<workload_name>_startup.yaml`:

```yaml
databases:
  - name: lab
    collections:
      - name: cart
        shardKey: player_id  # Optional, for sharded clusters
        indexes:
          - name: idx_player_id
            keys:
              player_id: 1
            options:
              unique: false
          - name: idx_ticket_date
            keys:
              ticket_date: -1
            options: {}
          - name: idx_compound
            keys:
              player_id: 1
              contest: 1
            options:
              unique: true
```

**Features**:
- Creates databases and collections
- Creates indexes with options
- Enables sharding (if admin access available)

## Best Practices

### 1. Schema Design

**MongoDB Schema Design**: https://www.mongodb.com/docs/manual/core/data-modeling-introduction/

### 2. Indexing Strategy

```yaml
# Single field index (most common)
indexes:
  - name: idx_email
    keys:
      email: 1
    options:
      unique: true

# Compound index (for multiple field queries)
indexes:
  - name: idx_user_date
    keys:
      user_id: 1
      created_at: -1

# Text index (for text search)
indexes:
  - name: idx_description_text
    keys:
      description: text
```

**Index Guidelines**:
- Index fields used in filters
- Monitor index usage with `.explain()`

**MongoDB Indexing**: https://www.mongodb.com/docs/manual/indexes/

### 3. Write Optimization

```yaml
# High-throughput inserts
- taskName: bulk_insert
  taskWeight: 80
  command:
    type: insert
    database: lab
    collection: logs
    batchSize: 500  # insert_many for better performance
    parameters:
      - name: "@log_id"
        type: guid
        as: string
      - name: "@message"
        type: faker.text
    document:
      log_id: "@log_id"
      message: "@message"
      timestamp: "@timestamp"
```

**Tips**:
- Use `batchSize` for bulk operations

### 4. Read Optimization

```yaml
# Efficient query with projection
- taskName: optimized_find
  taskWeight: 60
  command:
    type: find
    database: lab
    collection: users
    filter:
      status: "active"
      country: "@country"
    projection:
      name: 1
      email: 1
      _id: 0
    limit: 100
    sort:
      - ["created_at", -1]
```

**Tips**:
- Always use indexed fields in filters
- Use projections to return only needed fields
- Apply `limit` to control result size

### 5. Aggregation Pipelines

```yaml
- taskName: analytics_pipeline
  taskWeight: 20
  command:
    type: aggregate
    database: lab
    collection: orders
    pipeline:
      # Stage 1: Filter (use indexes)
      - { $match: { status: "completed", date: { $gte: "@start_date" } } }
      # Stage 2: Group
      - { $group: { _id: "$product_id", total_sales: { $sum: "$amount" } } }
      # Stage 3: Sort
      - { $sort: { total_sales: -1 } }
      # Stage 4: Limit
      - { $limit: 10 }
```

**Pipeline Optimization**:
- Put `$match` early to use indexes
- Minimize documents between stages
- Use `$project` to reduce document size
- Be cautious with `$lookup` (joins can be slow)

**Aggregation Framework**: https://www.mongodb.com/docs/manual/aggregation/

## Example Workloads

### E-Commerce Workload

```yaml
type: MongoDB
runStartUpFrequency: Once
tasks:
  - taskName: create_order
    taskWeight: 40
    command:
      type: insert
      database: ecommerce
      collection: orders
      parameters:
        - name: "@order_id"
          type: guid
          as: string
        - name: "@user_id"
          type: random_int
          start: 1
          end: 100000
        - name: "@amount"
          type: random_int
          start: 10
          end: 1000
      document:
        order_id: "@order_id"
        user_id: "@user_id"
        amount: "@amount"
        status: "pending"
        items: [
          { product_id: "prod_001", quantity: 2 },
          { product_id: "prod_002", quantity: 1 }
        ]
        created_at: "@timestamp"

  - taskName: find_user_orders
    taskWeight: 50
    command:
      type: find
      database: ecommerce
      collection: orders
      filter:
        user_id: "@user_id"
        status: "pending"
      projection:
        order_id: 1
        amount: 1
        created_at: 1
      limit: 20
      sort:
        - ["created_at", -1]
      parameters:
        - name: "@user_id"
          type: random_int
          start: 1
          end: 100000

  - taskName: update_order_status
    taskWeight: 10
    command:
      type: update
      database: ecommerce
      collection: orders
      filter:
        order_id: "@order_id"
      update:
        $set:
          status: "completed"
          completed_at: "@timestamp"
      parameters:
        - name: "@order_id"
          type: guid
          as: string
```

## Performance Tips

### Batch Size Guidelines
| Operation Type | Recommended Batch Size |
|---------------|----------------------|
| Insert | 100-1000 |
| Update/Delete | 1 (batch updates not supported) |
| Find | Use `limit` in query |

## Common Pitfalls

❌ **Don't**:
- Create too many indexes (slows writes)
- Use large documents (16MB limit)
- Perform unbounded queries (use `limit`)
- Use `$where` JavaScript expressions (slow)
- Ignore index usage with `.explain()`

✅ **Do**:
- Design schema around access patterns
- Use appropriate batch sizes
- Monitor slow queries
- Use projections to minimize data transfer

## References

- **Azure Cosmos DB for MongoDB vCore**: https://learn.microsoft.com/en-us/azure/cosmos-db/mongodb/vcore/
- **Schema Design Patterns**: https://www.mongodb.com/blog/post/building-with-patterns-a-summary

## See Also

- [Generic Workload Configuration Guide](./WORKLOAD_CONFIG_GUIDE.md)
- Example configuration: `config/mongodb_workload.yaml`
