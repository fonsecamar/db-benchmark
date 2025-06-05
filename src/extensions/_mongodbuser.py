from locust import User

class MongoDBUser(User):

    def __init__(self, environment):
        super().__init__(environment)
        self.client = None
        self.db = None