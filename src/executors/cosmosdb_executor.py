import logging
import time
from azure.cosmos import CosmosClient, exceptions
from executors.base_executor import BaseExecutor
from datamanager import DataManager

class CosmosDBExecutor(BaseExecutor):
    def __init__(self, environment, workload_name):
        super().__init__(environment, workload_name)
        logger = logging.getLogger("azure.core.pipeline.policies.http_logging_policy")
        logger.setLevel(logging.WARNING)
        self.client = None
        self._connect()
        self._param_map_cache = {}
        self._container_cache = {}

    def _connect(self):
        try:
            self.client = CosmosClient.from_connection_string(self.environment.parsed_options.cosmosdb_connection_string)
            logging.debug("CosmosDB connection established.")
        except Exception as e:
            logging.exception(f"CosmosDB connection error: {e}")
            self.client = None

    def _get_container(self, db_name, collection_name):
        cache_key = (db_name, collection_name)
        if cache_key not in self._container_cache:
            db = self.client.get_database_client(db_name)
            container = db.get_container_client(collection_name)
            self._container_cache[cache_key] = container
        return self._container_cache[cache_key]

    def execute(self, command, task_name):
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
        if cache_key not in self._param_map_cache:
            parameters = command.get('parameters', [])
            param_names = [param.get('name') for param in parameters]
            json_template = command.get('document', {})
            param_paths_dict = self._map_all_param_paths(json_template, param_names)
            self._param_map_cache[cache_key] = {
                'parameters': parameters,
                'param_names': param_names,
                'param_paths_dict': param_paths_dict,
                'json_template': json_template
            }
        else:
            cache = self._param_map_cache[cache_key]
            parameters = cache['parameters']
            param_names = cache['param_names']
            param_paths_dict = cache['param_paths_dict']
            json_template = cache['json_template']

        param_values = {}
        for param in parameters:
            value, _ = DataManager.generate_param_value(param)
            param_values[param.get('name')] = value

        start_time = time.time()
        try:
            result = None
            if command_type == 'insert':
                document = self._replace_all_params(command.get('document', {}), param_paths_dict, param_values)
                result = container.create_item(body=document)
            elif command_type == 'upsert':
                document = self._replace_all_params(command.get('document', {}), param_paths_dict, param_values)
                result = container.upsert_item(body=document)
            elif command_type in ('delete', 'point_read'):
                id_field = command.get('id')
                pk_fields = command.get('partitionKey', [])
                item_id = param_values.get(id_field) if id_field in param_values else id_field
                if isinstance(pk_fields, list):
                    pk_value = [param_values.get(pk) if pk in param_values else pk for pk in pk_fields]
                    if len(pk_value) == 1:
                        pk_value = pk_value[0]
                else:
                    pk_value = param_values.get(pk_fields) if pk_fields in param_values else pk_fields
                if command_type == 'delete':
                    result = container.delete_item(item=item_id, partition_key=pk_value)
                else:
                    result = container.read_item(item=item_id, partition_key=pk_value)
            elif command_type == 'select':
                query = command.get('query')
                query_parameters = []
                for param in command.get('parameters', []):
                    pname = param['name']
                    if pname in param_values:
                        query_parameters.append({"name": pname, "value": param_values[pname]})
                items = list(container.query_items(
                    query=query,
                    parameters=query_parameters,
                    enable_cross_partition_query=True
                ))
                result = items
            else:
                logging.error(f"Unsupported CosmosDB command type: {command_type}")
                return
            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('CosmosDB', task_name, total_time, response_length=1)
        except exceptions.CosmosResourceNotFoundError:
            total_time = int((time.time() - start_time) * 1000)
            self._fire_event(f'CosmosDB-{command_type}-NotFound', task_name, total_time, response_length=0)
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('CosmosDB-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing CosmosDB command: {e}")
