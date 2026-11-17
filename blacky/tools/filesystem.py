"""
Filesystem tools for BlackyAgent.
Allows creating folders, writing code, reading files, editing, and listing directories.
"""

import os
import shutil
from pathlib import Path
from blacky.config import config
from blacky.tools.base import registry


def _resolve_path(path_str: str) -> Path:
    """
    Resolve a path relative to macOS special folders (Desktop, Downloads, Documents)
    or the active workspace.
    """
    clean = (path_str or "").strip()
    p = Path(clean).expanduser()
    if p.is_absolute():
        return p

    lower = clean.lower()
    user_home = Path.home()
    if lower.startswith("desktop/") or lower.startswith("desktop\\") or lower == "desktop":
        rel = clean[len("desktop/"):].lstrip("/\\") if (lower.startswith("desktop/") or lower.startswith("desktop\\")) else ""
        return (user_home / "Desktop" / rel).resolve()
    elif lower.startswith("downloads/") or lower.startswith("downloads\\") or lower == "downloads":
        rel = clean[len("downloads/"):].lstrip("/\\") if (lower.startswith("downloads/") or lower.startswith("downloads\\")) else ""
        return (user_home / "Downloads" / rel).resolve()
    elif lower.startswith("documents/") or lower.startswith("documents\\") or lower == "documents":
        rel = clean[len("documents/"):].lstrip("/\\") if (lower.startswith("documents/") or lower.startswith("documents\\")) else ""
        return (user_home / "Documents" / rel).resolve()

    return (config.BASE_DIR / p).resolve()


@registry.register
def create_folder(folder_path: str) -> str:
    """
    Create a new directory/folder at the specified path.
    Creates parent directories if they do not exist.
    """
    try:
        path = _resolve_path(folder_path)
        path.mkdir(parents=True, exist_ok=True)
        res = f"Directory successfully created at: {path}"
        registry.log_call("create_folder", {"folder_path": folder_path}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to create folder '{folder_path}': {str(e)}"
        registry.log_call("create_folder", {"folder_path": folder_path}, err, success=False)
        return err


@registry.register
def write_file(file_path: str, content: str) -> str:
    """
    Write or overwrite code, text, or documentation into a file.
    Creates parent directories automatically if needed.
    """
    try:
        path = _resolve_path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        line_count = len(content.splitlines())
        res = f"Successfully wrote {line_count} lines to {path}"
        registry.log_call("write_file", {"file_path": file_path, "bytes": len(content)}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to write file '{file_path}': {str(e)}"
        registry.log_call("write_file", {"file_path": file_path}, err, success=False)
        return err


@registry.register
def read_file(file_path: str, max_lines: int = 400) -> str:
    """
    Read the contents of a file up to max_lines.
    """
    try:
        path = _resolve_path(file_path)
        if not path.exists():
            return f"Error: File '{file_path}' does not exist."
        if path.is_dir():
            return f"Error: '{file_path}' is a directory, not a file."

        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        truncated = len(lines) > max_lines
        content = "\n".join(lines[:max_lines])
        if truncated:
            content += f"\n... [Truncated {len(lines) - max_lines} more lines]"

        res = f"Read {min(len(lines), max_lines)} lines from {path}:\n\n{content}"
        registry.log_call("read_file", {"file_path": file_path}, f"Read {len(lines)} lines", success=True)
        return res
    except Exception as e:
        err = f"Failed to read file '{file_path}': {str(e)}"
        registry.log_call("read_file", {"file_path": file_path}, err, success=False)
        return err


@registry.register
def edit_file(file_path: str, target_text: str, replacement_text: str) -> str:
    """
    Replace specific text or code inside an existing file.
    """
    try:
        path = _resolve_path(file_path)
        if not path.exists():
            return f"Error: File '{file_path}' does not exist."

        current = path.read_text(encoding="utf-8")
        if target_text not in current:
            return f"Error: Target text not found in '{file_path}'."

        updated = current.replace(target_text, replacement_text, 1)
        path.write_text(updated, encoding="utf-8")
        res = f"Successfully updated '{file_path}'."
        registry.log_call("edit_file", {"file_path": file_path}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to edit file '{file_path}': {str(e)}"
        registry.log_call("edit_file", {"file_path": file_path}, err, success=False)
        return err


@registry.register
def list_directory(directory_path: str = ".") -> str:
    """
    List contents (files and folders) inside a directory.
    """
    try:
        path = _resolve_path(directory_path)
        if not path.exists():
            return f"Error: Directory '{directory_path}' does not exist."
        if not path.is_dir():
            return f"Error: '{directory_path}' is not a directory."

        entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        formatted = []
        for p in entries[:100]:
            prefix = "📁 " if p.is_dir() else "📄 "
            formatted.append(f"{prefix}{p.name}")

        result_str = f"Directory contents of '{path}':\n" + "\n".join(formatted)
        if len(entries) > 100:
            result_str += f"\n... [and {len(entries) - 100} more items]"

        registry.log_call("list_directory", {"directory_path": directory_path}, f"Found {len(entries)} items", success=True)
        return result_str
    except Exception as e:
        err = f"Failed to list directory '{directory_path}': {str(e)}"
        registry.log_call("list_directory", {"directory_path": directory_path}, err, success=False)
        return err


@registry.register
def delete_item(path: str) -> str:
    """
    Delete a file or folder. Use with caution.
    """
    try:
        target = _resolve_path(path)
        if not target.exists():
            return f"Item '{path}' does not exist."

        if target.is_dir():
            shutil.rmtree(target)
            res = f"Deleted directory: {target}"
        else:
            target.unlink()
            res = f"Deleted file: {target}"

        registry.log_call("delete_item", {"path": path}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to delete '{path}': {str(e)}"
        registry.log_call("delete_item", {"path": path}, err, success=False)
        return err
