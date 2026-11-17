"""
Command Simplifier & Natural Language Intent Distiller for BlackyAgent.

Transforms long, rambling, conversational, repetitive, or voice-dictated explanations
into crisp, clear, direct instructions suitable for deterministic fast-paths
and compact local AI models.

Example:
    Input:  "I have a task that you have to open the brave and search for the YouTube
             and inside the YouTube you have to search for the bulleya song and I have
             to that you have to play it song and play that song bulleya"
    Output: "play bulleya song on youtube in Brave Browser"
"""

import re
from typing import Optional


class CommandSimplifier:
    """Distills conversational explanations into clean, actionable instructions."""

    @classmethod
    def simplify(cls, text: str) -> str:
        """
        Simplify and distill a user instruction.
        Returns a clean, canonical command string.
        """
        clean = " ".join((text or "").strip().split())
        if not clean:
            return ""

        # Normalize curly and smart quotes
        clean = clean.replace("“", "\"").replace("”", "\"").replace("‘", "'").replace("’", "'")
        # Normalize common typos
        clean = re.sub(r"\b(?:serch|saerch|seach|srch|serach)\b", "search", clean, flags=re.I)
        clean = re.sub(r"\b(?:whastapp|whatsap|watsapp|watshap|wapp|whats\s+app)\b", "whatsapp", clean, flags=re.I)
        clean = re.sub(r"\b(?:messege|massege|messge|msge)\b", "message", clean, flags=re.I)
        clean = re.sub(r"\b(?:leetocde|leetcdoe|leatcode|letcode|leetcde)\b", "leetcode", clean, flags=re.I)
        clean = re.sub(r"\b(?:youtub|youtbe|yotube)\b", "youtube", clean, flags=re.I)
        clean = re.sub(r"\b(?:chrom|crome)\b", "chrome", clean, flags=re.I)
        lower = clean.lower()

        # Extract target browser if mentioned anywhere
        browser = cls._extract_browser(lower)

        # 0. Search & Open / Navigation (e.g. 'search here youtube and open it' -> 'open youtube')
        search_open = cls._simplify_search_and_open(clean, lower, browser)
        if search_open:
            return search_open

        # 1. Media / YouTube Play (e.g. open brave search youtube and play bulleya song)
        media_play = cls._simplify_media_play(clean, lower, browser)
        if media_play:
            return media_play

        # 2. YouTube Search without play intent
        yt_search = cls._simplify_youtube_search(lower, browser)
        if yt_search:
            return yt_search

        # 3. Web Search (Google / DuckDuckGo)
        web_search = cls._simplify_web_search(lower, browser)
        if web_search:
            return web_search

        # 4. WhatsApp Rambling
        wa_distilled = cls._simplify_whatsapp(clean, lower)
        if wa_distilled:
            return wa_distilled

        # 5. LeetCode Rambling
        lc_distilled = cls._simplify_leetcode(clean, lower)
        if lc_distilled:
            return lc_distilled

        # 6. General Preamble & Repetition Stripping
        return cls._strip_conversational_preamble(clean)

    @staticmethod
    def _extract_browser(lower: str) -> str:
        """Extract canonical browser name if mentioned in the prompt."""
        b_match = re.search(r"\b(brave(?:\s+browser)?|chrome|google\s+chrome|safari|firefox|edge)\b", lower)
        if not b_match:
            return ""
        raw = b_match.group(1).lower()
        if "brave" in raw:
            return "Brave Browser"
        if "chrome" in raw:
            return "Google Chrome"
        if "safari" in raw:
            return "Safari"
        if "firefox" in raw:
            return "Firefox"
        if "edge" in raw:
            return "Microsoft Edge"
        return ""

    @staticmethod
    def _simplify_search_and_open(clean: str, lower: str, browser: str) -> Optional[str]:
        """
        Distill commands like 'search here youtube and open it' -> 'open youtube'.
        """
        m = re.match(
            r"^(?:please\s+)?(?:search|find)\s+(?:here|right\s+here|in\s+here|on\s+this|on\s+screen)?\s*(?:for\s+)?([a-zA-Z0-9_\s]+?)\s+(?:and\s+)?(?:open(?:\s+it)?|launch(?:\s+it)?|chalao|kholo)$",
            lower,
        )
        if not m:
            m = re.match(
                r"^([a-zA-Z0-9_\s]+?)\s+(?:search|find)\s+(?:here|right\s+here|in\s+here)?\s+(?:and\s+)?(?:open(?:\s+it)?|launch(?:\s+it)?)$",
                lower,
            )
        if m:
            target = m.group(1).strip()
            target = re.sub(r"^(?:the|a|an)\s+", "", target).strip()
            target = re.sub(r"^(?:here|right\s+here|in\s+here|on\s+this)\s+", "", target).strip()
            known_apps = {
                "youtube", "whatsapp", "chrome", "google chrome", "brave", "brave browser",
                "safari", "spotify", "code", "vscode", "vs code", "cursor", "finder", "notes",
                "calculator", "blinkit", "amazon", "github", "netflix", "leetcode", "google"
            }
            b_suffix = f" in {browser}" if browser else ""
            if target in known_apps:
                return f"open {target}{b_suffix}"
            return f"search for {target} on youtube{b_suffix}"
        return None

    @staticmethod
    def _simplify_media_play(clean: str, lower: str, browser: str) -> Optional[str]:
        """
        Distill rambling multi-clause YouTube playback commands.
        Handles phrasings like:
        - 'I have a task that you have to open the brave and search for the YouTube
           and inside the YouTube you have to search for the bulleya song and I have
           to that you have to play it song and play that song bulleya'
        - 'open chrome and go to youtube and search for kesariya and play it'
        - 'open youtube and play lofi beats'
        """
        has_yt = bool(re.search(r"\b(?:youtube|yt)\b", lower))
        has_play = bool(re.search(r"\b(?:play|watch|listen|listen\s+to|start|chalao|bajao|sunao)\b", lower))
        has_media_word = bool(re.search(r"\b(?:song|music|track|playlist|video|audio|lofi|podcast)\b", lower))
        if not (has_play and (has_yt or has_media_word)):
            return None

        # Split into sequential clauses by conjunctions
        clauses = re.split(r"\s+(?:and\s+also|and\s+then|and|then|also|aur|phir)\s+", lower)

        play_queries = []
        for c in clauses:
            c = c.strip()
            # Match: search for ...
            m_s = re.search(r"\b(?:search\s+(?:for\s+)?|find\s+)(?:the\s+|a\s+)?(.+?)$", c)
            if m_s:
                target = m_s.group(1).strip()
                target = re.sub(r"^(?:the|a|an)\s+", "", target).strip()
                target = re.sub(r"\s+(?:on|in)\s+(?:youtube|yt|brave|chrome|safari).*$", "", target).strip()
                if target not in ("youtube", "the youtube", "yt", "brave", "chrome", "safari", "firefox", "browser", ""):
                    play_queries.append(target)

            # Match: play ...
            m_p = re.search(r"\b(?:play|watch|listen\s+to|listen|chalao|bajao)\s+(?:that\s+|the\s+|it\s+)?(?:song\s+|video\s+|track\s+)?(.+?)$", c)
            if m_p:
                target = m_p.group(1).strip()
                target = re.sub(r"^(?:the|a|an)\s+", "", target).strip()
                target = re.sub(r"\s+(?:on|in)\s+(?:youtube|yt|brave|chrome|safari).*$", "", target).strip()
                if target not in ("youtube", "the youtube", "yt", "brave", "chrome", "safari", "firefox", "browser", "it song", "song", "video", "it", "this", ""):
                    play_queries.append(target)

        if not play_queries:
            # Fallback regex for direct phrasings: play <song> [on youtube] [in browser]
            m_direct = re.search(r"\b(?:play|chalao|bajao)\s+(?:the\s+|a\s+)?(.+?)(?:\s+(?:on|in)\s+youtube|\s+(?:in|on)\s+(?:brave|chrome|safari)|$)", lower)
            if m_direct:
                cand = m_direct.group(1).strip()
                cand = re.sub(r"^(?:the|a|an)\s+", "", cand).strip()
                cand = re.sub(r"\s+(?:on|in)\s+(?:youtube|yt|brave|chrome|safari).*$", "", cand).strip()
                if cand and cand not in ("song", "video", "it"):
                    play_queries.append(cand)

        if play_queries:
            # Prefer queries that explicitly retain 'song' or the most specific title
            play_queries.sort(key=lambda q: (len(q), "song" in q), reverse=True)
            best_q = play_queries[0]
            b_suffix = f" in {browser}" if browser else ""
            return f"play {best_q} on youtube{b_suffix}"

        return None

    @staticmethod
    def _simplify_youtube_search(lower: str, browser: str) -> Optional[str]:
        """Distill rambling YouTube search commands (without play intent)."""
        has_yt = bool(re.search(r"\b(?:youtube|yt)\b", lower))
        has_search = bool(re.search(r"\b(?:search|find|look\s+for|dhoondho)\b", lower))
        has_play = bool(re.search(r"\b(?:play|watch|listen|listen\s+to|chalao|bajao)\b", lower))
        if not (has_yt and has_search and not has_play):
            return None

        clauses = re.split(r"\s+(?:and\s+also|and\s+then|and|then|also|aur|phir)\s+", lower)
        for c in clauses:
            m_s = re.search(r"\b(?:search\s+(?:for\s+)?|find\s+)(?:the\s+|a\s+)?(.+?)$", c)
            if m_s:
                target = m_s.group(1).strip()
                target = re.sub(r"^(?:the|a|an)\s+", "", target).strip()
                target = re.sub(r"^(?:here|right\s+here|in\s+here|on\s+this)\s+", "", target, flags=re.I).strip()
                target = re.sub(r"\s+(?:on|in)\s+(?:youtube|yt|brave|chrome|safari).*$", "", target).strip()
                b_suffix = f" in {browser}" if browser else ""
                if target in ("youtube", "the youtube", "yt"):
                    return f"open youtube{b_suffix}"
                if target not in ("brave", "chrome", "safari", "firefox", "browser", ""):
                    return f"search for {target} on youtube{b_suffix}"
        return None

    @staticmethod
    def _simplify_web_search(lower: str, browser: str) -> Optional[str]:
        """Distill Google or general web searches."""
        has_google = bool(re.search(r"\b(?:google|duckduckgo)\b", lower))
        has_search = bool(re.search(r"\b(?:search|find|look\s+for|what\s+is|who\s+is|tell\s+me\s+about)\b", lower))
        if not (has_google and has_search):
            return None

        site = "duckduckgo" if "duckduckgo" in lower else "google"
        clauses = re.split(r"\s+(?:and\s+also|and\s+then|and|then|also|aur|phir)\s+", lower)
        for c in clauses:
            m_s = re.search(r"\b(?:search\s+(?:for\s+)?|find\s+)(?:the\s+|a\s+)?(.+?)$", c)
            if m_s:
                target = m_s.group(1).strip()
                target = re.sub(r"^(?:the|a|an)\s+", "", target).strip()
                target = re.sub(r"\s+(?:on|in)\s+(?:google|duckduckgo|brave|chrome|safari).*$", "", target).strip()
                if target not in ("google", "the google", "duckduckgo", "brave", "chrome", "safari", "firefox", "browser", ""):
                    b_suffix = f" in {browser}" if browser else ""
                    return f"search for {target} on {site}{b_suffix}"
        return None

    @staticmethod
    def _simplify_whatsapp(clean: str, lower: str) -> Optional[str]:
        """Distill verbose WhatsApp send/open instructions."""
        if "whatsapp" not in lower and "whats app" not in lower and "wp" not in lower:
            return None

        # Check if contains conversational preambles
        if any(lower.startswith(p) for p in ("i have a task", "can you please", "you have to", "i want you to")):
            # Extract contact and message using existing agent logic or simplified structure
            # e.g. "open whatsapp and find X and send him message that Y"
            m = re.search(
                r"\b(?:text|message|msg|send(?:\s+a)?\s+message\s+to)\s+(?:to\s+)?([a-zA-Z0-9_\s]+?)\s+(?:that|saying|with|to|:)\s+(.+?)(?:\s+(?:and\s+)?send(?:\s+it|\s+him|\s+her|\s+this)?)?$",
                clean,
                re.I,
            )
            if m:
                contact = m.group(1).strip()
                msg = m.group(2).strip()
                return f"open whatsapp and text {contact} that \"{msg}\" and send"
        return None

    @staticmethod
    def _simplify_leetcode(clean: str, lower: str) -> Optional[str]:
        """Distill verbose LeetCode problem instructions."""
        is_lc = bool(re.search(r"\b(?:leetcode|leetocde|leetcdoe|leatcode|letcode|leetcde|lc)\b", lower))
        if not is_lc:
            return None

        if any(lower.startswith(p) for p in ("i have a task", "can you please", "you have to", "i want you to", "there is a task")):
            # Extract problem, language, and actions
            m_lang = re.search(r"\b(?:in\s+)?(java|python3?|py|cpp|c\+\+|javascript|js)\b(?:\s+(?:language|lang|code))?", lower)
            lang = f" in {m_lang.group(1)}" if m_lang else ""
            wants_solve = "solve" in lower or "solution" in lower
            wants_submit = "submit" in lower

            # Extract problem name between search for / solve and leetcode
            m_prob = re.search(r"\b(?:search\s+(?:for\s+)?|solve\s+)(?:the\s+|problem\s+|question\s+)?([a-zA-Z0-9_\s\+\.\-]+?)(?:\s+(?:ques|question|problem|on|in|and|solve|submit|$))", clean, re.I)
            if m_prob:
                prob = m_prob.group(1).strip()
                prob = re.sub(r"^(?:(?:q\.?|ques\.?|question\.?|problem\.?|no\.?|#)?\s*\d+[\.\)\:\-\s]+)", "", prob).strip()
                act = "solve and submit" if wants_submit else ("solve" if wants_solve else "open")
                return f"{act} {prob} on leetcode{lang}".strip()
        return None

    @staticmethod
    def _strip_conversational_preamble(text: str) -> str:
        """Strip conversational filler preambles and stuttering redundancies."""
        p = text.strip()
        p = re.sub(
            r"^(?:I\s+have\s+a\s+task\s+that\s+you\s+have\s+to\s+|I\s+have\s+a\s+request\s+that\s+|"
            r"There\s+is\s+a\s+task\s+that\s+you\s+have\s+to\s+|You\s+have\s+to\s+do\s+one\s+thing\s+|"
            r"Can\s+you\s+please\s+do\s+one\s+thing\s+for\s+me\s+|Can\s+you\s+do\s+one\s+thing\s+|"
            r"Could\s+you\s+please\s+|Will\s+you\s+please\s+|I\s+want\s+you\s+to\s+|I\s+need\s+you\s+to\s+|"
            r"You\s+have\s+to\s+|Listen\s+to\s+me\s+you\s+have\s+to\s+|Listen\s+carefully\s+|"
            r"Ek\s+kaam\s+kar\s+tujhe\s+ye\s+karna\s+hai\s+ki\s+|Ek\s+kaam\s+karo\s+|Sun\s+mere\s+bhai\s+)+",
            "",
            p,
            flags=re.I,
        ).strip()

        # Strip stuttering repetitive clauses like 'and I have to that you have to'
        p = re.sub(r"\s+and\s+I\s+have\s+to\s+(?:that\s+)?you\s+have\s+to\b", " and", p, flags=re.I)
        p = re.sub(r"\s+that\s+you\s+have\s+to\b", "", p, flags=re.I)
        return " ".join(p.split()).strip()
