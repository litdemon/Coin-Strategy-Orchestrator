from project_mcp.base import Tool
import subprocess
import os

class CommitTool(Tool):
    def execute(self, message: str, paths: str = ".") -> str:
        """
        Automatically bumps the version in 'version' file and commits changes.
        
        Args:
            message: The commit message.
            paths: Space-separated list of paths to stage (default: "." for all).
            
        Returns:
            str: Result of the commit operation.
        """
        version_file = "version"
        
        # 1. Read current version
        try:
            with open(version_file, "r") as f:
                current_ver = float(f.read().strip())
        except FileNotFoundError:
            current_ver = 0.0
            
        # 2. Bump version
        new_ver = round(current_ver + 0.1, 1)
        
        # 3. Write new version
        with open(version_file, "w") as f:
            f.write(str(new_ver))
            
        # 4. Git operations
        try:
            # Stage changes
            path_list = paths.split()
            # Always add version file if bumping
            if "version" not in path_list and paths != ".":
                path_list.append("version")
                
            subprocess.run(["git", "add"] + path_list, check=True, capture_output=True)
            
            # Commit
            full_message = f"{message} (v{new_ver})"
            result = subprocess.run(["git", "commit", "-m", full_message], check=True, capture_output=True, text=True)
            
            return f"Success: Committed with version {new_ver}. Output: {result.stdout.strip()}"
            
        except subprocess.CalledProcessError as e:
            return f"Error during git operation: {e.stderr if e.stderr else str(e)}"
        except Exception as e:
            return f"Unexpected error: {str(e)}"
