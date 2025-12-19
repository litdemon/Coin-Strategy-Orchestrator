from project_mcp.base import Resource

class GreetingResource(Resource):
    def get(self, name: str) -> str:
        """Get a personalized greeting resource"""
        return f"Hello, {name}!"
