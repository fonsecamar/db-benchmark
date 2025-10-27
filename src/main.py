from locust import User, events
from locust.runners import MasterRunner, LocalRunner
from executors.sql_executor import SQLExecutor
from executors.pgsql_executor import PGSQLExecutor
from executors.mongodb_executor import MongoDBExecutor
from executors.cosmosdb_executor import CosmosDBExecutor
from executors.cassandra_executor import CassandraExecutor
import settings
from settings import Settings, StartUpFrequency
import logging
from typing import Any, Callable

logging.basicConfig(level=logging.INFO)
all_profiles = settings.init_settings()

@events.init_command_line_parser.add_listener
def _(parser):
    added_types = set()
    for setting in all_profiles:
        load_type = setting.type
        if load_type in added_types:
            continue
        if load_type == "SQL":
            parser.add_argument("--sql-server", type=str, is_required=True, help="Server URI or IP address[:<port>]")
            parser.add_argument("--sql-user", type=str, is_required=True, help="User Name")
            parser.add_argument("--sql-password", type=str, is_required=True, is_secret=True, help="User Password")
            parser.add_argument("--sql-db-name", type=str, is_required=True, help="Database Name")
        elif load_type == "PGSQL":
            parser.add_argument("--pgsql-connection-string", type=str, is_required=True, is_secret=True, help="Format: postgresql://<server_name>.postgres.database.azure.com:<port>/postgres?sslmode=require")
        elif load_type == "MONGODB":
            parser.add_argument("--mongodb-connection-string", type=str, is_required=True, is_secret=True, help="Format: mongodb+srv://<username>:<password>@<cluster-address>/?tls=true&authMechanism=SCRAM-SHA-256&retrywrites=false&maxIdleTimeMS=120000")
        elif load_type == "COSMOSDB":
            parser.add_argument("--cosmosdb-connection-string", type=str, is_required=True, is_secret=True, help="Format: AccountEndpoint=<your-account-endpoint>;AccountKey=<your-account-key>;")
        elif load_type == "CASSANDRA":
            parser.add_argument("--cassandra-contact-points", type=str, is_required=True, help="Comma-separated list - IP addresses or hostnames")
            parser.add_argument("--cassandra-port", type=int, default=9042, is_required=True, help="Default: 9042")
            parser.add_argument("--cassandra-username", type=str, is_required=True, help="User Name")
            parser.add_argument("--cassandra-password", type=str, is_secret=True, is_required=True, help="User Password")
        added_types.add(load_type)

@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    if isinstance(environment.runner, MasterRunner) or isinstance(environment.runner, LocalRunner):
        for uc in environment.user_classes:
            if uc.runStartUp:
                logging.info(f"Running startup for user class: {uc.__name__}")
                uc(environment).run_startup()
            else:
                logging.info(f"Skipping startup for user class: {uc.__name__}")

def get_executor(load_type: str, environment: Any):
    if load_type == "SQL":
        return SQLExecutor(environment)
    elif load_type == "PGSQL":
        return PGSQLExecutor(environment)
    elif load_type == "MONGODB":
        return MongoDBExecutor(environment)
    elif load_type == "COSMOSDB":
        return CosmosDBExecutor(environment)
    elif load_type == "CASSANDRA":
        return CassandraExecutor(environment)
    else:
        logging.error(f"Unsupported type: {load_type}. Supported types are SQL, PGSQL, MONGODB, COSMOSDB, and CASSANDRA.")
        return None

def create_task_function(command, task_name) -> Callable:
    def task_func(self):
        self.executor.execute(command, task_name)
    task_func.__name__ = task_name
    return task_func

def create_user_class(class_name: str, workload_settings: Settings):
    executor_factory = lambda env: get_executor(workload_settings.type, env)

    class DynamicUser(User):

        runStartUp = workload_settings.runStartUpFrequency != StartUpFrequency.NEVER

        def __init__(self, environment, *args, **kwargs):
            super().__init__(environment, *args, **kwargs)
            self.executor = executor_factory(environment)
            self.workload_settings = workload_settings

        def run_startup(self):
            if self.executor and self.__class__.runStartUp:
                self.executor.run_startup(self.workload_settings.workloadName)
                self.__class__.runStartUp = self.workload_settings.runStartUpFrequency == StartUpFrequency.ALWAYS

        def on_stop(self):
            super().on_stop()

            if self.executor:
                try:
                    self.executor._disconnect()
                except Exception as e:
                    logging.error(f"Error disconnecting executor: {e}")

    task_list = []
    for task_def in workload_settings.tasks:
        fullTaskName = f"{workload_settings.workloadName}_{task_def.taskName}"
        func = create_task_function(task_def.command, fullTaskName)
        setattr(DynamicUser, task_def.taskName, func)
        logging.info(f"Adding task {task_def.taskName}:weight {task_def.taskWeight} to user class {class_name}")
        for i in range(task_def.taskWeight):
            task_list.append(func)
    
    DynamicUser.tasks = task_list
    DynamicUser.__name__ = class_name
    return DynamicUser

classes = {}
for setting in all_profiles:
    new_class_name = f"{setting.workloadName.replace('_', '')}_{setting.type}_User"
    logging.info(f"Creating user class: {new_class_name}")
    classes[new_class_name] = create_user_class(new_class_name, setting)

globals().update({cls.__name__: cls for cls in classes.values()})