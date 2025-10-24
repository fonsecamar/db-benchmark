import logging
import time
import sys

from azure.cosmos import CosmosClient, exceptions
from datamanager import DataManager
from executors.base_executor import BaseExecutor
from typing import Any, Dict, Optional

# Set up logging once at module level
logger = logging.getLogger("azure.cosmos._cosmos_http_logging_policy")
logger.setLevel(logging.WARNING)

logger = logging.getLogger('urllib3')
logger.setLevel(logging.WARNING)

class CosmosDBExecutor(BaseExecutor):
    def __init__(self, environment: Any):
        super().__init__(environment)
        self.client: Optional[CosmosClient] = None
        self._connect()
        self._param_map_cache: Dict[str, Dict] = {}
        self._container_cache: Dict[Any, Any] = {}

    def _connect(self) -> None:
        """Establish CosmosDB client connection."""
        try:
            self.client = CosmosClient.from_connection_string(
                self.environment.parsed_options.cosmosdb_connection_string
            )
            logging.debug("CosmosDB connection established.")
        except Exception as e:
            logging.exception(f"CosmosDB connection error: {e}")
            self.client = None

    def _disconnect(self) -> None:
        if self.client:
            self.client = None

    def _get_container(self, db_name: str, collection_name: str):
        """Get or cache CosmosDB container client."""
        cache_key = (db_name, collection_name)
        if cache_key not in self._container_cache:
            db = self.client.get_database_client(db_name)
            container = db.get_container_client(collection_name)
            self._container_cache[cache_key] = container
        return self._container_cache[cache_key]

    def execute(self, command: Dict, task_name: str) -> None:
        """Execute a CosmosDB command."""
        if self.client is None:
            logging.error("No CosmosDB client available. Attempting to reconnect.")
            self._connect()
            if self.client is None:
                logging.error("Reconnection to CosmosDB failed.")
                return

        command_type = command.get('type')
        db_name = command.get('database')
        collection_name = command.get('collection')
        container = self._get_container(db_name, collection_name)

        cache_key = f"{task_name}:{command_type}"
        cache = self._param_map_cache.get(cache_key)
        if not cache:
            parameters = command.get('parameters', [])

            for param in parameters:
                if param.get('type') == 'datetime':
                    param['as'] = 'string'

            param_names = [param.get('name') for param in parameters]
            json_template = command.get('document', {})
            param_paths_dict = self._map_all_param_paths(json_template, param_names)
            cache = {
                'parameters': parameters,
                'param_names': param_names,
                'param_paths_dict': param_paths_dict,
                'json_template': json_template
            }
            self._param_map_cache[cache_key] = cache
        else:
            parameters = cache['parameters']
            param_names = cache['param_names']
            param_paths_dict = cache['param_paths_dict']
            json_template = cache['json_template']

        # Generate parameter values
        param_values = {param['name']: DataManager.generate_param_value(param)[0] for param in parameters}

        result = None
        db_op = None

        if command_type in ('insert', 'upsert'):
            document = self._replace_all_params(command.get('document', {}), param_paths_dict, param_values)
            if command_type == 'insert':
                db_op = lambda: container.create_item(body=document)
            else:
                db_op = lambda: container.upsert_item(body=document)
            
            logging.debug(f"Executing CosmosDB {command_type} command: {document}")
        elif command_type in ('delete', 'point_read'):
            id_field = command.get('id')
            pk_fields = command.get('partitionKey', [])
            item_id = param_values.get(id_field, id_field)
            if isinstance(pk_fields, list):
                pk_value = [param_values.get(pk, pk) for pk in pk_fields]
                if len(pk_value) == 1:
                    pk_value = pk_value[0]
            else:
                pk_value = param_values.get(pk_fields, pk_fields)
            if command_type == 'delete':
                db_op = lambda: container.delete_item(item=item_id, partition_key=pk_value)
            else:
                db_op = lambda: container.read_item(item=item_id, partition_key=pk_value)
            
            logging.debug(f"Executing CosmosDB {command_type} command: pk: {pk_value}, id: {item_id}")
        elif command_type == 'select':
            query = command.get('query')
            query_parameters = [
                {"name": param['name'], "value": param_values[param['name']]}
                for param in parameters if param['name'] in param_values
            ]
            db_op = lambda: list(container.query_items(
                query=query,
                parameters=query_parameters,
                enable_cross_partition_query=True
            ))
            logging.debug(f"Executing CosmosDB {command_type} command: {query}, params: {query_parameters}")
        else:
            logging.error(f"Unsupported CosmosDB command type: {command_type}")
            return

        start_time = time.perf_counter()
        try:
            result = db_op()
            total_time = int((time.perf_counter() - start_time) * 1000)
            logging.debug(f"CosmosDB {command_type} command result: {result}")
            length = sys.getsizeof(result)
            self._fire_event('CosmosDB', task_name, total_time, response_length=length)
        except exceptions.CosmosResourceNotFoundError:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event(f'CosmosDB-{command_type}-NotFound', task_name, total_time)
        except Exception as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('CosmosDB-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing CosmosDB command: {e}")
