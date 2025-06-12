import logging
import time
from pymongo import MongoClient
from executors.base_executor import BaseExecutor
from datamanager import DataManager

class MongoDBExecutor(BaseExecutor):
    def __init__(self, environment, workload_name):
        super().__init__(environment, workload_name)
        self.client = None
        self.db = None
        self._connect()
        self._param_map_cache = {}

    def _connect(self):
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

    def execute(self, command, task_name):
        if self.client is None:
            logging.error("No MongoDB client available. Attempting to reconnect.")
            self._connect()
            if self.client is None:
                logging.error("Reconnection to MongoDB failed.")
                return

        # Select database per task if specified, else use default
        db_name = command.get('database')
        db = self.client[db_name]

        update_template = {}
        # Determine which JSON object to use for parameter mapping
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
        if cache_key not in self._param_map_cache:
            parameters = command.get('parameters', [])
            param_names = [param.get('name') for param in parameters]
            param_paths_dict = self._map_all_param_paths(json_template, param_names)
            param_paths_dict_upd = self._map_all_param_paths(update_template, param_names)
            self._param_map_cache[cache_key] = {
                'parameters': parameters,
                'param_names': param_names,
                'param_paths_dict': param_paths_dict,
                'param_paths_dict_upd': param_paths_dict_upd
            }
        else:
            cache = self._param_map_cache[cache_key]
            parameters = cache['parameters']
            param_names = cache['param_names']
            param_paths_dict = cache['param_paths_dict']
            param_paths_dict_upd = cache['param_paths_dict_upd']

        # Generate parameter values
        param_values = {}
        for param in parameters:
            value, _ = DataManager.generate_param_value(param)
            param_values[param.get('name')] = value

        # Replace all parameters in the template
        final_command = self._replace_all_params(json_template, param_paths_dict, param_values)
        upd_command = self._replace_all_params(update_template, param_paths_dict_upd, param_values)

        collection_name = command.get('collection')
        collection = db[collection_name] if collection_name else None

        start_time = time.time()
        try:
            result = None
            if command_type == 'insert':
                result = collection.insert_one(final_command)
            elif command_type == 'aggregate':
                logging.debug(f"Executing MongoDB aggregate command: {final_command}")
                cursor = collection.aggregate(final_command)
            elif command_type == 'find':
                logging.debug(f"Executing MongoDB find command: {final_command}")
                cursor = collection.find(final_command)
            elif command_type == 'update':
                logging.debug(f"Executing MongoDB update command: {final_command}, update: {upd_command}")
                result = collection.update_one(final_command, upd_command, upsert=True)
            elif command_type == 'replace':
                logging.debug(f"Executing MongoDB replace command: {final_command}, update: {upd_command}")
                result = collection.replace_one(final_command, upd_command, upsert=True)
            elif command_type == 'delete':
                logging.debug(f"Executing MongoDB delete command: {final_command}")
                result = collection.delete_one(final_command)
            else:
                logging.error(f"Unsupported MongoDB command type: {command_type}")
                return

            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('MongoDB', task_name, total_time, response_length=1)
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('MongoDB-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing MongoDB command: {e}")
