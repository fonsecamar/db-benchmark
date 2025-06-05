from locust import User, events
from locust.runners import MasterRunner, LocalRunner, WorkerRunner
from extensions.sqluser import SQLUser

@events.init_command_line_parser.add_listener
def _(parser):
    parser.add_argument("--server", type=str, env_var="server", is_required=True)
    parser.add_argument("--user", type=str, env_var="user", is_required=True)
    parser.add_argument("--password", type=str, env_var="password", is_required=True, is_secret=True)
    parser.add_argument("--db-name", type=str, env_var="db-name", is_required=True)

@events.init.add_listener
def on_locust_init(environment, **_kwargs):
    if isinstance(environment.runner, WorkerRunner) or isinstance(environment.runner, LocalRunner):
        SQLUser.setup_sqluser()