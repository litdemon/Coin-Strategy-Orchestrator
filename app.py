import os
import sys
import time
import logging
import traceback
import argparse
import json
from dotenv import load_dotenv

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.main import Manager

import logging.handlers

def setup_logging(console: bool = True):
    """Initialize logging configuration."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    # Date removed from format, only time
    time_format = "%H:%M:%S"
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    if root_logger.handlers:
        root_logger.handlers = []

    # File Handler - Timed Rotation (Daily at midnight)
    log_file = os.path.join(log_dir, "coin-stratege.log")
    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=log_file,
        when='midnight',
        interval=1, # 1 day
        backupCount=30, # Keep 30 days
        encoding='utf-8'
    )
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=time_format))
    file_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(file_handler)
    
    # Console Handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(logging.Formatter(log_format, datefmt=time_format))
        root_logger.addHandler(console_handler)

def load_config(file_path: str = "default.json") -> dict:
    """Load configuration from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        return config
    except FileNotFoundError:
        # Fallback if file missing (though usually we should fail or warn)
        logging.getLogger(__name__).warning("default.json not found, using minimal defaults")
        return {}

def main():
    parser = argparse.ArgumentParser(description="Coin Strategy Bot")
    parser.add_argument('--config', default='default.json', help='Configuration file path')
    args = parser.parse_args()

    # Setup Logging
    setup_logging(console=False)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Coin Strategy Manager")

    config = load_config(args.config)
    dash_mode = config.get("dashboard", {}).get("mode", "tui")
    manager = Manager(mode=dash_mode)
    
    # Dynamic Client ID if empty
    if not config.get("messaging", {}).get("mqtt", {}).get("client_id"):
        # Ensure structure exists
        if "messaging" not in config: config["messaging"] = {}
        if "mqtt" not in config["messaging"]: config["messaging"]["mqtt"] = {}
        config["messaging"]["mqtt"]["client_id"] = f"strategy_manager_{int(time.time())}"
    
    manager.init(config=config)

    # --- WebSocket Dashboard Server ---
    try:
        from src.ws_server import start_ws_server
        dash_cfg = config.get("dashboard", {})
        _host = dash_cfg.get("host", "127.0.0.1")
        _port = dash_cfg.get("port", 8765)
        _token = dash_cfg.get("token") or os.environ.get("DASHBOARD_TOKEN") or ""
        start_ws_server(
            state_store=manager.dashboard._state_store,
            host=_host,
            port=_port,
            token=_token or None,
            mcp_host=config.get("mcp", {}).get("host", "127.0.0.1"),
            mcp_port=config.get("mcp", {}).get("port", 8000),
        )
        _url = f"http://{_host}:{_port}"
        if _token:
            _url += f"?token={_token}"
        print(f"\n  Dashboard → {_url}\n", flush=True)
    except Exception as e:
        logger.warning(f"WebSocket server failed to start: {e}")
    # ---------------------------------

    # --- MCP Integration ---
    mcp_cfg = config.get("mcp", {})
    mcp_host = mcp_cfg.get("host", "127.0.0.1")
    mcp_port = mcp_cfg.get("port", 8000)
    try:
        from project_mcp.mymcp import initialize_command_context, run_mcp
        from project_mcp.tools.context import CommandExecutionContext
        import threading

        ctx = CommandExecutionContext(
            account_manager=manager.account_manager,
            pocket_manager=manager.pocket_manager,
            strategy_manager=manager.strategy_manager,
            messaging=manager.messaging,
            dashboard=manager.dashboard,
            current_prices=manager.current_prices,
            upbit_websocket=manager.upbit_websocket,
        )
        initialize_command_context(ctx)

        def run_mcp_server():
            try:
                run_mcp(host=mcp_host, port=mcp_port)
            except Exception as e:
                logger.error(f"MCP Server Failed: {e}")

        mcp_thread = threading.Thread(target=run_mcp_server, daemon=True)
        mcp_thread.start()
        print(f"  MCP Server → http://{mcp_host}:{mcp_port}/mcp\n", flush=True)

    except ImportError:
        logger.warning("MCP modules not found. Skipping MCP server startup.")
    except Exception as e:
        logger.error(f"Failed to start MCP Server: {e}")
        logger.error(traceback.format_exc())
    # -----------------------

    # --- /ws/control command handler ---
    try:
        from src.ws_server import set_command_handler
        from project_mcp.tools.strategy_tool import StrategyTool

        _strategy_tool = StrategyTool()

        def _ws_command_handler(cmd: dict) -> dict:
            action = cmd.get("action", "")
            if action == "strategy.create":
                return _strategy_tool.execute(
                    action="create",
                    params={
                        "name": cmd.get("name", "scalping_strategy"),
                        "ticker": cmd.get("ticker", ""),
                        "type": cmd.get("type", "buy"),
                        "budget": str(cmd.get("budget", "0")),
                        "config": cmd.get("config", {}),
                    },
                )
            elif action == "strategy.delete":
                return _strategy_tool.execute(
                    action="delete",
                    params={"strategy_id": cmd.get("strategy_id", "")},
                )
            elif action == "strategy.list":
                return _strategy_tool.execute(action="list", params={})
            elif action == "strategy.list_types":
                return _strategy_tool.execute(action="list_types", params={})
            return {"error": f"Unknown action: {action!r}. Supported: strategy.create, strategy.delete, strategy.list"}

        set_command_handler(_ws_command_handler)
        logger.info("WebSocket control command handler registered")
    except Exception as e:
        logger.warning(f"Failed to register ws command handler: {e}")
    # ------------------------------------

    try:
        while True:
            try:
                manager.run()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logger.error(f"Manager crashed — restarting in 5s: {e}")
                logger.error(traceback.format_exc())
                time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Stopping...")
        manager.stop()

if __name__ == "__main__":
    main()
