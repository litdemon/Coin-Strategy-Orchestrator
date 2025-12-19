from abc import ABC, abstractmethod
from typing import Any

class Tool(ABC):
   
    def identifier(self):
        return self.__class__.__name__.lower()
    
    @abstractmethod
    def execute(self, *args: Any, **kwargs: Any) -> Any:
        """Execute the tool logic."""
        pass

class Resource(ABC):
    def identifier(self):
        name = self.__class__.__name__.lower()
        return f"{name}://{{name}}"
    
    @abstractmethod
    def get(self, *args: Any, **kwargs: Any) -> Any:
        """Retrieve the resource content."""
        pass

class Prompt(ABC):
    def identifier(self):
        return self.__class__.__name__.lower().replace("prompt", "")

    @abstractmethod
    def get(self, *args: Any, **kwargs: Any) -> str:
        """Generate the prompt content."""
        pass
