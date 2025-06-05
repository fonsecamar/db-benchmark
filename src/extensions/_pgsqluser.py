import settings
import time
import pymssql
import logging

from datamanager import DataManager
from locust import User
from pymssql import OperationalError

class PGSQLUser(User):
    connection = None
    cursor = None
    parsedCommands = {}

    @staticmethod
    def setup_sqluser():
        tasks_dict = {}
        for task in settings.init_settings():
            def make_method(task_config):
                def method(self):
                    self.execute(task_config)
                method.__name__ = task_config.taskName
                return method
            method = make_method(task)
            setattr(PGSQLUser, task.taskName, method)
            tasks_dict[getattr(PGSQLUser, task.taskName)] = task.taskWeightPct
        PGSQLUser.tasks = tasks_dict

    def reset_connection(self):
        logging.info("-----> Creating database connection")
        try:
            self.connection = None
            self.cursor = None
            self.connection = pymssql.connect(server=self.environment.parsed_options.server,
                                            user=self.environment.parsed_options.user,
                                            password=self.environment.parsed_options.password,
                                            database=self.environment.parsed_options.db_name,
                                            autocommit=True)
            self.cursor = self.connection.cursor()
        except Exception as e:
            logging.info(f"Connection error occurred: {e}")

    def on_start(self):
        self.reset_connection(self)

    def on_stop(self):
        if self.connection:
            try:
                self.connection.close()
                logging.info("Connection successfully closed!")
            except Exception as e:
                logging.info(f"Error closing connection: {e}")
            finally:
                self.connection = None

    def execute(self, task_config):
        param_values = []
        param_mapping = {}

        if not self.connection or not self.cursor:
            return

        for param in task_config.command.parameters:
            value, placeholder = DataManager.generate_param_value(param)
            param_values.append(value)
            param_mapping[param.name] = placeholder

        if not task_config.taskName in self.parsedCommands:
            self.parsedCommands[task_config.taskName] = DataManager.replace_sql_vars(task_config.command.definition, param_mapping)

        start_time = time.time()
        try:
            with self.connection.cursor(as_dict=True) as cursor:
                cursor.execute(self.parsedCommands[task_config.taskName], tuple(param_values))

            total_time = int((time.time() - start_time) * 1000)
            self.environment.events.request.fire(
                request_type='SQLCommand', name=task_config.taskName, response_time=total_time, response_length=1
            )
        except OperationalError as e:
            total_time = int((time.time() - start_time) * 1000)
            self.environment.events.request.fire(
                request_type='SQLCommand-Error', name=task_config.taskName, response_time=total_time, exception=e, response_length=0,
            )
            self.reset_connection()
        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            self.environment.events.request.fire(
                request_type='SQLCommand-Error', name=task_config.taskName, response_time=total_time, exception=e, response_length=0,
            )
            