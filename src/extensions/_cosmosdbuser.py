from locust import User

class CosmosDBUser(User):

    def __init__(self, environment):
        super().__init__(environment)
        self.client = None
        self.db = None