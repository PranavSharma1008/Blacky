"""
Terminal and code execution tools for BlackyAgent.
Executes shell commands and Python scripts with timeout protection.
"""

import subprocess
import sys
import tempfile
from pathlib import Path
from blacky.config import config
from blacky.tools.base import registry


@registry.register
def run_terminal_command(command: str, timeout_seconds: int = 30) -> str:
    """
    Execute a shell/terminal command on macOS.
    Returns stdout, stderr, and the return code.
    """
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(config.BASE_DIR),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        output = proc.stdout.strip()
        error = proc.stderr.strip()
        code = proc.returncode

        res = f"[Exit Code: {code}]\n"
        if output:
            res += f"STDOUT:\n{output}\n"
        if error:
            res += f"STDERR:\n{error}\n"
        if not output and not error:
            res += "(Command completed with no output)"

        success = (code == 0)
        registry.log_call("run_terminal_command", {"command": command}, f"Exit code {code}", success=success)
        return res
    except subprocess.TimeoutExpired:
        err = f"Command timed out after {timeout_seconds} seconds."
        registry.log_call("run_terminal_command", {"command": command}, err, success=False)
        return err
    except Exception as e:
        err = f"Failed to execute command: {str(e)}"
        registry.log_call("run_terminal_command", {"command": command}, err, success=False)
        return err


@registry.register
def run_python_code(code: str, timeout_seconds: int = 20) -> str:
    """
    Execute a snippet of Python code and return its printed output or errors.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(config.BASE_DIR),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
        output = proc.stdout.strip()
        error = proc.stderr.strip()
        code_exit = proc.returncode

        res = f"[Exit Code: {code_exit}]\n"
        if output:
            res += f"Output:\n{output}\n"
        if error:
            res += f"Error:\n{error}\n"
        if not output and not error:
            res += "(Executed successfully with no output)"

        registry.log_call("run_python_code", {"lines": len(code.splitlines())}, f"Exit code {code_exit}", success=(code_exit == 0))
        return res
    except subprocess.TimeoutExpired:
        err = f"Python execution timed out after {timeout_seconds} seconds."
        registry.log_call("run_python_code", {"code_snippet": code[:50]}, err, success=False)
        return err
    except Exception as e:
        err = f"Execution failed: {str(e)}"
        registry.log_call("run_python_code", {"code_snippet": code[:50]}, err, success=False)
        return err
