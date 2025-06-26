import logging
import time
from typing import Any, Dict, Optional
from pymongo import MongoClient
from executors.base_executor import BaseExecutor
from datamanager import DataManager

logging.getLogger("pymongo").setLevel(logging.INFO)

class MongoDBExecutor(BaseExecutor):
    def __init__(self, environment: Any, workload_name: str):
        super().__init__(environment, workload_name)
        self.client: Optional[MongoClient] = None
        self.db = None
        self._connect()
        self._param_map_cache: Dict[str, Dict] = {}

    def _connect(self) -> None:
        try:
            self.client = MongoClient(
                self.environment.parsed_options.mongodb_connection_string,
                serverSelectionTimeoutMS=5000
            )
            logging.debug("MongoDB connection established.")
        except Exception as e:
            logging.exception(f"MongoDB connection error: {e}")
            self.client = None
            self.db = None

    def _disconnect(self) -> None:
        if self.client:
            self.client.close()
            self.client = None
            self.db = None

    def execute(self, command: Dict, task_name: str) -> None:
        if self.client is None:
            logging.error("No MongoDB client available. Attempting to reconnect.")
            self._connect()
            if self.client is None:
                logging.error("Reconnection to MongoDB failed.")
                return

        db_name = command.get('database')
        db = self.client[db_name]

        update_template = {}
        command_type = command.get('type')
        if command_type == 'insert':
            json_template = command.get('document', {})
        elif command_type == 'aggregate':
            json_template = command.get('pipeline', [])
        elif command_type in ('find', 'delete', 'update', 'replace'):
            json_template = command.get('filter', {})
            if command_type == 'update':
                update_template = command.get('update', {})
            elif command_type == 'replace':
                update_template = command.get('replacement', {})
        else:
            json_template = {}

        cache_key = f"{task_name}:{command_type}"
        cache = self._param_map_cache.get(cache_key)
        if not cache:
            parameters = command.get('parameters', [])
            param_names = [param.get('name') for param in parameters]
            param_paths_dict = self._map_all_param_paths(json_template, param_names)
            param_paths_dict_upd = self._map_all_param_paths(update_template, param_names)
            cache = {
                'parameters': parameters,
                'param_names': param_names,
                'param_paths_dict': param_paths_dict,
                'param_paths_dict_upd': param_paths_dict_upd
            }
            self._param_map_cache[cache_key] = cache
        else:
            parameters = cache['parameters']
            param_names = cache['param_names']
            param_paths_dict = cache['param_paths_dict']
            param_paths_dict_upd = cache['param_paths_dict_upd']

        param_values = {param['name']: DataManager.generate_param_value(param)[0] for param in parameters}
        final_command = self._replace_all_params(json_template, param_paths_dict, param_values)
        upd_command = self._replace_all_params(update_template, param_paths_dict_upd, param_values)

        collection_name = command.get('collection')
        collection = db[collection_name] if collection_name else None

        db_op = None
        projection = None
        limit = 0
        sort = None

        if command_type == 'insert':
            db_op = lambda: collection.insert_one(final_command)
        elif command_type == 'aggregate':
            db_op = lambda: collection.aggregate(final_command)
        elif command_type == 'find':
            projection = command.get('projection', None)
            limit = command.get('limit', 0)
            sort = command.get('sort', None)
            db_op = lambda: collection.find(filter=final_command, projection=projection, limit=limit, sort=sort)
        elif command_type == 'update':
            db_op = lambda: collection.update_one(final_command, upd_command, upsert=True)
        elif command_type == 'replace':
            db_op = lambda: collection.replace_one(final_command, upd_command, upsert=True)
        elif command_type == 'delete':
            db_op = lambda: collection.delete_one(final_command)
        else:
            logging.error(f"Unsupported MongoDB command type: {command_type}")
            return
        
        logging.debug(f"Executing MongoDB {command_type} command: {final_command}{', update: ' + str(upd_command) if upd_command else ''}{', projection: ' + str(projection) if projection else ''}{', limit: ' + str(limit) if limit else ''}{', sort: ' + str(sort) if sort else ''}")

        start_time = time.perf_counter()
        try:
            result = db_op()
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('MongoDB', task_name, total_time, response_length=1)
        except Exception as e:
            total_time = int((time.perf_counter() - start_time) * 1000)
            self._fire_event('MongoDB-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing MongoDB command: {e}")
