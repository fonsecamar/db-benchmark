import pymssql
import logging
import time
from executors.base_executor import BaseExecutor
from datamanager import DataManager
from pymssql import OperationalError

class SQLExecutor(BaseExecutor):
    def __init__(self, environment, workload_name):
        super().__init__(environment, workload_name)
        self.connection = None
        self._connect()

    def _connect(self):
        try:
            self.connection = pymssql.connect(
                server=self.environment.parsed_options.sql_server,
                user=self.environment.parsed_options.sql_user,
                password=self.environment.parsed_options.sql_password,
                database=self.environment.parsed_options.sql_db_name,
                autocommit=True
            )
        except Exception as e:
            logging.exception(f"Connection error occurred: {e}")
            self.connection = None

    def execute(self, command, task_name):
        if self.connection is None:
            logging.error("No database connection available. Attempting to reconnect.")
            self._connect()
            if self.connection is None:
                logging.error("Reconnection failed.")
                return

        param_values = []
        param_mapping = {}
        for param in command.get('parameters'):
            value, placeholder = DataManager.generate_param_value(param)
            param_values.append(value)
            param_mapping[param.get('name')] = placeholder

        if task_name not in self.parsedCommands:
            self.parsedCommands[task_name] = self._replace_string_params(command.get('definition'), param_mapping)

        start_time = time.time()
        try:
            with self.connection.cursor(as_dict=True) as cursor:
                cursor.execute(self.parsedCommands[task_name], tuple(param_values))
            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('SQLCommand', task_name, total_time, response_length=1)
        except OperationalError as e:
            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('SQLCommand-Error', task_name, total_time, exception=e)
            logging.exception(f"Operational error executing command: {e}")
            self.reset_connection()
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            self._fire_event('SQLCommand-Error', task_name, total_time, exception=e)
            logging.exception(f"Error executing command: {e}")