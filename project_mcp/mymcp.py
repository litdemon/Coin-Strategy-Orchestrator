import pkgutil
import inspect
import importlib
from mcp.server.fastmcp import FastMCP
from project_mcp.base import Tool, Resource, Prompt
import project_mcp.tools
import project_mcp.resources
import project_mcp.prompts
from typing import Generator, Any, Tuple, Type

# Initialize FastMCP server
mcp = FastMCP("My First MCP Server")

def discover_components(package: Any, base_class: Type) -> Generator[Tuple[str, Type], None, None]:
    """
    Discover components in a package that inherit from a base class.
    
    Args:
        package: The package module to search in.
        base_class: The base class to filter by (Tool, Resource, Prompt).
        
    Yields:
        Tuple[str, Type]: A tuple of (component_name, ComponentClass).
    """
    path = package.__path__
    prefix = package.__name__ + "."

    for _, name, _ in pkgutil.iter_modules(path, prefix):
        module = importlib.import_module(name)
        for _, obj in inspect.getmembers(module):
            if inspect.isclass(obj) and issubclass(obj, base_class) and obj is not base_class:
                # Derive name: AddTool -> add, GreetingResource -> greeting
                class_name = obj.__name__.lower()
                suffix = base_class.__name__.lower()
                component_name = class_name.replace(suffix, "")
                
                yield component_name, obj

# Register Tools
print("--- Registering Tools ---")
for name, ToolClass in discover_components(project_mcp.tools, Tool):
    tool = ToolClass()
    print(f"Registered tool: {name}")
    mcp.tool(name=tool.identifier())(tool.execute)

# Register Resources
print("--- Registering Resources ---")
for name, ResourceClass in discover_components(project_mcp.resources, Resource):
    resource = ResourceClass()
    print(f"Registered resource: {resource.identifier()}")
    
    mcp.resource(resource.identifier())(resource.get)

# Register Prompts
print("--- Registering Prompts ---")
for name, PromptClass in discover_components(project_mcp.prompts, Prompt):
    prompt = PromptClass()
    print(f"Registered prompt: {prompt.identifier()}")
    mcp.prompt(prompt.identifier())(prompt.get)

if __name__ == "__main__":
    # Run the server using stdio
    mcp.run(transport='stdio')
