"""
Mobile remote web server for BlackyAgent.
Runs a FastAPI backend and serves the Siri-style mobile web client.
"""

import re
import shutil
import socket
import subprocess
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from blacky.config import config
from blacky.core.agent import BlackyAgent
from blacky.tools import registry
from blacky.ui.console import print_mobile_qr, console

app = FastAPI(title="BlackyAgent Mobile Remote")

# Allow CORS for mobile web requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_agent: BlackyAgent | None = None
STATIC_DIR = Path(__file__).resolve().parent / "static"


class ChatRequest(BaseModel):
    prompt: str


def get_local_ip() -> str:
    """Detect local WiFi / LAN IP address on macOS."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.get("/", response_class=HTMLResponse)
async def get_index():
    """Serve the mobile remote web application."""
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Index file not found")
    console.print("  [bold green]📱 Mobile device opened the Web Controller![/bold green]")
    return FileResponse(index_file)


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """Handle chat message from mobile phone or web client."""
    global _agent
    if _agent is None:
        _agent = BlackyAgent(speak_replies=False)

    if not req.prompt or not req.prompt.strip():
        return {"response": "Please provide a command.", "tools": []}

    console.print(f"  [bold cyan]📱 Command from Mobile:[/bold cyan] {req.prompt}")
    response_text = _agent.run(req.prompt)
    recent_tools = registry.get_recent_logs(5)

    return {
        "response": response_text,
        "tools": recent_tools,
    }


@app.get("/api/status")
async def status_endpoint():
    """Health check endpoint."""
    return {
        "status": "online",
        "agent": "BlackyAgent",
        "active_model": _agent.active_model if _agent else config.GEMINI_MODEL,
    }


def start_tunnel(port: int) -> tuple[subprocess.Popen | None, str | None]:
    """Start cloudflared tunnel to expose port over public HTTPS (TryCloudflare)."""
    bin_path = shutil.which("cloudflared")
    if not bin_path:
        return None, None

    try:
        proc = subprocess.Popen(
            [bin_path, "tunnel", "--url", f"http://127.0.0.1:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        tunnel_url = None
        start_time = time.time()
        # Scan initial logs for the public trycloudflare.com URL
        while time.time() - start_time < 6:
            line = proc.stdout.readline()
            if not line and proc.poll() is not None:
                break
            match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
            if match:
                tunnel_url = match.group(0)
                break
        return proc, tunnel_url
    except Exception:
        return None, None


def run_server(host: str | None = None, port: int | None = None) -> None:
    """Launch the mobile web server."""
    global _agent
    _agent = BlackyAgent(speak_replies=False)

    host = host or config.MOBILE_SERVER_HOST
    port = port or config.MOBILE_SERVER_PORT
    local_ip = get_local_ip()

    tunnel_proc, public_url = start_tunnel(port)
    try:
        print_mobile_qr(local_ip, port, public_url=public_url)
        console.print(f"[bold green]✓ Server is LIVE and listening on all interfaces ({host}:{port}).[/bold green]")
        if public_url:
            console.print(f"[bold green]✓ Public tunnel ready:[/bold green] [cyan]{public_url}[/cyan] [dim](Works on 5G mobile data / anywhere)[/dim]")
        else:
            console.print(f"[dim]Note: Make sure your phone is connected to the same Wi-Fi network as this Mac.[/dim]")
        console.print(f"[dim]Press [Ctrl+C] anytime to stop the server.\n[/dim]")

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info",
        )
    finally:
        if tunnel_proc:
            try:
                tunnel_proc.terminate()
                tunnel_proc.wait(timeout=2)
            except Exception:
                tunnel_proc.kill()
