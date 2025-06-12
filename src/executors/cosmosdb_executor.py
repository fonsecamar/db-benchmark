import logging
from executors.base_executor import BaseExecutor

class CosmosDBExecutor(BaseExecutor):
    def __init__(self):
        self.cursor = self._connect()

    def _connect(self):
        logging.info("-----> Creating database connection")

    def execute(self, command, parameters):
        pass
