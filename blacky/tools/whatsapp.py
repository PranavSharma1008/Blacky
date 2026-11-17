"""
WhatsApp desktop automation tools for BlackyAgent on macOS.
Supports opening chats, searching contacts, sending messages, and initiating video/voice calls.
"""

import subprocess
import time
import re
from blacky.tools.base import registry


def _ensure_whatsapp_running() -> bool:
    """Ensure WhatsApp application is launched, open, frontmost, and in entire screen (full screen) on macOS."""
    from pathlib import Path
    app_path = Path("/Applications/WhatsApp.app")
    user_app_path = Path.home() / "Applications" / "WhatsApp.app"
    if not app_path.exists() and not user_app_path.exists():
        return False

    # 1. Launch/activate WhatsApp process
    try:
        subprocess.run(["open", "-a", "WhatsApp"], capture_output=True, timeout=8)
    except Exception:
        pass

    # 2. Reopen and bring frontmost via AppleScript
    try:
        script = '''
        tell application "WhatsApp"
            reopen
            activate
        end tell
        delay 0.2
        tell application "System Events"
            try
                set frontmost of process "WhatsApp" to true
            end try
        end tell
        '''
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=8)
    except Exception:
        pass

    time.sleep(0.3)

    # 3. Best-effort full screen mode
    try:
        from blacky.tools.macos import make_window_fullscreen
        make_window_fullscreen("WhatsApp")
    except Exception:
        pass

    return True


def _set_clipboard(text: str) -> None:
    """Copy text to macOS system clipboard using pbcopy for reliable emoji & unicode input."""
    proc = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
    proc.communicate(text.encode("utf-8"))


_SELF_CHAT_ALIASES = {
    "you",
    "me",
    "myself",
    "my self",
    "self",
    "my number",
    "my own number",
    "my own chat",
    "own chat",
    "message myself",
    "text myself",
}

# Filler words that never identify a recipient on their own.
_SELF_TARGET_FILLER = {
    "the", "a", "an", "to", "on", "in", "it", "this", "that", "chat", "text",
    "message", "msg", "send", "whatsapp", "app", "please", "now",
}


def _is_self_target(contact: str) -> bool:
    """
    Return True when the user is referring to their OWN WhatsApp chat
    (e.g. "me", "myself", "text me", "message yourself").
    WhatsApp Desktop exposes this conversation as the "<own number> (You)" row.
    """
    cleaned = " ".join(re.sub(r"[^a-z0-9\s]", " ", (contact or "").lower()).split())
    if not cleaned:
        return False
    if cleaned in _SELF_CHAT_ALIASES:
        return True
    tokens = [t for t in cleaned.split() if t not in _SELF_TARGET_FILLER]
    return bool(tokens) and " ".join(tokens) in _SELF_CHAT_ALIASES


def _ocr_bin() -> str | None:
    """Locate the bundled fast OCR binary."""
    from pathlib import Path

    bundled = Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
    if bundled.exists():
        return str(bundled)
    fallback = Path("/tmp/ocr_fast")
    if fallback.exists():
        return str(fallback)
    return None


_SELF_ROW_RE = re.compile(r"(?:\(\s*you\s*\)|\byou\b|message\s+yourself)", re.IGNORECASE)


def _search_whatsapp(term: str) -> str:
    """Type a search term into WhatsApp's search bar (Cmd+F) without leaving full screen."""
    clean = term.replace('"', '\\"')
    script = f'''
    tell application "WhatsApp" to activate
    delay 0.15
    tell application "System Events"
        tell process "WhatsApp"
            set frontmost to true
            keystroke "f" using {{command down}}
            delay 0.15
            keystroke "a" using {{command down}}
            key code 51 -- Delete current search text
            keystroke "{clean}"
            delay 0.6
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=6)
    time.sleep(0.3)
    return clean


def _find_self_chat_row() -> dict | None:
    """
    Locate the user's own "(You)" / "Message yourself" conversation row in the
    WhatsApp sidebar via search + OCR.
    Returns {'name', 'x', 'y'} in logical screen coordinates, or None.
    """
    _search_whatsapp("You")

    shot_path = "/tmp/wa_self_chat.png"
    try:
        from blacky.tools.macos import capture_display_screen, get_screen_scale_factor
        capture_display_screen(shot_path, app_name="WhatsApp")
        scale = get_screen_scale_factor(shot_path)
    except Exception:
        return None

    ocr = _ocr_bin()
    if not ocr:
        return None
    try:
        out = subprocess.check_output([ocr, shot_path], text=True)
    except Exception:
        return None

    for line in out.splitlines():
        if "->" not in line:
            continue
        coords, text = line.split("->", 1)
        text = text.strip()
        if not _SELF_ROW_RE.search(text):
            continue
        m = re.match(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', coords.strip())
        if not m:
            continue
        px, py, pw, ph = map(int, m.groups())
        # Sidebar chat list sits on the left half, below the search field.
        if px < int(1000 * scale) and py > int(140 * scale):
            return {
                "name": text,
                "x": int((px + pw / 2) / scale),
                "y": int((py + ph / 2) / scale),
            }
    return None


def _open_self_chat() -> str:
    """Open the user's own WhatsApp conversation ("Message yourself")."""
    global _CURRENT_ACTIVE_CHAT
    row = _find_self_chat_row()
    if row:
        from blacky.tools.macos import mouse_click
        mouse_click(row["x"], row["y"])
        time.sleep(0.4)
        _CURRENT_ACTIVE_CHAT = row["name"]
        _focus_whatsapp_composer()
        return f"Opened WhatsApp chat for contact: '{row['name']}' (your own chat)"

    # Fallback: search 'You' and select top match via Enter
    _search_whatsapp("You")
    time.sleep(0.3)
    script = '''
    tell application "WhatsApp" to activate
    delay 0.2
    tell application "System Events"
        tell process "WhatsApp"
            key code 36 -- Return to open highlighted search result
            delay 0.3
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=5)
    time.sleep(0.3)
    _CURRENT_ACTIVE_CHAT = "You (Message yourself)"
    _focus_whatsapp_composer()
    return "Opened WhatsApp chat for contact: 'You' (your own chat)"


