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

    def _connect(self):
        try:
            self.client = MongoClient(
                self.environment.parsed_options.mongodb_connection_string,
                serverSelectionTimeoutMS=5000
            )
            logging.info("MongoDB connection established.")
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

        # Determine which JSON object to use for parameter mapping
        command_type = command.get('type')
        if command_type == 'insert':
            json_template = command.get('document', {})
        elif command_type == 'aggregate':
            json_template = command.get('pipeline', [])
        elif command_type in ('find', 'update', 'delete'):
            json_template = command.get('filter', {})
        else:
            json_template = {}

        parameters = command.get('parameters', [])
        # Map all parameter paths in one pass
        param_names = [param.get('name') for param in parameters]
        param_paths_dict = self._map_all_param_paths(json_template, param_names)

        # Generate parameter values
        param_values = {}
        for param in parameters:
            value, _ = DataManager.generate_param_value(param)
            param_values[param.get('name')] = value

        # Replace all parameters in the template
        replaced_json = self._replace_all_params(json_template, param_paths_dict, param_values)

        collection_name = command.get('collection')
        collection = db[collection_name] if collection_name else None

        document = None
        pipeline = None
        if command_type == 'insert':
            document = replaced_json
        elif command_type == 'aggregate':
            pipeline = replaced_json
        elif command_type in ('find', 'update', 'delete'):
            document = replaced_json

        start_time = time.time()
        try:
            result = None
            if command_type == 'insert':
                result = collection.insert_one(document)
                response_length = 1
            elif command_type == 'aggregate':
                cursor = collection.aggregate(pipeline)
                response_length = len(list(cursor))
            elif command_type == 'find':
                cursor = collection.find(document)
                response_length = len(list(cursor))
            #elif command_type == 'update':
            #    update_doc = DataManager.replace_mongo_vars(command_definition.get('update', {}), param_values)
            #    result = collection.update_one(document, update_doc)
            #    response_length = result.modified_count
            elif command_type == 'delete':
                result = collection.delete_one(document)
                response_length = result.deleted_count
            else:
                logging.error(f"Unsupported MongoDB command type: {command_type}")
                return

            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('MongoDBCommand', task_name, total_time, response_length=response_length)
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('MongoDBCommand-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing MongoDB command: {e}")
