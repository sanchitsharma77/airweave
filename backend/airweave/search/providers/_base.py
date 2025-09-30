"""Base provider client."""

# TODO: not implemented by error


class BaseProviderClient:
    def _init_(self, client, api_key, model):
        self.client = client
        self.api_key = api_key
        self.model = model

    def generate(self, messages, stream):
        pass

    def rerank(self):
        pass

    def embed(self):
        pass
