
import inspect
from mcp.server.fastmcp import FastMCP
from project_mcp.tools.command_actions import BuyCommandTool
from project_mcp.base import Tool

# Mocking FastMCP to see what gets registered
class MockMCP:
    def __init__(self):
        self.tools = {}
    def tool(self, name=None):
        def decorator(fn):
            self.tools[name] = fn
            return fn
        return decorator

def test_registration():
    mock_mcp = MockMCP()
    tool = BuyCommandTool()
    
    # Logic from mymcp.py
    fn = getattr(tool, "mcp_execute", None) or tool.execute
    
    # Register
    mock_mcp.tool(name=tool.identifier())(fn)
    
    registered_fn = mock_mcp.tools["buy"]
    print(f"Registered function name: {registered_fn.__name__}")
    
    sig = inspect.signature(registered_fn)
    print(f"Signature: {sig}")
    
    assert registered_fn.__name__ == "mcp_execute"
    assert "ticker" in sig.parameters
    assert "won" in sig.parameters
    print("Registration verification PASSED")

if __name__ == "__main__":
    test_registration()
