"""
Web search, scraping, and browser automation tools for BlackyAgent.
"""

import urllib.parse
import subprocess
import time
import re
from pathlib import Path
import requests
from bs4 import BeautifulSoup
from blacky.tools.base import registry


@registry.register
def search_web(query: str, max_results: int = 5) -> str:
    """
    Search the live web using DuckDuckGo.
    Returns titles, snippets, and source URLs.
    """
    import warnings
    warnings.filterwarnings("ignore")
    try:
        try:
            from ddgs import DDGS
        except ImportError:
            from duckduckgo_search import DDGS

        ddgs = DDGS()
        results = list(ddgs.text(query, max_results=max_results))

        if not results:
            res = f"No web search results found for: '{query}'"
            registry.log_call("search_web", {"query": query}, res, success=True)
            return res

        formatted = []
        for i, item in enumerate(results, 1):
            title = item.get("title", "No Title")
            body = item.get("body", "")
            href = item.get("href", "")
            formatted.append(f"{i}. {title}\n   URL: {href}\n   Snippet: {body}\n")

        res_str = f"Web Search Results for '{query}':\n\n" + "\n".join(formatted)
        registry.log_call("search_web", {"query": query}, f"Found {len(results)} results", success=True)
        return res_str
    except Exception as e:
        err = f"Web search failed: {str(e)}"
        registry.log_call("search_web", {"query": query}, err, success=False)
        return err


@registry.register
def fetch_webpage(url: str, max_chars: int = 4000) -> str:
    """
    Fetch and extract clean readable text/articles from a webpage URL.
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=12)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # Strip scripts, stylesheets, and meta elements
        for element in soup(["script", "style", "nav", "footer", "header", "noscript"]):
            element.extract()

        text = soup.get_text(separator=" ", strip=True)
        text = " ".join(text.split())

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [Truncated {len(text) - max_chars} characters]"

        res = f"Content extracted from {url}:\n\n{text}"
        registry.log_call("fetch_webpage", {"url": url}, f"Extracted {len(text)} chars", success=True)
        return res
    except Exception as e:
        err = f"Failed to fetch webpage '{url}': {str(e)}"
        registry.log_call("fetch_webpage", {"url": url}, err, success=False)
        return err


def get_default_browser() -> str:
    """Detect the single system default browser on macOS, returning its application name (e.g. 'Brave Browser')."""
    try:
        res = subprocess.run(
            [
                "osascript",
                "-l",
                "JavaScript",
                "-e",
                'ObjC.import("AppKit"); $.NSWorkspace.sharedWorkspace.URLForApplicationToOpenURL($.NSURL.URLWithString("https://google.com")).path.js',
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        path = res.stdout.strip()
        if "Brave" in path:
            return "Brave Browser"
        if "Chrome" in path:
            return "Google Chrome"
        if "Safari" in path:
            return "Safari"
        if "Firefox" in path:
            return "Firefox"
        if "Edge" in path:
            return "Microsoft Edge"
        if "Arc" in path:
            return "Arc"
    except Exception:
        pass
    return "Brave Browser"


def _resolve_browser_app(browser: str = "") -> str:
    """
    Resolve target browser application name. If an explicit browser was specified
    (e.g. 'Brave Browser', 'Google Chrome', 'Safari'), respect it.
    Otherwise default to the macOS system default browser.
    """
    if browser:
        b_lower = browser.lower()
        if "brave" in b_lower:
            return "Brave Browser"
        if "chrome" in b_lower:
            return "Google Chrome"
        if "safari" in b_lower:
            return "Safari"
        if "firefox" in b_lower:
            return "Firefox"
        if "edge" in b_lower:
            return "Microsoft Edge"
        if "arc" in b_lower:
            return "Arc"
    return get_default_browser()


def get_user_github_info() -> dict[str, str]:
    """Retrieve the owner's GitHub username and repository from git config / git remote or environment."""
    info = {"user": "PranavSharma1008", "repo": "Blacky"}
    try:
        res_user = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True, timeout=1)
        if res_user.returncode == 0 and res_user.stdout.strip():
            info["user"] = res_user.stdout.strip()
    except Exception:
        pass
    try:
        res_remote = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True, timeout=1)
        if res_remote.returncode == 0 and res_remote.stdout.strip():
            m = re.search(r'github\.com[/:]([a-zA-Z0-9_\-]+)/([a-zA-Z0-9_\-]+?)(?:\.git)?$', res_remote.stdout.strip())
            if m:
                info["user"] = m.group(1)
                info["repo"] = m.group(2)
    except Exception:
        pass
    return info


def _bring_site_to_front(site_domain: str, browser_app: str = "") -> bool:
    """
    Check if a website matching site_domain (e.g. 'blinkit.com', 'youtube.com', 'amazon.', 'flipkart.com')
    is already open in any window/tab of the browser.
    If open, brings that specific window to front across macOS spaces, activates the tab, enters full screen, and returns True.
    """
    from blacky.tools.macos import make_window_fullscreen
    target_app = browser_app or get_default_browser()

    clean_domain = site_domain.lower().strip()
    clean_domain = re.sub(r'^https?://', '', clean_domain)
    clean_domain = clean_domain.split('/')[0]
    if clean_domain.startswith("www."):
        clean_domain = clean_domain[4:]
    if not clean_domain:
        clean_domain = site_domain.strip()

    if target_app in ("Google Chrome", "Brave Browser"):
        script = f'''
        set winTitle to ""
        tell application "{target_app}"
            activate
            repeat with w_idx from 1 to (count of windows)
                set w to window w_idx
                repeat with i from 1 to (count of tabs of w)
                    if (URL of tab i of w as string) contains "{clean_domain}" then
                        set index of w to 1
                        set active tab index of w to i
                        set winTitle to (title of tab i of w as string)
                        exit repeat
                    end if
                end repeat
                if winTitle is not "" then exit repeat
            end repeat
        end tell

        -- Bring the window to the front across macOS Spaces using the application Window menu
        tell application "System Events"
            tell process "{target_app}"
                set frontmost to true
                try
                    set wMenu to menu 1 of menu bar item "Window" of menu bar 1
                    repeat with mi in (menu items of wMenu)
                        try
                            set n to (name of mi as string)
                            if n contains "{clean_domain}" or (winTitle is not "" and n contains winTitle) then
                                click mi
                                exit repeat
                            end if
                        end try
                    end repeat
                end try
            end tell
        end tell

        if winTitle is not "" then
            return "found"
        else
            return "not_found"
        end if
        '''
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip() == "found":
                time.sleep(0.4)
                make_window_fullscreen(target_app)
                return True
        except Exception:
            pass
    elif target_app == "Safari":
        script = f'''
        set winTitle to ""
        tell application "Safari"
            activate
            repeat with w_idx from 1 to (count of windows)
                set w to window w_idx
                repeat with t in (tabs of w)
                    if (URL of t as string) contains "{clean_domain}" then
                        set index of w to 1
                        set current tab of w to t
                        set winTitle to (name of t as string)
                        exit repeat
                    end if
                end repeat
                if winTitle is not "" then exit repeat
            end repeat
        end tell

        tell application "System Events"
            tell process "Safari"
                set frontmost to true
                try
                    set wMenu to menu 1 of menu bar item "Window" of menu bar 1
                    repeat with mi in (menu items of wMenu)
                        try
                            set n to (name of mi as string)
                            if n contains "{clean_domain}" or (winTitle is not "" and n contains winTitle) then
                                click mi
                                exit repeat
                            end if
                        end try
                    end repeat
                end try
            end tell
        end tell

        if winTitle is not "" then
            return "found"
        else
            return "not_found"
        end if
        '''
        try:
            res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=3)
            if res.returncode == 0 and res.stdout.strip() == "found":
                time.sleep(0.4)
                make_window_fullscreen(target_app)
                return True
        except Exception:
            pass

    return False