def _normalize_for_match(text: str) -> str:
    """Collapse text to lowercase alphanumerics for fuzzy OCR comparison."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def _verify_message_in_chat(message: str) -> bool:
    """Check on screen whether the just-sent message is actually rendered in the open chat."""
    probe = _normalize_for_match(message)[:32].strip()
    if len(probe) < 4:
        return False
    ocr = _ocr_bin()
    if not ocr:
        return False
    shot_path = "/tmp/wa_send_verify.png"
    try:
        from blacky.tools.macos import capture_display_screen
        capture_display_screen(shot_path, app_name="WhatsApp")
        out = subprocess.check_output([ocr, shot_path], text=True)
    except Exception:
        return False
    return probe in _normalize_for_match(out)


def _get_whatsapp_window_geometry() -> tuple[int, int, int, int] | None:
    """Return (wx, wy, ww, wh) of the front WhatsApp window."""
    script = '''
    tell application "WhatsApp" to activate
    delay 0.1
    tell application "System Events"
        tell process "WhatsApp"
            set w to front window
            set wPos to position of w
            set wSize to size of w
            return ((item 1 of wPos) as string) & "," & ((item 2 of wPos) as string) & "," & ((item 1 of wSize) as string) & "," & ((item 2 of wSize) as string)
        end tell
    end tell
    '''
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if res.returncode == 0 and res.stdout.strip():
        try:
            parts = [int(p.strip()) for p in res.stdout.strip().split(",")]
            return parts[0], parts[1], parts[2], parts[3]
        except Exception:
            pass
    return None


def _focus_whatsapp_composer() -> bool:
    """
    Explicitly focus WhatsApp message composer text area.
    Clicks directly into the composer input field at the bottom of the active chat pane
    and ensures the AXTextArea element has keyboard focus.
    """
    from blacky.tools.macos import mouse_click
    geom = _get_whatsapp_window_geometry()
    if geom:
        wx, wy, ww, wh = geom
        offset_y = 42 if wy == 0 else 32
        target_x = wx + int(ww * 0.55)
        target_y = wy + wh - offset_y
        mouse_click(target_x, target_y)
        time.sleep(0.2)
        return True
    return False


@registry.register
def whatsapp_click_send_button() -> str:
    """
    Click the green Send button (paper airplane / arrow icon) at the bottom-right of the WhatsApp chat window,
    or press Return in the composer to send the currently typed / drafted message.
    Use this whenever the user asks to click the send button, send the message, or why the message was not sent.
    """
    _ensure_whatsapp_running()
    _focus_whatsapp_composer()
    time.sleep(0.2)

    # WhatsApp Desktop dispatches the drafted message on Return while the composer is focused.
    send_script = '''
    tell application "WhatsApp" to activate
    delay 0.1
    tell application "System Events"
        tell process "WhatsApp"
            key code 36 -- Return
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", send_script], capture_output=True)
    time.sleep(0.3)

    res = "Successfully clicked the WhatsApp Send button and sent the message."
    registry.log_call("whatsapp_click_send_button", {}, res, success=True)
    return res


def _clean_phone(target: str) -> str | None:
    """Check if target string is a phone number."""
    cleaned = re.sub(r"[\s\-\(\)]", "", target.strip())
    if re.match(r"^\+?\d{7,15}$", cleaned):
        return cleaned
    return None


def _clean_single_repair(text: str) -> tuple[str, bool]:
    """Resolve a single verbal self-correction / repair marker in text."""
    markers = [
        r"\boh\s+sorry\b",
        r"\bno\s+sorry\b",
        r"\bso\s+sorry\b",
        r"\bwait\s+no\b",
        r"\bno\s+wait\b",
        r"\bscratch\s+that\b",
        r"\bactually\s+no\b",
        r"\bactually\b",
        r"\bi\s+mean\b",
        r"\bmake\s+that\b",
        r"\bor\s+rather\b",
        r"\bcorrection:?\b",
        r"(?<!\bam\s)(?<!\bfeel\s)(?<!\bso\s)(?<!\bi\'m\s)(?<!\bim\s)\bsorry\b",
    ]

    pattern = re.compile(
        r"^(.*?)(?:,\s*|\s+)(" + "|".join(markers) + r")(?:,\s*|\s+)(.*)$",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        lead_pattern = re.compile(
            r"^(" + "|".join(markers) + r")(?:,\s*|\s+)(.*)$", re.IGNORECASE
        )
        lead_match = lead_pattern.search(text)
        if lead_match:
            if lead_match.group(1).lower() == "sorry":
                return text, False
            return lead_match.group(2).strip(), True
        return text, False

    before = match.group(1).strip()
    after = match.group(3).strip()

    if not after:
        return before, True

    words_after = after.split()
    words_before = before.split()

    # 1. Check if 'after' re-states a phrase or clause from 'before' (e.g. 'come to ...')
    for n in range(min(5, len(words_after)), 0, -1):
        lead_phrase = " ".join(words_after[:n]).lower()
        before_lower = before.lower()
        idx = before_lower.rfind(lead_phrase)
        if idx != -1:
            prefix = before[:idx].strip()
            # If prefix is empty or just greetings/filler ('hey', 'hello', 'hi')
            if not prefix or re.match(
                r"^(hey|hello|hi|dear)(\s+(hey|hello|hi))?$", prefix, re.IGNORECASE
            ):
                return after, True
            return f"{prefix} {after}".strip(), True

    # 2. Check if 'after' is a short fragment substitution (e.g. '5 pm' -> '6 pm', '10 minutes' -> '20 minutes')
    if len(words_after) <= 3 and len(words_before) >= len(words_after):
        num_replace = len(words_after)
        prefix_words = words_before[:-num_replace]
        return " ".join(prefix_words + words_after), True

    # 3. If after is a substantial clause/sentence (>= 3 words), treat after as the full intended message
    if len(words_after) >= 3:
        return after, True

    return after, True


def clean_dictated_message(message: str) -> str:
    """
    Detect and resolve verbal self-corrections / speech repairs in dictated text or messages.
    Extracts the speaker's final intended correction when repair cues are present.
    E.g.:
    - 'hey hello come to martin luther block oh sorry come to turing block' -> 'come to turing block'
    - 'we are meeting at 5 pm wait no 6 pm' -> 'we are meeting at 6 pm'
    - 'I will reach in 10 minutes actually 20 minutes' -> 'I will reach in 20 minutes'
    - 'let's go to subway scratch that let's go to dominos' -> 'let's go to dominos'
    """
    if not message or not message.strip():
        return message
    curr = message.strip().strip("'\"").strip()
    for _ in range(5):
        cleaned, changed = _clean_single_repair(curr)
        if not changed or cleaned == curr:
            break
        curr = cleaned
    return curr


def _contact_match_score(query_norm: str, cand_norm: str) -> float:
    """
    Compute a character-level similarity and match score (0.0 to 1.0)
    between a search query and a candidate contact name.
    Treats uppercase and lowercase identically.
    Supports character-by-character prefixes, substrings, word tokens, and fuzzy sequence matching.
    """
    if not query_norm or not cand_norm:
        return 0.0

    q = query_norm.lower().strip()
    c = cand_norm.lower().strip()

    # 1. Exact match (case-insensitive)
    if q == c:
        return 1.0

    # 2. Character-by-character prefix match (e.g. 'yash' matches 'yash baniya', 'yash bani' matches 'yash baniya')
    if c.startswith(q) or q.startswith(c):
        length_ratio = min(len(q), len(c)) / max(len(q), len(c))
        return 0.90 + 0.09 * length_ratio

    # 3. Substring match (e.g. 'baniya' in 'yash baniya')
    if q in c or c in q:
        length_ratio = min(len(q), len(c)) / max(len(q), len(c))
        return 0.80 + 0.09 * length_ratio

    # 4. Word-token subset match (e.g. 'baniya yash' vs 'yash baniya')
    q_words = set(q.split())
    c_words = set(c.split())
    if q_words and (q_words.issubset(c_words) or c_words.issubset(q_words)):
        return 0.85

    # 5. Character-by-character sequence ratio (handles typos like 'yash banya' vs 'yash baniya')
    import difflib
    return difflib.SequenceMatcher(None, q, c).ratio()


def _extract_whatsapp_candidates(ocr_output: str, norm_query: str, scale: float) -> list[dict]:
    """
    Parse OCR text from WhatsApp left sidebar and collect matching contact rows.
    Properly handles macOS Retina scaling, boundaries above 'Groups in common'/'Messages',
    and character-by-character case-insensitive matching.
    """
    q_norm = re.sub(r'[^a-zA-Z0-9\s]', '', norm_query).lower().strip()
    q_words = [w for w in q_norm.split() if len(w) >= 2]

    # Find boundary where Groups in common or Messages begins (direct contacts appear above them)
    cutoff_y = 999999
    for line in ocr_output.splitlines():
        if "->" not in line:
            continue
        coords, text = line.split("->", 1)
        t_clean = text.strip().lower()
        if t_clean in ("messages", "groups in common", "groups") or "groups in common" in t_clean:
            m = re.match(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', coords.strip())
            if m:
                cutoff_y = min(cutoff_y, int(m.group(2)))

    # Search bar is at y ~ 100pt (py ~ 200 in Retina 2x).
    # Results start at y ~ 150pt (py ~ 300 in Retina 2x).
    # min_y = int(120 * scale) ensures contacts right below the search bar are not skipped.
    min_y = int(120 * scale)
    max_x = int(500 * scale)

    candidates = []
    seen = set()

    for line in ocr_output.splitlines():
        if "->" not in line:
            continue
        coords, text = line.split("->", 1)
        text = text.strip()
        m = re.match(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', coords.strip())
        if not m:
            continue
        px, py, pw, ph = map(int, m.groups())
        if px < max_x and min_y < py < cutoff_y:
            t_lower = text.lower()
            if any(k in t_lower for k in [
                "yesterday", "resume", "maps", "pdf", "unread", "starred", "archived", "chats",
                "more", "communities", "media", "calls", "in this group", "in common", "group"
            ]):
                continue
            t_norm = re.sub(r'[^a-zA-Z0-9\s]', '', text).lower().strip()
            if not t_norm:
                continue

            score = _contact_match_score(q_norm, t_norm)
            prefix_match = t_norm.startswith(q_norm) or q_norm.startswith(t_norm)
            word_match = any(w in t_norm for w in q_words) or any(w in q_norm for w in t_norm.split())

            if prefix_match or word_match or score >= 0.5:
                if t_norm not in seen:
                    seen.add(t_norm)
                    lx = int((px + pw / 2) / scale)
                    ly = int((py + ph / 2) / scale)
                    candidates.append({"name": text, "norm": t_norm, "x": lx, "y": ly, "score": score})

    return candidates


def _resolve_whatsapp_candidates(candidates: list[dict], query: str) -> tuple[str, list[dict]]:
    """Classify extracted candidates as EXACT, AMBIGUOUS, or NOT_FOUND."""
    if not candidates:
        return "NOT_FOUND", []

    import difflib

    q_norm = re.sub(r'[^a-zA-Z0-9\s]', '', query).lower().strip()
    q_words = [w for w in q_norm.split() if w]

    # Helper to check if a candidate's name is an exact match for query
    def is_exact(cand: dict) -> bool:
        norm = cand.get("norm", "").strip()
        name = cand.get("name", "").strip().lower()
        return norm == q_norm or name == query.strip().lower() or cand.get("score", 0) == 1.0

    exact_matches = [c for c in candidates if is_exact(c)]

    if len(exact_matches) > 1:
        # Multiple contacts with the exact same name -> truly ambiguous
        return "AMBIGUOUS", exact_matches

    if len(exact_matches) == 1:
        exact_cand = exact_matches[0]
        # Check if any OTHER candidate is a peer near-identical variant / typo
        # with the same word structure (e.g. query 'satyam' matching 'Satyam' (exact)
        # while another contact is 'Satyma' (peer variant with 1 word)).
        # If there are peer variants like 'Satyam' vs 'Satyma', ask the user!
        # But if the other candidates are multi-word extensions like 'Satyam Brother'
        # or 'Satyam College' (extra distinguishing words), the exact full name wins!
        peer_variants = []
        for c in candidates:
            if c is exact_cand or is_exact(c):
                continue
            c_norm = c.get("norm", "").strip()
            c_words = [w for w in c_norm.split() if w]
            # Peer variant condition:
            # 1) Same number of words (e.g. 1 word vs 1 word)
            # 2) High character similarity / typo (e.g. 'satyam' vs 'satyma')
            if len(c_words) == len(q_words):
                sim = difflib.SequenceMatcher(None, q_norm, c_norm).ratio()
                is_transposition = len(q_norm) == len(c_norm) and sorted(q_norm) == sorted(c_norm)
                if sim >= 0.80 or is_transposition:
                    peer_variants.append(c)

        if peer_variants:
            # We have the exact match and one or more peer variants (e.g. 'Satyam' and 'Satyma')
            return "AMBIGUOUS", [exact_cand] + peer_variants

        # No peer variants; other candidates (if any) are extensions like 'Satyam Brother'
        return "EXACT", [exact_cand]

    candidates.sort(key=lambda c: c.get("score", 0), reverse=True)
    top = candidates[0]

    # Single matching contact on screen
    if len(candidates) == 1:
        if top.get("score", 0) >= 0.5:
            return "EXACT", [top]
        return "NOT_FOUND", []

    second = candidates[1]
    # If the top candidate is a clear winner (score >= 0.8 and >= 0.15 margin over second)
    if top.get("score", 0) >= 0.8 and (top["score"] - second.get("score", 0) >= 0.15):
        return "EXACT", [top]

    # Multiple close candidates -> halt for owner clarification
    return "AMBIGUOUS", candidates


def _find_whatsapp_contacts(query: str) -> tuple[str, list[dict]]:
    """
    Search WhatsApp for contact candidates using fast OCR and classify matching results.
    Returns:
        (status, contacts) where:
        - status: 'EXACT' (single clear match), 'AMBIGUOUS' (multiple distinct matches), or 'NOT_FOUND'.
        - contacts: list of dicts [{'name': ..., 'x': ..., 'y': ...}]
    """
    from pathlib import Path

    # 1. Phonetic name normalization (e.g. 'Avinash' / 'Avdhesh' / 'avnsish' -> 'Avnish', 'Rishabh' -> 'Rishab')
    alias_map = {
        "avinash": "avnish",
        "avdhesh": "avnish",
        "avnsish": "avnish",
        "awdesh": "avnish",
        "avneesh": "avnish",
        "abnesh": "avnish",
        "rishabh": "rishab",
        "rishav": "rishab",
    }
    q_lower = query.lower().strip()
    norm_query = alias_map.get(q_lower, query)
    norm_query = re.sub(r'\b(avinash|avdhesh|awdesh|avneesh|abnesh|avnsish)\b', 'avnish', norm_query, flags=re.IGNORECASE)
    norm_query = re.sub(r'\brishabh\b', 'rishab', norm_query, flags=re.IGNORECASE)
    clean = norm_query.replace('"', '\\"').strip()
    script = f'''
    tell application "WhatsApp" to activate
    delay 0.15
    tell application "System Events"
        tell process "WhatsApp"
            set frontmost to true
            keystroke "f" using {{command down}} -- Focus WhatsApp search bar without touching Escape
            delay 0.15
            keystroke "a" using {{command down}}
            key code 51 -- Delete
            keystroke "{clean}"
            delay 0.6
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script], capture_output=True, timeout=6)
    time.sleep(0.3)

    shot_path = "/tmp/wa_search_contacts.png"
    try:
        from blacky.tools.macos import capture_display_screen
        capture_display_screen(shot_path, app_name="WhatsApp")
    except Exception:
        try:
            subprocess.run(["screencapture", "-x", shot_path], check=True)
        except Exception:
            return "NOT_FOUND", []

    ocr_bin = Path(__file__).resolve().parent.parent / "bin" / "ocr_fast"
    if not ocr_bin.exists():
        ocr_bin = Path("/tmp/ocr_fast")
    if not ocr_bin.exists():
        return "NOT_FOUND", []

    try:
        out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
    except Exception:
        return "NOT_FOUND", []

    from blacky.tools.macos import get_screen_scale_factor
    scale = get_screen_scale_factor(shot_path)

    candidates = _extract_whatsapp_candidates(out, norm_query, scale)

    # 2. Single-character progressive backoff search if initial search returned no results
    if not candidates and len(clean) >= 3:
        for length in range(len(clean) - 1, 1, -1):
            sub_term = clean[:length]
            sub_script = f'''
            tell application "WhatsApp" to activate
            delay 0.1
            tell application "System Events"
                tell process "WhatsApp"
                    set frontmost to true
                    keystroke "f" using {{command down}}
                    delay 0.1
                    keystroke "a" using {{command down}}
                    key code 51 -- Delete
                    keystroke "{sub_term}"
                    delay 0.4
                end tell
            end tell
            '''
            subprocess.run(["osascript", "-e", sub_script], capture_output=True, timeout=6)
            time.sleep(0.2)
            try:
                from blacky.tools.macos import capture_display_screen
                capture_display_screen(shot_path, app_name="WhatsApp")
                out = subprocess.check_output([str(ocr_bin), shot_path], text=True)
            except Exception:
                continue

            if "no results" in out.lower():
                continue

            candidates = _extract_whatsapp_candidates(out, norm_query, scale)
            if candidates:
                break

    return _resolve_whatsapp_candidates(candidates, norm_query)


_LAST_DISAMBIGUATION_CANDIDATES: list[dict] = []
_CURRENT_ACTIVE_CHAT: str = ""


def set_last_disambiguation_candidates(candidates: list[dict]) -> None:
    """Public setter for pending disambiguation candidates (used by the agent task flow)."""
    global _LAST_DISAMBIGUATION_CANDIDATES
    _LAST_DISAMBIGUATION_CANDIDATES = list(candidates or [])


def _resolve_contact_ordinal(contact: str) -> str:
    """If contact is an ordinal choice like 'second' or '1st', resolve to candidate name."""
    global _LAST_DISAMBIGUATION_CANDIDATES
    c_lower = contact.lower().strip()
    clean = re.sub(r'^(the|number)\s+', '', c_lower).strip()
    if clean in ("1", "first", "first one", "1st", "1st one", "one") and len(_LAST_DISAMBIGUATION_CANDIDATES) >= 1:
        return _LAST_DISAMBIGUATION_CANDIDATES[0]["name"]
    if clean in ("2", "second", "second one", "2nd", "2nd one", "two") and len(_LAST_DISAMBIGUATION_CANDIDATES) >= 2:
        return _LAST_DISAMBIGUATION_CANDIDATES[1]["name"]
    if clean in ("3", "third", "third one", "3rd", "3rd one", "three") and len(_LAST_DISAMBIGUATION_CANDIDATES) >= 3:
        return _LAST_DISAMBIGUATION_CANDIDATES[2]["name"]
    if clean in ("4", "fourth", "fourth one", "4th", "4th one", "four") and len(_LAST_DISAMBIGUATION_CANDIDATES) >= 4:
        return _LAST_DISAMBIGUATION_CANDIDATES[3]["name"]
    if clean in ("5", "fifth", "fifth one", "5th", "5th one", "five") and len(_LAST_DISAMBIGUATION_CANDIDATES) >= 5:
        return _LAST_DISAMBIGUATION_CANDIDATES[4]["name"]
    return contact


@registry.register
def whatsapp_open_chat(contact: str) -> str:
    """
    Open a chat with a specific contact name (e.g. 'Satyam') or phone number in WhatsApp on macOS.
    Use this when the user asks to open WhatsApp and search for or open a chat with someone.
    Pass contact='me' to open the user's own chat ("Message yourself").
    """
    global _LAST_DISAMBIGUATION_CANDIDATES
    contact = clean_dictated_message(contact)
    contact = _resolve_contact_ordinal(contact)
    if not _ensure_whatsapp_running():
        err = "Could not open WhatsApp. Please ensure WhatsApp is installed in /Applications/WhatsApp.app."
        registry.log_call("whatsapp_open_chat", {"contact": contact}, err, success=False)
        return err

    # The user's own conversation ("me", "myself") is a real chat, not a search term.
    if _is_self_target(contact):
        res = _open_self_chat()
        registry.log_call("whatsapp_open_chat", {"contact": contact}, res, success=res.startswith("Opened"))
        return res

    clean_contact = contact.replace('"', '\\"').strip()
    if not clean_contact or clean_contact.lower() in ("whatsapp", "app", "chats"):
        # No recipient given: the app is open, but no chat was opened. Report this
        # as NOT done so the agent never declares a messaging task complete.
        res = (
            "Opened WhatsApp in full screen, but NO contact was specified so no chat was opened. "
            "If the user asked to message/text someone, call "
            "whatsapp_send_message(contact=<name>, message=<text>) with the recipient "
            "(use contact='me' for the user's own chat). Do NOT report the task as completed."
        )
        registry.log_call("whatsapp_open_chat", {"contact": contact}, res, success=False)
        return res

    phone = _clean_phone(contact)
    if phone:
        # Use direct URL scheme for phone numbers
        url = f"whatsapp://send?phone={phone}"
        subprocess.run(["open", url], capture_output=True)
        time.sleep(0.5)
        from blacky.tools.macos import make_window_fullscreen
        make_window_fullscreen("WhatsApp")
        time.sleep(0.3)
        res = f"Opened WhatsApp chat with phone number: {phone}"
        registry.log_call("whatsapp_open_chat", {"contact": contact}, res, success=True)
        return res

    # Use UI search and Vision OCR click for contact names
    from blacky.tools.macos import screen_click_text, mouse_click

    # Search and disambiguate contact matches
    status, candidates = _find_whatsapp_contacts(clean_contact)

    if status == "AMBIGUOUS":
        _LAST_DISAMBIGUATION_CANDIDATES = candidates
        names = [c["name"] for c in candidates]
        res = (
            f"AMBIGUOUS_CONTACTS: Found multiple contacts matching '{contact}': "
            + ", ".join(repr(n) for n in names)
            + f". Please ask the owner: 'I found {len(names)} contacts matching \"{contact}\" ({', '.join(names)}). Which one would you like to open or message?' Do NOT select any contact or send any message until the owner confirms."
        )
        registry.log_call("whatsapp_open_chat", {"contact": contact}, res, success=False)
        return res

    if status == "EXACT":
        _LAST_DISAMBIGUATION_CANDIDATES = []
        target = candidates[0]
        mouse_click(target["x"], target["y"])
        time.sleep(0.4)
        _CURRENT_ACTIVE_CHAT = target["name"]
        _focus_whatsapp_composer()
        res = f"Opened WhatsApp chat for contact: '{target['name']}'"
        registry.log_call("whatsapp_open_chat", {"contact": contact}, res, success=True)
        return res

    # 3. Fallback: try screen_click_text
    click_res = screen_click_text(contact, app_name="WhatsApp")
    if "Found" in click_res:
        time.sleep(0.3)
        _focus_whatsapp_composer()
        res = f"Opened WhatsApp chat for contact: '{contact}'"
        registry.log_call("whatsapp_open_chat", {"contact": contact}, res, success=True)
        return res

    err = f"Contact '{contact}' not found in WhatsApp."
    registry.log_call("whatsapp_open_chat", {"contact": contact}, err, success=False)
    return err


@registry.register
def whatsapp_send_message(contact: str, message: str) -> str:
    """
    Send a message to a contact name (e.g. 'Satyam') or phone number on WhatsApp.
    ALWAYS use this tool when the user wants to text, chat, or send a message on WhatsApp.
    Pass contact='me' when the user says 'message me' / 'text me' (their own chat).
    NEVER use mobile_send_imessage for WhatsApp!
    """
    contact = clean_dictated_message(contact)
    contact = _resolve_contact_ordinal(contact)
    message = clean_dictated_message(message)
    if not (contact or "").strip():
        err = (
            "ERROR: No recipient was specified, so NOTHING was sent. "
            "Call whatsapp_send_message again with contact=<name> "
            "(use contact='me' for the user's own chat)."
        )
        registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, err, success=False)
        return err
    if not (message or "").strip():
        err = "ERROR: The message text was empty, so NOTHING was sent."
        registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, err, success=False)
        return err
    if not _ensure_whatsapp_running():
        err = "Could not open WhatsApp. Please ensure WhatsApp is installed."
        registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, err, success=False)
        return err

    phone = _clean_phone(contact)
    if phone:
        import urllib.parse
        encoded_msg = urllib.parse.quote(message)
        url = f"whatsapp://send?phone={phone}&text={encoded_msg}"
        subprocess.run(["open", url], capture_output=True)
        time.sleep(1.2)
        from blacky.tools.macos import make_window_fullscreen
        make_window_fullscreen("WhatsApp")
        time.sleep(0.4)
        _focus_whatsapp_composer()
        time.sleep(0.2)
        whatsapp_click_send_button()
        res = f"Message sent to {contact} via WhatsApp: '{message}'"
        registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, res, success=True)
        return res

    global _CURRENT_ACTIVE_CHAT

    # "me" / "myself" -> the user's own conversation, which is a real chat.
    if _is_self_target(contact):
        open_res = _open_self_chat()
        if not open_res.startswith("Opened"):
            registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, open_res, success=False)
            return open_res
        time.sleep(0.35)
        target_label = "your own chat"
    else:
        # For contact names, open chat if not already active
        target_norm = re.sub(r'[^a-zA-Z0-9\s]', '', contact).lower().strip()
        curr_norm = re.sub(r'[^a-zA-Z0-9\s]', '', _CURRENT_ACTIVE_CHAT).lower().strip()
        if not (curr_norm and (target_norm in curr_norm or curr_norm in target_norm)):
            open_res = whatsapp_open_chat(contact)
            if not open_res.startswith("Opened WhatsApp chat"):
                registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, open_res, success=False)
                return open_res
            time.sleep(0.4)
        target_label = contact

    # Explicitly focus message composer text area
    _focus_whatsapp_composer()
    time.sleep(0.2)

    _set_clipboard(message)

    script = '''
    tell application "WhatsApp" to activate
    delay 0.2
    tell application "System Events"
        tell process "WhatsApp"
            -- Select any accidental draft in composer and paste message
            keystroke "a" using {command down}
            delay 0.05
            key code 51 -- Delete existing draft
            delay 0.05
            keystroke "v" using {command down}
            delay 0.25
            key code 36 -- Return to send message
            delay 0.3
        end tell
    end tell
    '''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    time.sleep(0.45)

    verified = _verify_message_in_chat(message)
    if proc.returncode != 0:
        res = (
            f"Could not send the message to {target_label} — macOS automation error: "
            f"{proc.stderr.strip() or 'unknown error'}. NOTHING was sent."
        )
        registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, res, success=False)
        return res

    if verified:
        res = f"Message successfully sent to {target_label} on WhatsApp: '{message}' (verified in the chat)."
    else:
        res = (
            f"Sent the message to {target_label} on WhatsApp: '{message}'. "
            "I could not visually confirm it in the chat — please check the screen before assuming it was delivered."
        )
    registry.log_call("whatsapp_send_message", {"contact": contact, "message": message}, res, success=True)
    return res


@registry.register
def whatsapp_start_video_call(contact: str = "") -> str:
    """
    Start a WhatsApp Video Call with a specified contact name (e.g. 'Satyam'),
    or with the currently active WhatsApp chat if contact is empty.
    ALWAYS use this when the user says 'video call on WhatsApp' or 'click on video call'.
    """
    if contact.strip():
        contact = clean_dictated_message(contact)
        contact = _resolve_contact_ordinal(contact)
    if not _ensure_whatsapp_running():
        err = "Could not open WhatsApp. Please ensure WhatsApp is installed."
        registry.log_call("whatsapp_start_video_call", {"contact": contact}, err, success=False)
        return err

    # If contact provided, verify if chat is already open; if not, open it
    if contact.strip():
        check_script = '''
        tell application "System Events"
            tell process "WhatsApp"
                repeat with mb in (menu bar items of menu bar 1)
                    if (name of mb as string) contains "Chat" then
                        repeat with mi in (menu items of menu 1 of mb)
                            if (name of mi as string) contains "Video Call" then
                                return (value of attribute "AXEnabled" of mi as string)
                            end if
                        end repeat
                    end if
                end repeat
                return "false"
            end tell
        end tell
        '''
        check_proc = subprocess.run(["osascript", "-e", check_script], capture_output=True, text=True)
        if "true" not in check_proc.stdout.lower():
            open_res = whatsapp_open_chat(contact)
            if not open_res.startswith("Opened WhatsApp chat"):
                registry.log_call("whatsapp_start_video_call", {"contact": contact}, open_res, success=False)
                return open_res
            time.sleep(0.5)

    # Click Video Call menu item under Chat menu
    script = '''
    tell application "WhatsApp" to activate
    delay 0.3
    tell application "System Events"
        tell process "WhatsApp"
            repeat with mb in (menu bar items of menu bar 1)
                if (name of mb as string) contains "Chat" then
                    repeat with mi in (menu items of menu 1 of mb)
                        if (name of mi as string) contains "Video Call" then
                            click mi
                            return "Video Call started"
                        end if
                    end repeat
                end if
            end repeat
            return "Video Call menu item not currently available"
        end tell
    end tell
    '''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    out = proc.stdout.strip()
    if proc.returncode == 0 and "Video Call started" in out:
        target_name = f"with '{contact}'" if contact.strip() else "in active chat"
        res = f"WhatsApp Video Call initiated {target_name}."
        registry.log_call("whatsapp_start_video_call", {"contact": contact}, res, success=True)
        return res
    else:
        err = f"Could not start Video Call: {proc.stderr.strip() or out}"
        registry.log_call("whatsapp_start_video_call", {"contact": contact}, err, success=False)
        return err


@registry.register
def whatsapp_start_voice_call(contact: str = "") -> str:
    """
    Start a WhatsApp Voice / Audio Call with a specified contact name (e.g. 'Satyam'),
    or with the currently active WhatsApp chat if contact is empty.
    """
    if contact.strip():
        contact = clean_dictated_message(contact)
        contact = _resolve_contact_ordinal(contact)
    if not _ensure_whatsapp_running():
        err = "Could not open WhatsApp. Please ensure WhatsApp is installed."
        registry.log_call("whatsapp_start_voice_call", {"contact": contact}, err, success=False)
        return err

    # If contact provided, verify if chat is already open; if not, open it
    if contact.strip():
        check_script = '''
        tell application "System Events"
            tell process "WhatsApp"
                repeat with mb in (menu bar items of menu bar 1)
                    if (name of mb as string) contains "Chat" then
                        repeat with mi in (menu items of menu 1 of mb)
                            if (name of mi as string) contains "Video Call" then
                                return (value of attribute "AXEnabled" of mi as string)
                            end if
                        end repeat
                    end if
                end repeat
                return "false"
            end tell
        end tell
        '''
        check_proc = subprocess.run(["osascript", "-e", check_script], capture_output=True, text=True)
        if "true" not in check_proc.stdout.lower():
            open_res = whatsapp_open_chat(contact)
            if not open_res.startswith("Opened WhatsApp chat"):
                registry.log_call("whatsapp_start_voice_call", {"contact": contact}, open_res, success=False)
                return open_res
            time.sleep(0.5)

    # Click Voice Call menu item under Chat menu
    script = '''
    tell application "WhatsApp" to activate
    delay 0.3
    tell application "System Events"
        tell process "WhatsApp"
            repeat with mb in (menu bar items of menu bar 1)
                if (name of mb as string) contains "Chat" then
                    repeat with mi in (menu items of menu 1 of mb)
                        if (name of mi as string) contains "Voice Call" then
                            click mi
                            return "Voice Call started"
                        end if
                    end repeat
                end if
            end repeat
            return "Voice Call menu item not currently available"
        end tell
    end tell
    '''
    proc = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    out = proc.stdout.strip()
    if proc.returncode == 0 and "Voice Call started" in out:
        target_name = f"with '{contact}'" if contact.strip() else "in active chat"
        res = f"WhatsApp Voice Call initiated {target_name}."
        registry.log_call("whatsapp_start_voice_call", {"contact": contact}, res, success=True)
        return res
    else:
        err = f"Could not start Voice Call: {proc.stderr.strip() or out}"
        registry.log_call("whatsapp_start_voice_call", {"contact": contact}, err, success=False)
        return err
