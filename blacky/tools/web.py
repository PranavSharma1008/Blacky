"""
Web search, scraping, and browser automation tools for BlackyAgent.
"""

import urllib.parse
import subprocess
import time
import re
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
    Work ONLY on the single system default browser (e.g. Brave Browser).
    Never open or work across multiple browsers.
    """
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

    if target_app in ("Google Chrome", "Brave Browser"):
        script = f'''
        set winTitle to ""
        tell application "{target_app}"
            activate
            repeat with w_idx from 1 to (count of windows)
                set w to window w_idx
                repeat with i from 1 to (count of tabs of w)
                    if (URL of tab i of w as string) contains "{site_domain}" then
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
                            if n contains "{site_domain}" or (winTitle is not "" and n contains winTitle) then
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
                    if (URL of t as string) contains "{site_domain}" then
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
                            if n contains "{site_domain}" or (winTitle is not "" and n contains winTitle) then
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


def _open_url_in_browser_app(url: str, browser_app: str | None) -> None:
    """
    Open URL in the single system default browser, ALWAYS opening in a NEW TAB
    and ensuring Entire Screen (Full Screen) mode on macOS.
    """
    from blacky.tools.macos import make_window_fullscreen

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    target_app = browser_app or get_default_browser() or "Brave Browser"

    # Use specialized AppleScript for Chrome, Brave, Safari to ALWAYS make a brand new tab
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
def open_in_browser(url: str, browser: str = "") -> str:
    """
    Open any website or URL directly in a web browser on macOS.
    Args:
        url: Web address to open (e.g. 'https://blinkit.com', 'https://amazon.in').
        browser: Optional target browser: 'Google Chrome' (or 'chrome'), 'Brave Browser' (or 'brave'), 'Safari', or leave empty for default.
    """
    try:
        resolved_browser = _resolve_browser_app(browser)
        _open_url_in_browser_app(url, resolved_browser)
        browser_desc = f"in {resolved_browser}" if resolved_browser else "in default browser"
        res = f"Opened {url} {browser_desc}."
        registry.log_call("open_in_browser", {"url": url, "browser": browser}, res, success=True)
        return res
    except Exception as e:
        err = f"Failed to open browser: {str(e)}"
        registry.log_call("open_in_browser", {"url": url, "browser": browser}, err, success=False)
        return err


@registry.register
def browser_search(query: str, site: str = "", browser: str = "") -> str:
    """
    Search for items, products, videos, or queries in the browser WITHOUT adding anything to cart.
    CRITICAL INTENT RULE: ALWAYS invoke this tool when the user asks to 'search', 'find', or 'look for' something
    (e.g. 'search the diet coke in blinkit', 'search boat headphones on amazon', 'search for milk').
    Displays the search results on screen. NEVER clicks ADD or modifies the shopping cart.
    Args:
        query: Search term (e.g. 'diet coke', 'boat headphones', 'milk').
        site: Specific website ('blinkit', 'amazon', 'youtube', 'google', 'flipkart') or empty for Google.
        browser: Target browser (leave empty for system default browser).
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

        encoded_query = urllib.parse.quote_plus(clean_query)
        if site_lower in ("amazon", "amazon.in", "amazon.com"):
            target_url = f"https://www.amazon.in/s?k={encoded_query}"
        elif site_lower in ("youtube", "yt"):
            target_url = f"https://www.youtube.com/results?search_query={encoded_query}"
        elif site_lower in ("blinkit", "grofers"):
            target_url = f"https://blinkit.com/s/?q={encoded_query}"
        elif site_lower in ("flipkart", "fk"):
            target_url = f"https://www.flipkart.com/search?q={encoded_query}"
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

        _open_url_in_browser_app(target_url, resolved_browser)

        site_name = site.capitalize() if site else "Google"
        browser_desc = f"in {resolved_browser}" if resolved_browser else "in default browser"
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
