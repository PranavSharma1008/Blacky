"""
Mobile remote web server for BlackyAgent.
Runs a FastAPI backend and serves the Siri-style mobile web client.
"""

import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn

from blacky.config import config
from blacky.core.agent import BlackyAgent
from blacky.core.ollama_client import OllamaProvider
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


class ScreenChatRequest(BaseModel):
    prompt: str
    target_app: str = ""


class ScreenMcqRequest(BaseModel):
    count: int = 10
    auto_advance: bool = True
    target_app: str = ""


def _is_loopback(host: str | None) -> bool:
    """True for requests that originate on the Mac itself."""
    return (host or "") in ("127.0.0.1", "::1", "localhost")


def _authorize(token: str | None, client_host: str | None) -> None:
    """
    Remote desktop control is powerful: require the configured token for any
    non-local caller. With no token configured, only localhost may command.
    """
    if _is_loopback(client_host):
        return
    if not config.MOBILE_API_TOKEN:
        raise HTTPException(
            status_code=403,
            detail="Remote control is disabled. Set MOBILE_API_TOKEN in .env to allow phone access.",
        )
    if token != config.MOBILE_API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing API token.")


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
async def chat_endpoint(
    req: ChatRequest,
    request: Request,
    x_blacky_token: str | None = Header(default=None),
):
    """Handle chat message from mobile phone or web client."""
    global _agent
    _authorize(x_blacky_token, request.client.host if request.client else None)
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
    """Health check endpoint reporting local model readiness."""
    provider = _agent.provider if _agent else OllamaProvider()
    health = provider.health()
    return {
        "status": "online" if health["connected"] else "degraded",
        "agent": "BlackyAgent",
        "active_model": _agent.active_model if _agent else config.OLLAMA_MODEL,
        "ollama": health,
        "agent_ready": bool(health["connected"] and health["model_available"]),
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
        print_mobile_qr(local_ip, port, public_url=public_url, token=config.MOBILE_API_TOKEN)
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


# ----------------------------------------------------------------------
# Screen-Analysis Mode (local chat window that reads the display)
# ----------------------------------------------------------------------
_screen_agent: BlackyAgent | None = None


def get_screen_agent() -> BlackyAgent:
    global _screen_agent
    if _screen_agent is None:
        _screen_agent = BlackyAgent(speak_replies=False)
    return _screen_agent


def _screen_session():
    from blacky.core.screen_mode import ScreenSession

    def _emit(kind: str, text: str) -> None:
        if kind == "state":
            console.print(f"  [dim]👁  {text}...[/dim]")
        else:
            console.print(f"[bold cyan]{text}[/bold cyan]\n")

    return ScreenSession(provider=get_screen_agent().provider, emit=_emit)


@app.get("/screen", response_class=HTMLResponse)
async def get_screen_index():
    """Serve the screen-analysis chat window."""
    page = STATIC_DIR / "screen.html"
    if not page.exists():
        raise HTTPException(status_code=404, detail="Screen mode UI not found")
    return FileResponse(page)


@app.get("/api/screen/status")
async def screen_status():
    """Vision model readiness for the screen-analysis window."""
    session = _screen_session()
    return {
        **session.status(),
        "agent_ready": get_screen_agent().provider.is_available(),
    }


@app.get("/api/screen/apps")
async def screen_apps():
    """List visible running GUI apps on macOS to populate the Target App dropdown."""
    try:
        cmd = 'tell application "System Events" to get name of every application process whose background only is false'
        out = subprocess.check_output(["osascript", "-e", cmd], text=True, timeout=2.5)
        raw_apps = [a.strip() for a in out.split(",") if a.strip()]
        exclude = {"Terminal", "iTerm2", "Code", "Cursor", "Ollama", "Finder", "Dock", "SystemUIServer", "Blacky"}
        apps = [a for a in raw_apps if a not in exclude]
        return {"apps": apps}
    except Exception:
        return {"apps": ["Google Chrome", "Brave Browser", "Safari", "Preview"]}


@app.get("/api/screen/frame")
async def screen_frame(target_app: str = ""):
    """One live preview frame of the display (base64 JPEG)."""
    from blacky.core.screen_mode import activate_app, capture_screen_base64

    try:
        activate_app(target_app)
        image = capture_screen_base64(target_app)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Screen capture failed: {exc}")
    return {"image": f"data:image/jpeg;base64,{image}" if image else ""}


@app.post("/api/screen/window/hide")
async def screen_window_hide():
    """Hide the companion window into the macOS menu bar."""
    from blacky.web.companion import get_active_companion
    comp = get_active_companion()
    if comp is not None:
        comp.hide_window_sync()
        return {"status": "hidden"}
    return {"status": "no_companion"}


@app.post("/api/screen/window/show")
async def screen_window_show():
    """Show the companion window over the current screen."""
    from blacky.web.companion import get_active_companion
    comp = get_active_companion()
    if comp is not None:
        comp.show_window_sync()
        return {"status": "shown"}
    return {"status": "no_companion"}


@app.post("/api/screen/window/toggle")
async def screen_window_toggle():
    """Toggle visibility of the companion window."""
    from blacky.web.companion import get_active_companion
    comp = get_active_companion()
    if comp is not None:
        comp.toggle_window()
        return {"status": "toggled"}
    return {"status": "no_companion"}


@app.post("/api/screen/chat")
async def screen_chat(req: ScreenChatRequest):
    """Run an instruction from the local companion window."""
    from blacky.core.screen_mode import (
        activate_app,
        extract_question_count,
        format_solved_summary,
        is_mcq_request,
    )

    if not req.prompt or not req.prompt.strip():
        return {"response": "Please provide an instruction.", "tools": []}

    prompt = req.prompt.strip()
    console.print(f"  [bold cyan]💬 Companion command:[/bold cyan] {prompt}")

    try:
        # 1. If it's an MCQ / paper-solving request, activate target app and run solver
        if is_mcq_request(prompt):
            if req.target_app:
                activate_app(req.target_app)
            count = extract_question_count(prompt)
            res = _screen_session().solve_mcqs(count=count, auto_advance=True, target_app=req.target_app)
            return {"response": format_solved_summary(res), "solved": res.get("solved", [])}

        # 2. Check for explicit visual screen inspection requests (e.g. 'analyze screen', 'what is on my screen')
        lowered = prompt.lower()
        screen_intents = (
            "analyze screen", "analyze my screen", "inspect screen", "check screen",
            "what is on my screen", "what's on my screen", "read my screen", "read the screen",
            "explain screen", "explain code on screen", "screen error", "display error",
        )
        if any(si in lowered for si in screen_intents):
            if req.target_app:
                activate_app(req.target_app)
            reply = _screen_session().analyze(instruction=prompt, target_app=req.target_app)
            return {"response": reply}

        # 3. All general and action commands run through the agent loop without limits
        response_text = get_screen_agent().run(prompt)
        recent_tools = registry.get_recent_logs(5)
        return {
            "response": response_text,
            "tools": recent_tools,
        }
    except Exception as exc:
        console.print(f"[red]Companion command error: {exc}[/red]")
        return {"response": f"⚠️ Companion Note: {exc}", "error": str(exc)}


@app.post("/api/screen/mcq")
async def screen_mcq(req: ScreenMcqRequest):
    """Solve visible MCQs one by one (answer → Next → repeat)."""
    from blacky.core.screen_mode import format_solved_summary

    console.print(
        f"  [bold cyan]👁  Solving up to {req.count} MCQ(s)[/bold cyan]"
        f"{' (auto-advance)' if req.auto_advance else ''}"
    )
    try:
        result = _screen_session().solve_mcqs(
            count=req.count,
            auto_advance=req.auto_advance,
            target_app=req.target_app,
        )
        return {
            "response": format_solved_summary(result),
            "solved": result.get("solved", []),
        }
    except Exception as exc:
        console.print(f"[red]MCQ solver error: {exc}[/red]")
        return {"response": f"⚠️ Error solving MCQs: {exc}", "solved": [], "error": str(exc)}


@app.post("/api/screen/mcq/stream")
async def screen_mcq_stream(req: ScreenMcqRequest):
    """Stream live progress of solving MCQs question by question with Server-Sent Events."""
    import queue
    import json
    from blacky.core.screen_mode import format_solved_summary

    q: queue.Queue[dict[str, Any] | None] = queue.Queue()

    def _worker():
        session = ScreenSession(
            provider=get_screen_agent().provider,
            emit=lambda kind, text: q.put({"kind": kind, "text": text}),
        )
        try:
            result = session.solve_mcqs(
                count=req.count,
                auto_advance=req.auto_advance,
                target_app=req.target_app,
                on_question_solved=lambda record: q.put({"kind": "question", "record": record}),
            )
            q.put({"kind": "done", "result": result, "response": format_solved_summary(result)})
        except Exception as e:
            q.put({"kind": "error", "message": str(e)})
        finally:
            q.put(None)

    threading.Thread(target=_worker, daemon=True).start()

    async def event_generator():
        while True:
            try:
                item = q.get(timeout=45.0)
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield f"data: {json.dumps({'kind': 'ping'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


_screen_server_instance: uvicorn.Server | None = None
_screen_server_thread: threading.Thread | None = None


def ensure_screen_mode_active(port: int | None = None) -> bool:
    """Ensure the screen server is running and open the companion window."""
    global _screen_server_instance, _screen_server_thread
    port = port or config.SCREEN_SERVER_PORT
    url = f"http://127.0.0.1:{port}/api/screen/status"

    running = False
    try:
        with urllib.request.urlopen(url, timeout=0.8):
            running = True
    except Exception:
        running = False

    if not running:
        cfg = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
        _screen_server_instance = uvicorn.Server(cfg)
        _screen_server_thread = threading.Thread(target=_screen_server_instance.run, daemon=True)
        _screen_server_thread.start()

    # If native companion is already running, show it directly
    try:
        from blacky.web.companion import get_active_companion
        comp = get_active_companion()
        if comp is not None:
            comp.show_window_sync()
            return True
    except Exception:
        pass

    threading.Thread(target=_open_screen_window, args=(port,), daemon=True).start()
    return True


def _open_screen_window(port: int, timeout: float = 20.0) -> None:
    """Open the screen companion window (small movable chatbot over the screen)."""
    url = f"http://127.0.0.1:{port}/screen"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                break
        except Exception:
            time.sleep(0.3)

    # Check if native companion is already active
    try:
        from blacky.web.companion import get_active_companion
        comp = get_active_companion()
        if comp is not None:
            comp.show_window_sync()
            return
    except Exception:
        pass

    # Fallback to compact Chrome/Brave app window (compact 400x640 at top-right of screen)
    chrome_app = Path("/Applications/Google Chrome.app")
    brave_app = Path("/Applications/Brave Browser.app")
    edge_app = Path("/Applications/Microsoft Edge.app")
    try:
        if chrome_app.exists():
            subprocess.Popen(
                ["open", "-na", "Google Chrome", "--args", f"--app={url}", "--window-size=400,640", "--window-position=950,50"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif brave_app.exists():
            subprocess.Popen(
                ["open", "-na", "Brave Browser", "--args", f"--app={url}", "--window-size=400,640", "--window-position=950,50"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        elif edge_app.exists():
            subprocess.Popen(
                ["open", "-na", "Microsoft Edge", "--args", f"--app={url}", "--window-size=400,640", "--window-position=950,50"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.Popen(["open", url])
    except Exception:
        console.print(f"[dim]Open {url} in your browser for screen analysis mode.[/dim]")


def run_screen_mode(port: int | None = None) -> None:
    """Launch the screen companion (menu bar item + floating movable chatbot)."""
    port = port or config.SCREEN_SERVER_PORT
    session = _screen_session()

    console.print("\n[bold cyan]👁  Blacky Screen Companion[/bold cyan]")
    if session.status()["ready"]:
        console.print(f"[green]✓ Vision ready:[/green] {session.provider.vision_model}")
    else:
        console.print(f"[yellow]⚠ {session.vision_detail}[/yellow]")
    console.print(
        "[dim]Status bar item added to your macOS Menu Bar. "
        "Click it anytime to toggle the floating chatbot companion over your screen.[/dim]\n"
    )

    # 1. Start uvicorn server in a background daemon thread
    global _screen_server_instance, _screen_server_thread
    cfg = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="warning")
    _screen_server_instance = uvicorn.Server(cfg)
    _screen_server_thread = threading.Thread(target=_screen_server_instance.run, daemon=True)
    _screen_server_thread.start()

    # Wait for local server
    url = f"http://127.0.0.1:{port}/api/screen/status"
    for _ in range(30):
        try:
            with urllib.request.urlopen(url, timeout=0.5):
                break
        except Exception:
            time.sleep(0.1)

    # 2. Start Native macOS Menu Bar + Floating WKWebView Companion on the main thread
    try:
        from blacky.web.companion import BlackyScreenCompanion
        comp = BlackyScreenCompanion(port=port)
        if comp.initialize():
            console.print("[green]✓ Blacky Screen Companion is active in your macOS Menu Bar![/green]")
            console.print("[dim]Drag the chatbot window anywhere. Click the menu bar icon to toggle.[/dim]")
            comp.run()
            return
    except Exception as exc:
        console.print(f"[yellow]Note: Native menu bar app fell back to browser window ({exc})[/yellow]")

    # 3. Fallback to Chrome / Browser if Cocoa is unavailable
    _open_screen_window(port)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Screen mode closed.[/dim]")