def find_in_page_search_bar(ocr_text: str, site: str = "", scale: float = 1.0) -> tuple[int, int]:
    """
    Locate the in-page search input box from screen OCR lines.
    Returns (lx, ly) in logical coordinates for clicking into the search input.
    """
    lines = []
    for l in ocr_text.splitlines():
        if "->" in l:
            coords, text = l.split("->", 1)
            text = text.strip()
            m = re.match(r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]", coords.strip())
            if m:
                px, py, pw, ph = map(int, m.groups())
                lines.append({"text": text, "px": px, "py": py, "pw": pw, "ph": ph})

    site_lower = site.lower().strip()
    candidates = []

    for it in lines:
        # Search bars in web applications are located in the top navigation header
        if int(15 * scale) <= it["py"] <= int(115 * scale):
            # Exclude extreme left (logos/hamburger menu) and extreme right (profile/cart)
            if int(200 * scale) <= it["px"] <= int(1100 * scale):
                score = 0
                t_lower = it["text"].lower()
                if "search" in t_lower:
                    score += 60
                if any(w in t_lower for w in ["bread", "milk", "coke", "angles", "products", "brands", "items", "grocery"]):
                    score += 40
                if len(it["text"]) >= 2:
                    score += 10
                candidates.append((score, it))

    if candidates:
        candidates.sort(key=lambda x: -x[0])
        best = candidates[0][1]
        lx = int((best["px"] + best["pw"] / 2) / scale)
        ly = int((best["py"] + best["ph"] / 2) / scale)
        return lx, ly

    # Verified fallback defaults if OCR didn't catch the placeholder
    defaults = {
        "blinkit": (530, 44),
        "youtube": (600, 35),
        "amazon": (550, 48),
        "flipkart": (500, 42),
    }
    for k, coords in defaults.items():
        if k in site_lower:
            return coords
    return 520, 44


def execute_in_page_search(query: str, site: str, browser_app: str = "") -> bool:
    """
    Perform search inside the currently open web page using the in-page search bar.
    Avoids full-page reloads, tab duplication, and unnecessary HTTP navigation.
    """
    from blacky.tools.macos import mouse_click, press_key, type_text, capture_display_screen, make_window_fullscreen
    from pathlib import Path

    target_app = browser_app or get_default_browser() or "Brave Browser"

    # 1. Bring browser window and target site to front
    domain_map = {
        "blinkit": "blinkit.com",
        "youtube": "youtube.com",
        "amazon": "amazon.",
        "flipkart": "flipkart.com",
    }
    domain = domain_map.get(site.lower().strip(), "")
    if domain:
        _bring_site_to_front(domain, target_app)
    else:
        subprocess.run(["osascript", "-e", f'tell application "{target_app}" to activate'])

    time.sleep(0.08)
    make_window_fullscreen(target_app)

    # 2. Capture screen to locate search bar using direct hardware JPEG
    shot_path = "/tmp/blacky_inpage_search.jpg"
    disp = capture_display_screen(shot_path, app_name=target_app, target_site=site)
    scale = disp["scale"]
    origin_x = disp["origin_x"]
    origin_y = disp["origin_y"]

    ocr_bin = Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
    if not ocr_bin.exists():
        ocr_bin = Path("/tmp/ocr_fast")

    ocr_text = ""
    if ocr_bin.exists():
        try:
            ocr_text = subprocess.check_output([str(ocr_bin), shot_path], text=True)
        except Exception:
            pass

    lx, ly = find_in_page_search_bar(ocr_text, site=site, scale=scale)
    click_x = int(origin_x + lx)
    click_y = int(origin_y + ly)

    # 3. Click search bar and submit query via single-transaction AppleScript
    mouse_click(click_x, click_y)
    time.sleep(0.08)

    # Fast single-transaction text replacement via pbcopy and atomic osascript
    p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    p.communicate(query.strip().encode("utf-8"))

    script = '''
    tell application "System Events"
        keystroke "a" using {command down}
        key code 51
        keystroke "v" using {command down}
        key code 36
    end tell
    '''
    subprocess.run(["osascript", "-e", script], timeout=2)
    time.sleep(0.35)
    return True


def _open_url_in_browser_app(url: str, browser_app: str | None = None, new_tab: bool = False) -> bool:
    """
    Open URL in the single system default browser and ensure Entire Screen (Full Screen) mode on macOS.
    If new_tab is False and the website/domain is already open in an existing tab:
      - Reuses and activates that tab/window in full screen without creating a duplicate tab (returns False).
    If new_tab is True or the site is not currently open:
      - Opens the URL in a brand new tab in full screen (returns True).
    """
    from blacky.tools.macos import make_window_fullscreen

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    target_app = browser_app or get_default_browser() or "Brave Browser"

    # If new_tab is not explicitly requested, check if the website is already open in an existing tab
    if not new_tab:
        try:
            parsed = urllib.parse.urlparse(url)
            netloc = (parsed.netloc or "").lower().strip()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            if netloc and _bring_site_to_front(netloc, target_app):
                # If the requested URL has a specific path/query, ensure the tab navigates to it
                if parsed.path and parsed.path not in ("", "/"):
                    clean_path = parsed.path.rstrip("/")
                    if target_app in ("Google Chrome", "Brave Browser"):
                        nav_script = f'''
                        tell application "{target_app}"
                            set curr to URL of active tab of front window as string
                            if curr does not contain "{clean_path}" then
                                set URL of active tab of front window to "{url}"
                            end if
                        end tell
                        '''
                        subprocess.run(["osascript", "-e", nav_script], capture_output=True, timeout=3)
                    elif target_app == "Safari":
                        nav_script = f'''
                        tell application "Safari"
                            set curr to URL of current tab of front window as string
                            if curr does not contain "{clean_path}" then
                                set URL of current tab of front window to "{url}"
                            end if
                        end tell
                        '''
                        subprocess.run(["osascript", "-e", nav_script], capture_output=True, timeout=3)
                time.sleep(0.3)
                make_window_fullscreen(target_app)
                return False
        except Exception:
            pass

    # Use specialized AppleScript for Chrome, Brave, Safari to make a brand new tab
    if target_app in ("Google Chrome", "Brave Browser"):
        script = f'''
        tell application "{target_app}"
            activate
            if (count of windows) is 0 then
                make new window
                set URL of active tab of window 1 to "{url}"
            else
                tell window 1
                    make new tab with properties {{URL:"{url}"}}
                    set active tab index to (count of tabs)
                end tell
            end if
        end tell
        '''
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if proc.returncode != 0:
            subprocess.run(["open", "-a", target_app, url], check=True)
    elif target_app == "Safari":
        script = f'''
        tell application "Safari"
            activate
            if (count of windows) is 0 then
                make new document with properties {{URL:"{url}"}}
            else
                tell window 1
                    set current tab to (make new tab with properties {{URL:"{url}"}})
                end tell
            end if
        end tell
        '''
        proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if proc.returncode != 0:
            subprocess.run(["open", "-a", "Safari", url], check=True)
    else:
        subprocess.run(["open", "-a", target_app, url], check=True)

    # ALWAYS ensure browser window is in Entire Screen (Full Screen) mode
    time.sleep(0.4)
    make_window_fullscreen(target_app)
    return True


def _parse_ocr_lines(ocr_text: str) -> list[dict]:
    """
    Parse OCR output lines of the form: "[x, y, w, h] -> text"
    into structured dicts with coordinates.
    """
    lines = []
    for line in ocr_text.splitlines():
        if "->" not in line:
            continue
        coords, text = line.split("->", 1)
        text = text.strip()
        m = re.match(r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]", coords.strip())
        if not m:
            continue
        px, py, pw, ph = map(int, m.groups())
        lines.append({"text": text, "px": px, "py": py, "pw": pw, "ph": ph})
    return lines


def _collect_visible_search_results(browser_app: str, site: str) -> str:
    """
    Capture the live screen and OCR the visible results after a search,
    returning a formatted result list and an ambiguity notice when multiple
    candidate results are visible.
    """
    shot_path = "/tmp/blacky_search_results.png"
    lines: list[dict] = []
    try:
        from blacky.tools.macos import capture_display_screen
        from pathlib import Path as _Path

        ocr_bin = _Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
        if not ocr_bin.exists():
            ocr_bin = _Path("/tmp/ocr_fast")
        if not ocr_bin.exists():
            return ""

        disp = capture_display_screen(shot_path, app_name=browser_app, target_site=site or None)
        scale = disp.get("scale") or 1.0
        out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
        lines = _parse_ocr_lines(out)
    except Exception:
        lines = []

    # Filter out obvious UI chrome lines (nav bars, counts, etc.)
    filtered: list[dict] = []
    skip_tokens = ("min", "mins", "sec", "ago", "views", "subscriber", "subscribers", "http", "www.", "com", "inr")
    for l in lines:
        t = l["text"].strip().lower()
        is_chrome = t in skip_tokens or any(t.startswith(s + " ") for s in skip_tokens)
        if is_chrome or len(t) < 3 or t.startswith("http"):
            continue
        filtered.append(l)

    if not filtered:
        return ""

    formatted = "\n".join(f"{i}. {l['text']}" for i, l in enumerate(filtered[:12], 1))
    res = f"\n\nSEARCH RESULTS (visible matches on screen):\n{formatted}"
    if len(filtered) > 1:
        res += "\nAMBIGUOUS: Multiple possible results matched the search. Present the options to the user and ASK which one they want before selecting any product or performing any next action."
    return res


@registry.register
def open_in_browser(url: str, browser: str = "", new_tab: bool = False) -> str:
    """
    Open any website or URL directly in a web browser on macOS.
    If the website is already open in an existing tab, brings it to front without opening a duplicate tab.
    Args:
        url: Web address to open (e.g. 'https://blinkit.com', 'https://amazon.in').
        browser: Optional target browser: 'Google Chrome' (or 'chrome'), 'Brave Browser' (or 'brave'), 'Safari', or leave empty for default.
        new_tab: Force opening in a new tab even if the site is already open.
    """
    try:
        resolved_browser = _resolve_browser_app(browser)
        opened_new = _open_url_in_browser_app(url, resolved_browser, new_tab=new_tab)
        browser_desc = f"in {resolved_browser}" if resolved_browser else "in default browser"
        if opened_new:
            res = f"Opened {url} {browser_desc} in full screen."
        else:
            res = f"{url} is already open {browser_desc} (brought to front in full screen)."
        registry.log_call("open_in_browser", {"url": url, "browser": browser, "new_tab": new_tab}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to open browser: {str(e)}"
        registry.log_call("open_in_browser", {"url": url, "browser": browser, "new_tab": new_tab}, err, success=False)
        return err


@registry.register
def browser_search(query: str, site: str = "", browser: str = "", new_tab: bool = False) -> str:
    """
    Search for items, products, videos, or queries in the browser WITHOUT adding anything to cart.
    CRITICAL INTENT RULE: ALWAYS invoke this tool when the user asks to 'search', 'find', or 'look for' something
    (e.g. 'search the diet coke in blinkit', 'search boat headphones on amazon', 'search for milk').
    Displays the search results on screen. NEVER clicks ADD or modifies the shopping cart.
    Args:
        query: Search term (e.g. 'diet coke', 'boat headphones', 'milk').
        site: Specific website ('blinkit', 'amazon', 'youtube', 'google', 'flipkart') or empty for Google.
        browser: Target browser (leave empty for system default browser).
        new_tab: Force opening in a new tab even if the site is already open.
    """
    try:
        resolved_browser = _resolve_browser_app(browser)
        site_lower = site.lower().strip()
        query_raw = query.strip()

        # Infer site if not provided explicitly but mentioned in query (e.g. 'in blinkit', 'on amazon')
        if not site_lower:
            for s_key in ("blinkit", "grofers", "amazon", "youtube", "flipkart"):
                if re.search(rf'\b(in|on|at)\s+(the\s+)?{s_key}\b', query_raw, flags=re.IGNORECASE):
                    site_lower = s_key
                    break

        # Clean conversational filler phrases and website name from search query
        clean_query = query_raw
        clean_query = re.sub(r'^(search|find|look for|show me)\s+(for\s+)?(the\s+|a\s+)?', '', clean_query, flags=re.IGNORECASE).strip()
        clean_query = re.sub(r'\s+(in|on|at)\s+(the\s+)?(blinkit|blanket|amazon|youtube|google|flipkart)\b.*', '', clean_query, flags=re.IGNORECASE).strip()
        if not clean_query:
            clean_query = query_raw

        # If Blinkit is requested, check if Blinkit is already open to use in-page search
        if site_lower in ("blinkit", "grofers") and not new_tab:
            if _bring_site_to_front("blinkit.com", resolved_browser):
                execute_in_page_search(query=clean_query, site="blinkit", browser_app=resolved_browser)
                browser_desc = f"in {resolved_browser}" if resolved_browser else "in default browser"
                res = f"Searched Blinkit for '{clean_query}' {browser_desc} (reused active tab in full screen)."
                res += _collect_visible_search_results(resolved_browser, site_lower)
                registry.log_call("browser_search", {"query": query, "site": site, "browser": browser, "new_tab": new_tab}, res, success=True)
                return res

        encoded_query = urllib.parse.quote_plus(clean_query)
        if site_lower in ("amazon", "amazon.in", "amazon.com"):
            target_url = f"https://www.amazon.in/s?k={encoded_query}"
        elif site_lower in ("youtube", "yt"):
            target_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        elif site_lower in ("blinkit", "grofers"):
            target_url = f"https://blinkit.com/s/?q={encoded_query}"
        elif site_lower in ("flipkart", "fk"):
            target_url = f"https://www.flipkart.com/search?q={encoded_query}"
        elif site_lower in ("leetcode", "lc") or "leetcode" in query.lower():
            p_clean = re.sub(r'^(search|find|look for|show me|open|solve|submit)\s+(for\s+)?(the\s+|a\s+)?', '', clean_query, flags=re.I).strip()
            p_clean = re.sub(r'\s+(in|on|at)\s+(the\s+)?(leetcode|lc)\b.*', '', p_clean, flags=re.I).strip()
            p_clean = re.sub(r'\s+(ques|question|problem|code|solution)\b.*', '', p_clean, flags=re.I).strip()
            slug = re.sub(r'[^a-zA-Z0-9]+', '-', p_clean).strip('-').lower()
            if slug and len(slug) >= 2:
                target_url = f"https://leetcode.com/problems/{slug}/"
            else:
                target_url = f"https://leetcode.com/problemset/all/?search={encoded_query}"
        elif site_lower in ("github", "gh") or "repo" in query.lower():
            q_clean = query.lower().strip()
            gh_info = get_user_github_info()
            if any(k in q_clean for k in ("blacky", "balcky", "blackie", "blacki", "agent")):
                target_url = f"https://github.com/{gh_info['user']}/{gh_info['repo']}"
            else:
                from blacky.tools.macos import get_screen_context
                ctx = get_screen_context()
                gh_user = ctx.get("github_user") or gh_info["user"]
                # Extract repo name from query (e.g. "open foo repo" -> "foo")
                repo_words = [w for w in re.sub(r'[^a-zA-Z0-9_\-\s]', '', query).split() if w.lower() not in ("open", "the", "repo", "repository", "name", "named", "is", "my", "out", "of", "that", "i", "have", "as", "you", "can", "see")]
                repo_name = repo_words[0] if repo_words else ""
                target_url = f"https://github.com/{gh_user}/{repo_name}" if repo_name else f"https://github.com/{gh_user}"
        else:
            # If query is already a domain (e.g. blinkit.com), open it directly
            if re_match := query.strip().lower():
                if "." in re_match and not " " in re_match:
                    target_url = f"https://{re_match}"
                else:
                    target_url = f"https://www.google.com/search?q={encoded_query}"
            else:
                target_url = f"https://www.google.com/search?q={encoded_query}"

        opened_new = _open_url_in_browser_app(target_url, resolved_browser, new_tab=new_tab)

        site_name = site.capitalize() if site else "Google"
        browser_desc = f"in {resolved_browser}" if resolved_browser else "in default browser"
        if not opened_new:
            res = f"{target_url} is already open {browser_desc} (brought to front in full screen)."
        else:
            res = f"Searched {site_name} for '{query}' {browser_desc}: {target_url}"

        # Collect visible search results from the live screen via OCR so the
        # agent can analyze matches and variants before deciding anything.
        res += _collect_visible_search_results(resolved_browser, site_lower)

        registry.log_call("browser_search", {"query": query, "site": site, "browser": browser}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to perform browser search: {str(e)}"
        registry.log_call("browser_search", {"query": query, "site": site, "browser": browser}, err, success=False)
        return err


def _blinkit_add_candidates(ocr_text: str, query: str, scale: float = 1.0) -> list[tuple[int, str, dict]]:
    """
    Score all visible Blinkit ADD buttons against the query and return the
    ranked candidate list: [(score, product_title, add_button_dict), ...]
    Sorted by score descending. Used for ambiguity detection before any click.
    """
    import difflib

    lines = []
    for l in ocr_text.splitlines():
        if "->" in l:
            coords, text = l.split("->", 1)
            text = text.strip()
            m = re.match(r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]", coords.strip())
            if m:
                px, py, pw, ph = map(int, m.groups())
                lines.append({"text": text, "px": px, "py": py, "pw": pw, "ph": ph})

    add_buttons = [item for item in lines if item["text"].strip().upper() == "ADD"]
    if not add_buttons:
        return []

    # 1. Extract target price (e.g. '38 rupees', '₹38', '38 rs' -> '38')
    target_price = None
    m_price = re.search(r'\b(?:₹|rs\.?|inr|rupees)?\s*(\d+)\s*(?:rs|rupees|inr|rupee)?\b', query.lower())
    if m_price:
        num = m_price.group(1)
        if any(k in query.lower() for k in [f'{num} rupees', f'{num} rupee', f'{num} rs', f'₹{num}', f'rupees {num}']):
            target_price = num

    # 2. Extract target volume (e.g. '750 ml', '500g' -> '750ml')
    target_volume = None
    m_vol = re.search(r'(\d+)\s*(ml|l|g|kg)\b', query.lower())
    if m_vol:
        target_volume = m_vol.group(1) + m_vol.group(2)

    # 3. Clean conversational filler words
    clean_q = query.lower()
    clean_q = re.sub(
        r'\b(so add the|add this one into my card|add this one into my cart|into my card|into my cart|'
        r'and now go to the next part|so add|add the|add a|add one|add this|add|please|packet|bottle|'
        r'can you|rupees|rupee|rs|one)\b',
        ' ', clean_q
    )
    if target_price:
        clean_q = re.sub(rf'\b{target_price}\b', ' ', clean_q)
    clean_q = ' '.join(clean_q.split())

    # Phonetic normalization
    clean_q = re.sub(r'\b(a charlie|charlie|achari)\b', 'achaari', clean_q)
    q_words = [w for w in re.sub(r'[^a-zA-Z0-9\s]', '', clean_q).split() if len(w) >= 2]
    q_norm = re.sub(r'[^a-z0-9]', '', clean_q)

    scored_buttons = []
    for b in add_buttons:
        # Collect all text items in the card container around this ADD button
        card_items = [
            it for it in lines
            if it["text"].upper() != "ADD"
            and -int(50 * scale) <= (b["px"] - it["px"]) <= int(220 * scale)
            and -int(15 * scale) <= (b["py"] - it["py"]) < int(280 * scale)
        ]
        card_text = " ".join(it["text"] for it in card_items)
        card_lower = card_text.lower()

        # Extract title from card items
        title = "Product"
        for it in card_items:
            t = it["text"]
            if not any(k in t.lower() for k in ["mins", "min", "08min", "oemin", "r1", "t2", "₹", "56g", "70g", "100g", "38g", "off"]):
                title = t
                break

        title_norm = re.sub(r'[^a-z0-9]', '', title.lower())

        score = 0

        # Penalize sponsored ad cards heavily
        is_ad = any(it["text"].strip().lower() == "ad" for it in card_items)
        if is_ad:
            score -= 100

        # Character-by-character exact normalized title match
        if q_norm and title_norm:
            if q_norm == title_norm:
                score += 120
            elif q_norm in title_norm:
                score += 80
            elif title_norm in q_norm:
                score += 60
            else:
                sim = difflib.SequenceMatcher(None, q_norm, title_norm).ratio()
                score += int(sim * 60)

        # Word-level matches
        for w in q_words:
            if w in card_lower:
                score += 15
            else:
                best_sub = max((difflib.SequenceMatcher(None, w, cw).ratio() for cw in card_lower.split()), default=0)
                if best_sub >= 0.8:
                    score += 8

        # Unrequested modifier penalty (prevents picking Diet Coke when user asked for Coca-Cola Soft Drink)
        unwanted_modifiers = ["diet", "zero", "sugar free", "ginger", "orange", "lemon", "lime", "kiwi", "boba"]
        for mod in unwanted_modifiers:
            if mod in card_lower and mod not in clean_q:
                score -= 30

        # Price match bonus / penalty
        if target_price:
            if re.search(rf'[\b₹rtE]?{target_price}\b', card_lower):
                score += 50
            else:
                if any(re.search(rf'[\b₹rtE]{p}\b', card_lower) for p in ["50", "60", "75", "89", "40"] if p != target_price):
                    score -= 30

        # Volume match bonus
        if target_volume:
            if target_volume in card_lower or re.sub(r'\s+', '', target_volume) in card_lower:
                score += 40

        scored_buttons.append((score, title, b))

    scored_buttons.sort(key=lambda x: x[0], reverse=True)
    return scored_buttons


def _resolve_blinkit_add_click(ocr_text: str, query: str, scale: float = 1.0) -> tuple[str, int, int] | None:
    """
    Intelligently match the product on Blinkit that best matches the search query,
    filtering out sponsored ads and irrelevant products, and find the coordinates of ITS specific ADD button.
    Uses character-by-character normalized matching, price/variant extraction, and card spatial grouping.
    Returns: (matched_product_name, click_x, click_y) in logical coordinates, or None.
    """
    scored_buttons = _blinkit_add_candidates(ocr_text, query, scale)
    if not scored_buttons:
        return None

    score, prod_title, b = scored_buttons[0]
    if score <= 0:
        return None

    lx = int((b["px"] + b["pw"] / 2) / scale)
    ly = int((b["py"] + b["ph"] / 2) / scale)
    return prod_title, lx, ly


def _blinkit_add_ambiguity_message(query: str, ocr_text: str, scale: float = 1.0) -> str | None:
    """
    Detect when the add-to-cart query maps to MULTIPLE plausible Blinkit
    products (e.g. ambiguous variants like 'Diet Coke' vs 'Coca-Cola'). Returns
    an ambiguity question for the user, or None when the match is unambiguous.
    """
    candidates = _blinkit_add_candidates(ocr_text, query, scale)
    if len(candidates) < 2:
        return None
    top_score, top_title, top_btn = candidates[0]
    second_score, second_title, second_btn = candidates[1]
    if top_score <= 0 or second_score <= 0:
        return None
    # Multiple close-scoring candidates -> ambiguous, must ask the user.
    if (top_score - second_score) < 25:
        opts = []
        for score, title, btn in candidates[:5]:
            lx = int((btn["px"] + btn["pw"] / 2) / scale)
            ly = int((btn["py"] + btn["ph"] / 2) / scale)
            opts.append(f"{title} (score {score})")
        return (
            f"AMBIGUOUS_PRODUCTS: Multiple Blinkit products match '{query}': "
            + " | ".join(opts)
            + ". Do NOT auto-select. Present these options to the user and ASK which product they want to add to cart."
        )
    return None


@registry.register
def blinkit_add_to_cart(query: str, browser: str = "") -> str:
    """
    ADD an item to cart on Blinkit.
    CRITICAL INTENT RULE: ONLY invoke this tool when the user EXPLICITLY asks to 'add' or 'put' an item into the cart (e.g. 'add diet coke to cart', 'add milk', 'add lays').
    NEVER invoke this tool if the user only asks to 'search', 'look for', or 'find' an item without asking to add it! For searching, invoke `browser_search(query=..., site='blinkit')`.
    DOES NOT navigate to checkout, proceed to order, or open the address selection drawer.
    Args:
        query: Exact item name to add to cart on Blinkit (e.g. 'Coca-Cola Soft Drink 38 rupees', 'diet coke', 'milk').
        browser: Target browser to run in ('Brave Browser', 'Google Chrome', or empty for default).
    """
    import time
    from pathlib import Path
    from blacky.tools.macos import mouse_click, capture_display_screen, make_window_fullscreen

    # 1. Defense-in-depth safety guard: If user only asked to search without adding to cart, safely delegate to browser_search
    query_lower = query.lower()
    has_explicit_add = bool(re.search(r'\b(add|cart|card|buy|put in)\b', query_lower))
    is_search_intent = bool(re.search(r'\b(search|find|look for|show me)\b', query_lower))
    if is_search_intent and not has_explicit_add:
        return browser_search(query, site="blinkit", browser=browser)

    resolved_browser = _resolve_browser_app(browser) or "Brave Browser"
    ocr_bin = Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
    if not ocr_bin.exists():
        ocr_bin = Path("/tmp/ocr_fast")

    shot_path = "/tmp/blinkit_add_screen.jpg"

    # Clean query for search bar typing if needed
    clean_query = query.strip()
    clean_query = re.sub(
        r'\b(so add the|add this one into my card|add this one into my cart|into my card|into my cart|'
        r'and now go to the next part|so add|add the|add a|add one|add this|add|please|packet|bottle|'
        r'can you)\b',
        '', clean_query, flags=re.IGNORECASE
    ).strip()
    clean_query = re.sub(r'^(the|a)\s+', '', clean_query, flags=re.IGNORECASE).strip()
    if not clean_query:
        clean_query = query.strip()

    try:
        is_already_open = _bring_site_to_front("blinkit.com", resolved_browser)
        if is_already_open:
            make_window_fullscreen(resolved_browser)
            time.sleep(0.08)

            # SCREEN ANALYSIS FIRST: Check if the item is ALREADY visible right now on screen!
            disp = capture_display_screen(shot_path, app_name=resolved_browser, target_site="blinkit")
            scale = disp["scale"]
            origin_x = disp["origin_x"]
            origin_y = disp["origin_y"]

            click_target = None
            if ocr_bin.exists():
                out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
                amb_res = _blinkit_add_ambiguity_message(query, out, scale=scale)
                if amb_res:
                    return amb_res
                click_target = _resolve_blinkit_add_click(out, query, scale=scale)

            if click_target:
                prod_name, lx, ly = click_target
                click_x = int(origin_x + lx)
                click_y = int(origin_y + ly)
                mouse_click(click_x, click_y)
                time.sleep(0.15)
                res = f"Found '{prod_name}' already visible on screen and clicked ADD at ({click_x}, {click_y}) to add it to the cart."
                registry.log_call("blinkit_add_to_cart", {"query": query, "browser": resolved_browser}, res, success=True)
                return res

            # Not visible on screen yet: perform in-page search without page reload
            execute_in_page_search(clean_query, "blinkit", resolved_browser)

            # Capture updated screen
            disp = capture_display_screen(shot_path, app_name=resolved_browser, target_site="blinkit")
            scale = disp["scale"]
            origin_x = disp["origin_x"]
            origin_y = disp["origin_y"]

            if ocr_bin.exists():
                out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
                amb_res = _blinkit_add_ambiguity_message(query, out, scale=scale)
                if amb_res:
                    return amb_res
                click_target = _resolve_blinkit_add_click(out, query, scale=scale)

            if click_target:
                prod_name, lx, ly = click_target
                click_x = int(origin_x + lx)
                click_y = int(origin_y + ly)
                mouse_click(click_x, click_y)
                time.sleep(0.15)
                res = f"Successfully searched Blinkit for '{clean_query}', located '{prod_name}', and clicked ADD at ({click_x}, {click_y}) to add it to the cart."
                registry.log_call("blinkit_add_to_cart", {"query": query, "browser": resolved_browser}, res, success=True)
                return res
            else:
                from blacky.tools.macos import screen_click_text
                add_res = screen_click_text("ADD", app_name=resolved_browser, match_index=0)
                time.sleep(0.15)
                res = f"Added item to cart on Blinkit for '{clean_query}': {add_res}"
                registry.log_call("blinkit_add_to_cart", {"query": query, "browser": resolved_browser}, res, success=True)
                return res
        else:
            # Blinkit not open yet: open search URL directly
            encoded_query = urllib.parse.quote_plus(clean_query)
            search_url = f"https://blinkit.com/s/?q={encoded_query}"
            _open_url_in_browser_app(search_url, resolved_browser)
            time.sleep(1.2)

            disp = capture_display_screen(shot_path, app_name=resolved_browser, target_site="blinkit")
            scale = disp["scale"]
            origin_x = disp["origin_x"]
            origin_y = disp["origin_y"]

            click_target = None
            if ocr_bin.exists():
                out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
                amb_res = _blinkit_add_ambiguity_message(query, out, scale=scale)
                if amb_res:
                    return amb_res
                click_target = _resolve_blinkit_add_click(out, query, scale=scale)

            if click_target:
                prod_name, lx, ly = click_target
                click_x = int(origin_x + lx)
                click_y = int(origin_y + ly)
                mouse_click(click_x, click_y)
                time.sleep(0.15)
                res = f"Successfully searched Blinkit for '{clean_query}', located '{prod_name}', and clicked ADD at ({click_x}, {click_y}) to add it to the cart."
                registry.log_call("blinkit_add_to_cart", {"query": query, "browser": resolved_browser}, res, success=True)
                return res
            else:
                from blacky.tools.macos import screen_click_text
                add_res = screen_click_text("ADD", app_name=resolved_browser, match_index=0)
                time.sleep(0.15)
                res = f"Added item to cart on Blinkit for '{clean_query}': {add_res}"
                registry.log_call("blinkit_add_to_cart", {"query": query, "browser": resolved_browser}, res, success=True)
                return res
    except Exception as e:
        err = f"Failed to add '{query}' to cart on Blinkit: {str(e)}"
        registry.log_call("blinkit_add_to_cart", {"query": query, "browser": resolved_browser}, err, success=False)
        return err


@registry.register
def blinkit_checkout_flow(query: str = "diet coke", browser: str = "Brave Browser") -> str:
    """
    Search for an item on Blinkit, add the matching product to cart, and navigate to checkout.
    SAFETY CRITICAL: Always stops at the checkout/cart page. NEVER places the final paid order.
    Args:
        query: Item name to search on Blinkit (e.g. 'diet coke', 'coke', 'milk').
        browser: Target browser to run in ('Brave Browser', 'Google Chrome', or empty for default).
    """
    import time
    from blacky.tools.macos import screen_click_text

    resolved_browser = _resolve_browser_app(browser) or "Brave Browser"

    try:
        # 1. Add matching product to cart (skipping ads)
        add_res = blinkit_add_to_cart(query=query, browser=resolved_browser)
        time.sleep(1.2)

        # 2. Click Cart button ("item" or "My Cart") to open the cart review drawer
        cart_res = screen_click_text("item", app_name=resolved_browser, match_index=0)
        if "not found" in cart_res.lower():
            cart_res = screen_click_text("My Cart", app_name=resolved_browser, match_index=0)
        time.sleep(1.2)

        # SAFETY & INTENT DISCIPLINE: Stop here at My Cart drawer. NEVER click "Proceed To Pay" or navigate to payment screen!
        res = f"Blinkit cart ready: added matching item for '{query}' to cart and opened My Cart drawer. Stopped safely without proceeding to payment."
        registry.log_call("blinkit_checkout_flow", {"query": query, "browser": resolved_browser}, res, success=True)
        return res
    except Exception as e:
        err = f"Blinkit checkout flow error: {str(e)}"
        registry.log_call("blinkit_checkout_flow", {"query": query, "browser": resolved_browser}, err, success=False)
        return err


@registry.register
def amazon_checkout_flow(query: str = "boat headphones", browser: str = "") -> str:
    """
    Search for an item on Amazon, locate the product, and navigate to cart/checkout.
    SAFETY CRITICAL: Always stops at checkout. NEVER places the final paid order.
    Args:
        query: Item name to search on Amazon (e.g. 'boat headphones', 'usb cable').
        browser: Target browser to run in (defaults to system default browser).
    """
    import time
    from blacky.tools.macos import screen_click_text

    resolved_browser = _resolve_browser_app(browser)
    encoded_query = urllib.parse.quote_plus(query.strip())
    search_url = f"https://www.amazon.in/s?k={encoded_query}"

    try:
        # 1. Open Amazon search in target browser
        _open_url_in_browser_app(search_url, resolved_browser)
        time.sleep(2.0)

        # 2. Look for Add to Cart or navigate to cart
        add_res = screen_click_text("Add to cart", app_name=resolved_browser, match_index=0)
        if "not found" in add_res.lower():
            add_res = screen_click_text("Add to Cart", app_name=resolved_browser, match_index=0)
        time.sleep(1.2)

        # 3. View Cart / Proceed to checkout
        cart_url = "https://www.amazon.in/gp/cart/view.html"
        _open_url_in_browser_app(cart_url, resolved_browser)

        res = f"Amazon test completed: searched '{query}' and navigated to cart/checkout in {resolved_browser}. Stopped safely without placing order."
        registry.log_call("amazon_checkout_flow", {"query": query, "browser": resolved_browser}, res, success=True)
        return res
    except Exception as e:
        err = f"Amazon checkout flow error: {str(e)}"
        registry.log_call("amazon_checkout_flow", {"query": query, "browser": resolved_browser}, err, success=False)
        return err


def _resolve_youtube_video_click(ocr_text: str, query: str, scale: float = 1.0) -> tuple[str, int, int] | None:
    """
    Parse OCR lines from a YouTube search results page, identify the top matching video or playlist,
    and return its title and local click coordinates (lx, ly).
    """
    lines = []
    for line in ocr_text.strip().splitlines():
        if "->" in line:
            coords, text = line.split("->", 1)
            text = text.strip()
            m = re.match(r"\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]", coords.strip())
            if m:
                px, py, pw, ph = map(int, m.groups())
                lines.append({"text": text, "px": px, "py": py, "pw": pw, "ph": ph})

    is_playlist_query = any(k in query.lower() for k in ("playlist", "mix", "album", "songs"))
    stop_words = {"video", "play", "youtube", "official", "a", "the", "for", "in", "and", "of"}
    q_words = [w for w in re.sub(r"[^a-zA-Z0-9\s]", "", query.lower()).split() if len(w) >= 2 and w not in stop_words]
    if not q_words:
        q_words = [w for w in re.sub(r"[^a-zA-Z0-9\s]", "", query.lower()).split() if len(w) >= 2]

    # Detect channel header card (e.g. Subscribe / View Channel buttons) to avoid clicking artist bio
    channel_header_y = None
    for it in lines:
        if it["text"].lower() in ("view channel", "subscribe", "subscribed"):
            channel_header_y = max(channel_header_y or 0, it["py"] + it["ph"])

    ignore_ui = {
        "shorts", "unwatched", "watched", "videos", "recently uploaded", "live", "filters",
        "subtitles", "views", "view", "ago", "yr ago", "subscribers", "subscribe", "view channel",
        "from your search", "from the series", "watch later", "liked videos", "playlists", "history",
        "report history", "more from youtube", "youtube premium", "youtube music", "youtube kids"
    }

    candidates = []
    for it in lines:
        t_lower = it["text"].lower()
        # Exclude left navigation sidebar (px < 150pt) and header search bar / chips (py < 130pt)
        if it["px"] < int(150 * scale) or it["py"] < int(130 * scale):
            continue
        # Exclude artist bio text inside channel banner above channel buttons
        if channel_header_y and it["py"] < channel_header_y:
            continue
        if any(ui == t_lower or t_lower.startswith(ui) for ui in ignore_ui):
            continue
        if len(it["text"]) < 4:
            continue

        match_count = sum(1 for w in q_words if w in t_lower)
        score = match_count * 10

        # Playlist prioritization if user requested a playlist
        has_playlist = any(k in t_lower for k in ("playlist", "mix"))
        has_sub_playlist = any(
            "playlist" in other["text"].lower()
            and abs(other["px"] - it["px"]) < int(100 * scale)
            and 0 < (other["py"] - it["py"]) < int(80 * scale)
            for other in lines
        )
        if is_playlist_query:
            if has_playlist or has_sub_playlist:
                score += 40
            else:
                score -= 10

        if score > 0:
            vertical_penalty = it["py"] / (100 * scale)
            total_score = score - vertical_penalty
            candidates.append((total_score, it["py"], it["text"], it))

    # If no exact word match, fallback to the first video title in search results
    if not candidates:
        for it in lines:
            t_lower = it["text"].lower()
            if channel_header_y and it["py"] < channel_header_y:
                continue
            if it["px"] > int(300 * scale) and it["py"] > int(140 * scale) and len(it["text"]) > 10:
                if not any(ui in t_lower for ui in ignore_ui):
                    candidates.append((1, it["py"], it["text"], it))
                    break

    if not candidates:
        return None

    candidates.sort(key=lambda x: -x[0])
    score, py, title, it = candidates[0]
    # Click near the start of the video/playlist title link
    lx = int((it["px"] + 50 * scale) / scale)
    ly = int((it["py"] + it["ph"] / 2) / scale)
    return title, lx, ly


@registry.register
def youtube_play(query: str, browser: str = "") -> str:
    """
    Play a song, playlist, or video on YouTube.
    CRITICAL INTENT RULE: ONLY invoke this tool when the user EXPLICITLY asks to 'play', 'start', 'watch', or 'listen to' a video/song
    (e.g. 'play bulleya on youtube', 'play sidhu moose wala playlist').
    NEVER invoke this tool if the user only asks to 'search' or 'find' videos on YouTube without asking to play!
    For searching, invoke `browser_search(query=..., site='youtube')`.
    Args:
        query: Song or video name to search and play (e.g. 'bulleya song', 'sidhu moose wala playlist', 'lofi hip hop').
        browser: Target browser to run in (defaults to system default browser, e.g. 'Brave Browser').
    """
    import time
    from pathlib import Path
    from blacky.tools.macos import mouse_click, capture_display_screen, make_window_fullscreen

    # 1. Defense-in-depth safety guard: If user only asked to search without playing, safely delegate to browser_search
    query_lower = query.lower()
    has_play_intent = bool(re.search(r'\b(play|start|listen|watch|run)\b', query_lower))
    is_search_intent = bool(re.search(r'\b(search|find|look for|show me)\b', query_lower))
    if is_search_intent and not has_play_intent:
        return browser_search(query, site="youtube", browser=browser)

    resolved_browser = _resolve_browser_app(browser) or "Brave Browser"
    clean_query = query.strip()
    # Remove conversational filler phrases
    clean_query = re.sub(
        r'\b(one more task for you|open the youtube and|open youtube and|open search for|search for|and play the playlist.*|and play it.*|which is in the top most.*|play the playlist.*|play it)\b',
        '', clean_query, flags=re.IGNORECASE
    ).strip()
    clean_query = re.sub(r'^(the|a)\s+', '', clean_query, flags=re.IGNORECASE).strip()
    if not clean_query:
        clean_query = query.strip()

    ocr_bin = Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
    if not ocr_bin.exists():
        ocr_bin = Path("/tmp/ocr_fast")

    shot_path = "/tmp/youtube_search_screen.jpg"

    try:
        # ALWAYS open YouTube search URL in a brand new tab and in Full Screen
        encoded_query = urllib.parse.quote_plus(clean_query)
        search_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        _open_url_in_browser_app(search_url, resolved_browser)
        time.sleep(1.0)

        subprocess.run(["osascript", "-e", f'tell application "{resolved_browser}" to activate'], check=True)
        time.sleep(0.08)

        disp = capture_display_screen(shot_path, app_name=resolved_browser, target_site="youtube")
        scale = disp["scale"]
        origin_x = disp["origin_x"]
        origin_y = disp["origin_y"]

        click_target = None
        if ocr_bin.exists():
            out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
            click_target = _resolve_youtube_video_click(out, clean_query, scale=scale)

        if click_target:
            video_title, lx, ly = click_target
            click_x = int(origin_x + lx)
            click_y = int(origin_y + ly)
            mouse_click(click_x, click_y)
            time.sleep(0.35)

            # Verify if URL transitioned to a video watch or playlist page
            script = f'tell application "{resolved_browser}" to return (URL of active tab of front window as string)'
            try:
                proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=2)
                curr_url = proc.stdout.strip()
            except Exception:
                curr_url = ""

            if "watch?v=" not in curr_url and "playlist?list=" not in curr_url:
                mouse_click(click_x, click_y)
                time.sleep(0.2)

            res = f"Playing '{video_title}' on YouTube in {resolved_browser}."
            registry.log_call("youtube_play", {"query": query, "browser": resolved_browser}, res, success=True)
            return res
        else:
            # Fallback: click directly at the standard first video result location (~830pt, ~160pt)
            click_x = int(origin_x + 830)
            click_y = int(origin_y + 160)
            mouse_click(click_x, click_y)
            time.sleep(0.35)
            res = f"Searched YouTube for '{clean_query}' and clicked top result in {resolved_browser} to play."
            registry.log_call("youtube_play", {"query": query, "browser": resolved_browser}, res, success=True)
            return res
    except Exception as e:
        err = f"Failed to play '{query}' on YouTube: {str(e)}"
        registry.log_call("youtube_play", {"query": query, "browser": resolved_browser}, err, success=False)
        return err


# ----------------------------------------------------------------------
# LeetCode Solution Database & Direct Automation
# ----------------------------------------------------------------------

_LEETCODE_SOLUTIONS: dict[tuple[str, str], str] = {
    ("two-sum", "python"): (
        "class Solution:\n"
        "    def twoSum(self, nums: List[int], target: int) -> List[int]:\n"
        "        seen = {}\n"
        "        for i, num in enumerate(nums):\n"
        "            diff = target - num\n"
        "            if diff in seen:\n"
        "                return [seen[diff], i]\n"
        "            seen[num] = i\n"
        "        return []\n"
    ),
    ("two-sum", "java"): (
        "import java.util.HashMap;\n"
        "import java.util.Map;\n\n"
        "class Solution {\n"
        "    public int[] twoSum(int[] nums, int target) {\n"
        "        Map<Integer, Integer> map = new HashMap<>();\n"
        "        for (int i = 0; i < nums.length; i++) {\n"
        "            int diff = target - nums[i];\n"
        "            if (map.containsKey(diff)) {\n"
        "                return new int[] { map.get(diff), i };\n"
        "            }\n"
        "            map.put(nums[i], i);\n"
        "        }\n"
        "        return new int[] {};\n"
        "    }\n"
        "}\n"
    ),
    ("median-of-two-sorted-arrays", "java"): (
        "class Solution {\n"
        "    public double findMedianSortedArrays(int[] nums1, int[] nums2) {\n"
        "        if (nums1.length > nums2.length) {\n"
        "            return findMedianSortedArrays(nums2, nums1);\n"
        "        }\n"
        "        int m = nums1.length, n = nums2.length;\n"
        "        int low = 0, high = m;\n"
        "        while (low <= high) {\n"
        "            int partitionX = (low + high) / 2;\n"
        "            int partitionY = (m + n + 1) / 2 - partitionX;\n"
        "            int maxLeftX = (partitionX == 0) ? Integer.MIN_VALUE : nums1[partitionX - 1];\n"
        "            int minRightX = (partitionX == m) ? Integer.MAX_VALUE : nums1[partitionX];\n"
        "            int maxLeftY = (partitionY == 0) ? Integer.MIN_VALUE : nums2[partitionY - 1];\n"
        "            int minRightY = (partitionY == n) ? Integer.MAX_VALUE : nums2[partitionY];\n"
        "            if (maxLeftX <= minRightY && maxLeftY <= minRightX) {\n"
        "                if ((m + n) % 2 == 0) {\n"
        "                    return ((double) Math.max(maxLeftX, maxLeftY) + Math.min(minRightX, minRightY)) / 2.0;\n"
        "                } else {\n"
        "                    return (double) Math.max(maxLeftX, maxLeftY);\n"
        "                }\n"
        "            } else if (maxLeftX > minRightY) {\n"
        "                high = partitionX - 1;\n"
        "            } else {\n"
        "                low = partitionX + 1;\n"
        "            }\n"
        "        }\n"
        "        return 0.0;\n"
        "    }\n"
        "}\n"
    ),
    ("median-of-two-sorted-arrays", "python"): (
        "class Solution:\n"
        "    def findMedianSortedArrays(self, nums1: List[int], nums2: List[int]) -> float:\n"
        "        if len(nums1) > len(nums2):\n"
        "            nums1, nums2 = nums2, nums1\n"
        "        m, n = len(nums1), len(nums2)\n"
        "        low, high = 0, m\n"
        "        while low <= high:\n"
        "            partitionX = (low + high) // 2\n"
        "            partitionY = (m + n + 1) // 2 - partitionX\n"
        "            maxLeftX = float('-inf') if partitionX == 0 else nums1[partitionX - 1]\n"
        "            minRightX = float('inf') if partitionX == m else nums1[partitionX]\n"
        "            maxLeftY = float('-inf') if partitionY == 0 else nums2[partitionY - 1]\n"
        "            minRightY = float('inf') if partitionY == n else nums2[partitionY]\n"
        "            if maxLeftX <= minRightY and maxLeftY <= minRightX:\n"
        "                if (m + n) % 2 == 0:\n"
        "                    return (max(maxLeftX, maxLeftY) + min(minRightX, minRightY)) / 2.0\n"
        "                else:\n"
        "                    return float(max(maxLeftX, maxLeftY))\n"
        "            elif maxLeftX > minRightY:\n"
        "                high = partitionX - 1\n"
        "            else:\n"
        "                low = partitionX + 1\n"
        "        return 0.0\n"
    ),
    ("median-of-two-sorted-arrays", "cpp"): (
        "#include <vector>\n"
        "#include <algorithm>\n"
        "#include <climits>\n"
        "using namespace std;\n\n"
        "class Solution {\n"
        "public:\n"
        "    double findMedianSortedArrays(vector<int>& nums1, vector<int>& nums2) {\n"
        "        if (nums1.size() > nums2.size()) return findMedianSortedArrays(nums2, nums1);\n"
        "        int m = nums1.size(), n = nums2.size();\n"
        "        int low = 0, high = m;\n"
        "        while (low <= high) {\n"
        "            int partitionX = (low + high) / 2;\n"
        "            int partitionY = (m + n + 1) / 2 - partitionX;\n"
        "            int maxLeftX = (partitionX == 0) ? INT_MIN : nums1[partitionX - 1];\n"
        "            int minRightX = (partitionX == m) ? INT_MAX : nums1[partitionX];\n"
        "            int maxLeftY = (partitionY == 0) ? INT_MIN : nums2[partitionY - 1];\n"
        "            int minRightY = (partitionY == n) ? INT_MAX : nums2[partitionY];\n"
        "            if (maxLeftX <= minRightY && maxLeftY <= minRightX) {\n"
        "                if ((m + n) % 2 == 0)\n"
        "                    return ((double)max(maxLeftX, maxLeftY) + min(minRightX, minRightY)) / 2.0;\n"
        "                else\n"
        "                    return (double)max(maxLeftX, maxLeftY);\n"
        "            } else if (maxLeftX > minRightY) {\n"
        "                high = partitionX - 1;\n"
        "            } else {\n"
        "                low = partitionX + 1;\n"
        "            }\n"
        "        }\n"
        "        return 0.0;\n"
        "    }\n"
        "};\n"
    ),
    ("3sum", "java"): (
        "import java.util.*;\n\n"
        "class Solution {\n"
        "    public List<List<Integer>> threeSum(int[] nums) {\n"
        "        Arrays.sort(nums);\n"
        "        List<List<Integer>> res = new ArrayList<>();\n"
        "        for (int i = 0; i < nums.length - 2; i++) {\n"
        "            if (i > 0 && nums[i] == nums[i - 1]) continue;\n"
        "            int l = i + 1, r = nums.length - 1;\n"
        "            while (l < r) {\n"
        "                int sum = nums[i] + nums[l] + nums[r];\n"
        "                if (sum == 0) {\n"
        "                    res.add(Arrays.asList(nums[i], nums[l], nums[r]));\n"
        "                    while (l < r && nums[l] == nums[l + 1]) l++;\n"
        "                    while (l < r && nums[r] == nums[r - 1]) r--;\n"
        "                    l++;\n"
        "                    r--;\n"
        "                } else if (sum < 0) {\n"
        "                    l++;\n"
        "                } else {\n"
        "                    r--;\n"
        "                }\n"
        "            }\n"
        "        }\n"
        "        return res;\n"
        "    }\n"
        "}\n"
    ),
    ("valid-parentheses", "java"): (
        "import java.util.Stack;\n\n"
        "class Solution {\n"
        "    public boolean isValid(String s) {\n"
        "        Stack<Character> stack = new Stack<>();\n"
        "        for (char c : s.toCharArray()) {\n"
        "            if (c == '(') stack.push(')');\n"
        "            else if (c == '{') stack.push('}');\n"
        "            else if (c == '[') stack.push(']');\n"
        "            else if (stack.isEmpty() || stack.pop() != c) return false;\n"
        "        }\n"
        "        return stack.isEmpty();\n"
        "    }\n"
        "}\n"
    ),
    ("reverse-linked-list", "java"): (
        "class Solution {\n"
        "    public ListNode reverseList(ListNode head) {\n"
        "        ListNode prev = null;\n"
        "        ListNode curr = head;\n"
        "        while (curr != null) {\n"
        "            ListNode next = curr.next;\n"
        "            curr.next = prev;\n"
        "            prev = curr;\n"
        "            curr = next;\n"
        "        }\n"
        "        return prev;\n"
        "    }\n"
        "}\n"
    ),
    ("3sum", "python"): (
        "class Solution:\n"
        "    def threeSum(self, nums: List[int]) -> List[List[int]]:\n"
        "        nums.sort()\n"
        "        res = []\n"
        "        for i in range(len(nums) - 2):\n"
        "            if i > 0 and nums[i] == nums[i - 1]:\n"
        "                continue\n"
        "            l, r = i + 1, len(nums) - 1\n"
        "            while l < r:\n"
        "                s = nums[i] + nums[l] + nums[r]\n"
        "                if s < 0:\n"
        "                    l += 1\n"
        "                elif s > 0:\n"
        "                    r -= 1\n"
        "                else:\n"
        "                    res.append([nums[i], nums[l], nums[r]])\n"
        "                    while l < r and nums[l] == nums[l + 1]: l += 1\n"
        "                    while l < r and nums[r] == nums[r - 1]: r -= 1\n"
        "                    l += 1; r -= 1\n"
        "        return res\n"
    ),
    ("valid-parentheses", "python"): (
        "class Solution:\n"
        "    def isValid(self, s: str) -> bool:\n"
        "        stack = []\n"
        "        mapping = {')': '(', '}': '{', ']': '['}\n"
        "        for char in s:\n"
        "            if char in mapping:\n"
        "                top = stack.pop() if stack else '#'\n"
        "                if mapping[char] != top:\n"
        "                    return False\n"
        "            else:\n"
        "                stack.append(char)\n"
        "        return not stack\n"
    ),
    ("reverse-linked-list", "python"): (
        "class Solution:\n"
        "    def reverseList(self, head: Optional[ListNode]) -> Optional[ListNode]:\n"
        "        prev = None\n"
        "        curr = head\n"
        "        while curr:\n"
        "            nxt = curr.next\n"
        "            curr.next = prev\n"
        "            prev = curr\n"
        "            curr = nxt\n"
        "        return prev\n"
    ),
}


@registry.register
def leetcode_problem(
    problem: str,
    language: str = "",
    solve: bool = True,
    submit: bool = True,
    browser: str = "",
) -> str:
    """
    Open any LeetCode problem, generate its optimal solution, save to Desktop, copy to clipboard, and submit.
    Args:
        problem: Name of the LeetCode problem (e.g. 'Two Sum', '3Sum', 'Valid Parentheses', 'Reverse Linked List').
        language: Programming language ('python', 'java', 'cpp'). If empty, auto-detects from active LeetCode editor.
        solve: Whether to provide and prepare the optimal solution.
        submit: Whether to automatically send the submit keystroke (Cmd+') to LeetCode in browser.
        browser: Browser application name (default: Brave Browser or system default).
    """
    try:
        from blacky.tools.macos import mouse_click, capture_display_screen
        clean = re.sub(r'^(search|find|look for|show me|open|solve|submit)\s+(for\s+)?(the\s+|a\s+)?', '', problem, flags=re.I).strip()
        clean = re.sub(r'^(?:(?:q\.?|ques\.?|question\.?|problem\.?|no\.?|#)?\s*\d+[\.\)\:\-\s]+)', '', clean, flags=re.I).strip()
        clean = re.sub(r'\s+(in|on|at)\s+(the\s+)?(leetcode|leetocde|leetcdoe|leatcode|letcode|leetcde|lc)\b.*', '', clean, flags=re.I).strip()
        clean = re.sub(r'\s+(ques|question|problem|code|solution)\b.*', '', clean, flags=re.I).strip()
        clean = re.sub(r'^(?:(?:q\.?|ques\.?|question\.?|problem\.?|no\.?|#)?\s*\d+[\.\)\:\-\s]+)', '', clean, flags=re.I).strip()
        slug = re.sub(r'[^a-zA-Z0-9]+', '-', clean).strip('-').lower()
        if not slug:
            slug = "two-sum"

        target_url = f"https://leetcode.com/problems/{slug}/"
        resolved_browser = _resolve_browser_app(browser) or get_default_browser() or "Brave Browser"

        # 1. Open the LeetCode problem in browser in full screen
        _open_url_in_browser_app(target_url, resolved_browser, new_tab=False)
        time.sleep(1.8)

        # 2. Inspect active screen via fast OCR to detect language, editor location, and submit button
        shot_path = "/tmp/blacky_leetcode_screen.png"
        disp = capture_display_screen(shot_path, app_name=resolved_browser)
        scale = disp.get("scale", 2.0)
        origin_x = disp.get("origin_x", 0.0)
        origin_y = disp.get("origin_y", 0.0)

        ocr_bin = Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
        ocr_lines = []
        if ocr_bin.exists():
            try:
                ocr_out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
                ocr_lines = ocr_out.splitlines()
            except Exception:
                pass

        # Detect language from screen if not explicitly requested
        lang_key = (language or "").lower().strip()
        detected_lang = ""
        editor_coords = None
        submit_coords = None

        for line in ocr_lines:
            if "->" in line:
                coords_str, text = line.split("->", 1)
                t_lower = text.strip().lower()
                m = re.match(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', coords_str.strip())
                if not m:
                    continue
                px, py, pw, ph = map(int, m.groups())
                lx = (px + pw / 2) / scale
                ly = (py + ph / 2) / scale

                if not detected_lang:
                    if "java" in t_lower and ("auto" in t_lower or "original" in t_lower or "class" in t_lower or py < 300 * scale):
                        detected_lang = "java"
                    elif "python" in t_lower and py < 300 * scale:
                        detected_lang = "python"
                    elif "c++" in t_lower and py < 300 * scale:
                        detected_lang = "cpp"

                if "submit" in t_lower and ly < 120:
                    submit_coords = (int(origin_x + lx), int(origin_y + ly))

                if ("class solution" in t_lower or "def twosum" in t_lower or "solution" in t_lower) and lx > 600:
                    editor_coords = (int(origin_x + lx), int(origin_y + ly))

        if not lang_key:
            lang_key = detected_lang or "java"

        # 3. Get optimal solution code
        solution_code = _LEETCODE_SOLUTIONS.get((slug, lang_key)) or _LEETCODE_SOLUTIONS.get((slug, "java")) or _LEETCODE_SOLUTIONS.get((slug, "python"))
        if not solution_code:
            desktop = Path.home() / "Desktop"
            for f in desktop.glob(f"*{slug.replace('-', '')}*"):
                try:
                    solution_code = f.read_text(encoding="utf-8")
                    break
                except Exception:
                    pass

        saved_path = ""
        if solution_code:
            fname = f"{slug.replace('-', '_')}_leetcode_solution.txt"
            save_file = Path.home() / "Desktop" / fname
            save_file.write_text(solution_code, encoding="utf-8")
            saved_path = f"~/Desktop/{fname}"

            try:
                subprocess.run(["pbcopy"], input=solution_code.encode("utf-8"), check=True)
            except Exception:
                pass

        # 4. Focus editor and paste solution
        submitted_msg = ""
        if solution_code:
            # Click inside the editor to focus
            if editor_coords:
                mouse_click(editor_coords[0], editor_coords[1])
            else:
                default_editor_x = int(origin_x + disp["width"] * 0.65)
                default_editor_y = int(origin_y + disp["height"] * 0.35)
                mouse_click(default_editor_x, default_editor_y)
            time.sleep(0.3)

            # Paste code
            paste_script = f'''
            tell application "{resolved_browser}" to activate
            tell application "System Events"
                keystroke "a" using {{command down}}
                delay 0.2
                keystroke "v" using {{command down}}
            end tell
            '''
            subprocess.run(["osascript", "-e", paste_script], capture_output=True, timeout=5)
            time.sleep(0.5)

            # 5. Submit solution
            if submit:
                if submit_coords:
                    mouse_click(submit_coords[0], submit_coords[1])
                else:
                    sub_script = '''
                    tell application "System Events"
                        keystroke "'" using {command down}
                    end tell
                    '''
                    subprocess.run(["osascript", "-e", sub_script], capture_output=True, timeout=3)

                time.sleep(2.5)
                # Verify result via OCR
                outcome_text = ""
                try:
                    capture_display_screen(shot_path, app_name=resolved_browser)
                    v_out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
                    for vl in v_out.splitlines():
                        if any(k in vl.lower() for k in ("accepted", "testcases passed", "wrong answer", "runtime error")):
                            outcome_text = vl.split("->", 1)[-1].strip()
                            break
                except Exception:
                    pass

                if outcome_text:
                    submitted_msg = f" Solution pasted into code editor and submitted: {outcome_text}!"
                else:
                    submitted_msg = " Solution pasted into code editor and submitted (Cmd+')."

        res = f"Opened LeetCode problem '{clean.title()}' ({target_url}) in {resolved_browser} in full screen."
        if saved_path:
            res += f" Saved optimal {lang_key.title()} solution to {saved_path} and copied to clipboard."
        if submitted_msg:
            res += submitted_msg

        registry.log_call("leetcode_problem", {"problem": problem, "slug": slug}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to handle LeetCode problem: {str(e)}"
        registry.log_call("leetcode_problem", {"problem": problem}, err, success=False)
        return err
