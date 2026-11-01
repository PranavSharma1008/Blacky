import unittest
from blacky.tools.web import _resolve_blinkit_add_click


class TestBlinkitTools(unittest.TestCase):
    def test_blinkit_ad_filter_and_matching(self):
        sample_ocr = """
[108, 22, 70, 19] -> Brave
[598, 175, 353, 25] -> blinkit.comlsl?q=diet+coke
[367, 610, 457, 28] -> Showing results for "diet coke"
[408, 1016, 92, 16] -> 0 10 MINS
[781, 1016, 92, 16] -> 0 10 MINS
[393, 1053, 275, 23] -> Paper Boat Zero Dark
[393, 1083, 181, 19] -> Roast Coffee...
[767, 1053, 259, 19] -> Coca-cola Diet Coke
[765, 1083, 127, 19] -> Soft Drink
[1141, 1053, 283, 23] -> Bombay Banta Diets &
[393, 1191, 43, 17] -> t60
[767, 1191, 42, 17] -> E50
[1140, 1191, 43, 17] -> E40
[960, 1191, 58, 18] -> ADD
"""
        res = _resolve_blinkit_add_click(sample_ocr, "diet coke")
        self.assertIsNotNone(res)
        name, cx, cy = res
        self.assertIn("Coca-cola Diet Coke", name)
        # Should NOT match Paper Boat
        self.assertNotIn("Paper Boat", name)

    def test_blinkit_explicit_add_button_correlation(self):
        sample_ocr = """
[124, 65, 459, 27] -> Showing results for "diet coke"
[152, 507, 275, 23] -> Paper Boat Zero Dark
[525, 507, 259, 18] -> Coca-cola Diet Coke
[524, 580, 78, 17] -> 330 ml
[525, 645, 43, 17] -> E50
[717, 645, 58, 18] -> ADD
"""
        res = _resolve_blinkit_add_click(sample_ocr, "diet coke", scale=2.0)
        self.assertIsNotNone(res)
        name, cx, cy = res
        self.assertIn("Coca-cola Diet Coke", name)
        self.assertEqual(cx, int((717 + 29) / 2))
        self.assertEqual(cy, int((645 + 9) / 2))

    def test_blinkit_bingo_mad_angles_card_matching(self):
        sample_ocr = """
[421, 298, 41, 7] -> 08MIN5
[414, 317, 113, 10] -> Bingo Mad Angles
[414, 331, 127, 12] -> Achaari Masti Crisps
[414, 352, 24, 10] -> 569
[414, 378, 17, 9] -> r19
[509, 385, 28, 8] -> ADD
[601, 317, 113, 10] -> Bingo Mad Angles
[601, 332, 111, 9] -> Masala Madness_
[601, 352, 23, 10] -> 56g
[600, 385, 21, 8] -> T20
[696, 385, 28, 8] -> ADD
[414, 620, 136, 11] -> Bingo Cheese Nachos
[414, 634, 83, 11] -> with Free Dip
[414, 655, 23, 10] -> 38g
[414, 681, 17, 9] -> r19
[509, 688, 28, 9] -> ADD
"""
        # Test matching on 1x display (scale = 1.0)
        res = _resolve_blinkit_add_click(sample_ocr, "Bingo Mad Angles Achari Masti", scale=1.0)
        self.assertIsNotNone(res)
        name, cx, cy = res
        self.assertIn("Bingo Mad Angles", name)
        # Should click row 1 Achaari Masti ADD button (523, 389), NOT row 2 Cheese Nachos (523, 692)
        self.assertEqual(cx, 509 + 14)
        self.assertEqual(cy, 385 + 4)

        # Test dictated phonetic variation "a Charlie flavour Bingo Mad Angle"
        res_voice = _resolve_blinkit_add_click(sample_ocr, "a Charlie flavour Bingo Mad Angle", scale=1.0)
        self.assertIsNotNone(res_voice)
        name_v, cx_v, cy_v = res_voice
        self.assertEqual(cx_v, 509 + 14)
        self.assertEqual(cy_v, 385 + 4)

    def test_blinkit_coca_cola_soft_drink_38_rupees_disambiguation(self):
        sample_ocr = """
[45, 230, 103, 10] -> Paper Boat Zero
[45, 244, 82, 12] -> Sugar Ginger
[45, 265, 38, 9] -> 300 ml
[45, 298, 22, 8] -> r60
[100, 230, 15, 10] -> Ad
[100, 298, 28, 9] -> ADD
[788, 537, 130, 10] -> Coca-cola Diet Coke
[788, 573, 38, 8] -> 330 ml
[788, 606, 22, 8] -> r50
[883, 606, 28, 8] -> ADD
[1161, 840, 131, 10] -> Coca-cola Soft Drink
[1162, 861, 37, 8] -> 750 ml
[1161, 902, 21, 9] -> r38
[1256, 909, 29, 8] -> ADD
"""
        query = "so add the Coca Cola soft drink 38 rupees one add this one into my card and now go to the next part"
        res = _resolve_blinkit_add_click(sample_ocr, query, scale=1.0)
        self.assertIsNotNone(res)
        name, cx, cy = res
        self.assertEqual(name, "Coca-cola Soft Drink")
        self.assertEqual(cx, int(1256 + 29 / 2))
        self.assertEqual(cy, int(909 + 8 / 2))

        res_diet = _resolve_blinkit_add_click(sample_ocr, "add one diet coke", scale=1.0)
        self.assertIsNotNone(res_diet)
        name_d, cx_d, cy_d = res_diet
        self.assertEqual(name_d, "Coca-cola Diet Coke")
        self.assertEqual(cx_d, int(883 + 28 / 2))
        self.assertEqual(cy_d, int(606 + 8 / 2))


class TestWhatsAppAndVoice(unittest.TestCase):
    def test_voice_stt_normalization(self):
        from blacky.voice.stt import normalize_speech_text
        
        # Test wake word misrecognitions
        t1 = normalize_speech_text("Hitler ki open the WhatsApp text to Avnish hello Avnish how are you")
        self.assertIn("Hey Blacky", t1)
        self.assertIn("Avnish", t1)

        # Test name variations
        t2 = normalize_speech_text("the name is Avdhesh")
        self.assertEqual(t2, "the name is Avnish")

        t3 = normalize_speech_text("send message to Avinash on WhatsApp")
        self.assertEqual(t3, "send message to Avnish on WhatsApp")

        t4 = normalize_speech_text("call rishabh on whats app")
        self.assertIn("Rishab", t4)
        self.assertIn("WhatsApp", t4)

        # Test snack / Kurkure phonetics ("one crore packet")
        t5 = normalize_speech_text("search for the diet coke and add one diet coke and add a one crore packet")
        self.assertIn("Kurkure packet", t5)
        self.assertNotIn("one crore", t5)

    def test_whatsapp_no_escape_key(self):
        import inspect
        from blacky.tools import whatsapp
        src = inspect.getsource(whatsapp)
        # Verify key code 53 (Escape) is NOT present in whatsapp module
        self.assertNotIn("key code 53", src, "Escape key code 53 must NEVER be used in WhatsApp as it drops fullscreen!")

    def test_whatsapp_contact_filter_excludes_groups_in_common(self):
        sample_ocr = """
[341, 200, 121, 25] -> Q Avnish
[445, 428, 86, 21] -> Avnish
[444, 712, 321, 24] -> Avnish is also in this group
[444, 847, 321, 25] -> Avnish is also in this group
[302, 1385, 158, 31] -> Messages
[418, 1470, 145, 20] -> From Avnish
"""
        import re
        messages_y = 1385
        candidates = []
        for line in sample_ocr.splitlines():
            if "->" not in line:
                continue
            coords, text = line.split("->", 1)
            text = text.strip()
            m = re.match(r'\[(\d+),\s*(\d+),\s*(\d+),\s*(\d+)\]', coords.strip())
            if not m:
                continue
            px, py, pw, ph = map(int, m.groups())
            if px < 1000 and 280 < py < messages_y:
                t_lower = text.lower()
                if any(k in t_lower for k in [
                    "yesterday", "resume", "maps", "pdf", "unread", "starred", "archived", "chats",
                    "more", "communities", "media", "calls", "in this group", "in common", "group"
                ]):
                    continue
                candidates.append(text)

        # Only Avnish should remain as candidate, NOT "Avnish is also in this group"
        self.assertEqual(candidates, ["Avnish"])


class TestYouTubeTools(unittest.TestCase):
    def test_youtube_video_matching_and_click(self):
        from blacky.tools.web import _resolve_youtube_video_click
        sample_ocr = """
[206, 104, 123, 35] -> YouTube
[855, 107, 387, 33] -> bulleya song salman khan
[652, 219, 86, 23] -> Shorts
[804, 219, 146, 23] -> Unwatched
[1563, 301, 1154, 37] -> Bulleya l Full Song I Sultan I Salman Khan, Anushka Sharma I Papon |
[1560, 356, 524, 34] -> Vishal & Shekhar | Irshad Kamil
[1563, 894, 1154, 36] -> Lyrical | Bulleya Song with Lyrics I Sultan I Salman, Anushka, Vishal &
"""
        res = _resolve_youtube_video_click(sample_ocr, "bulleya song", scale=2.0)
        self.assertIsNotNone(res)
        title, lx, ly = res
        self.assertIn("Bulleya", title)
        self.assertIn("Full Song", title)
        self.assertEqual(lx, int((1563 + 100) / 2))
        self.assertEqual(ly, int((301 + 18) / 2))

    def test_youtube_playlist_prioritization(self):
        from blacky.tools.web import _resolve_youtube_video_click
        sample_ocr = """
[206, 104, 123, 35] -> YouTube
[854, 107, 388, 33] -> sidhu moose wala playlist
[566, 357, 698, 61] -> Sidhu Moose Wala
[1342, 482, 123, 21] -> Subscribe
[1547, 481, 168, 23] -> View Channel
[327, 1055, 372, 26] -> Mix- Sidhu Moose Wala
[325, 1105, 196, 26] -> YouTube Playlist
[1139, 1053, 695, 36] -> KAALI HOODIE (MUSIC VIDEO) SIDHU MOOSE
[1312, 1288, 1347, 38] -> Best Of Sidhu Moose Wala l Latest Punjabi Songs Sidhu Moose Wala Songs
"""
        res = _resolve_youtube_video_click(sample_ocr, "sidhu moose wala playlist", scale=2.0)
        self.assertIsNotNone(res)
        title, lx, ly = res
        self.assertIn("Mix- Sidhu Moose Wala", title)
        self.assertEqual(lx, int((327 + 100) / 2))
        self.assertEqual(ly, int((1055 + 13) / 2))

    def test_blinkit_ambiguous_add_requires_clarification(self):
        from blacky.tools.web import _blinkit_add_candidates, _blinkit_add_ambiguity_message
        # Two plausible Coke products -> should be flagged ambiguous, never auto-select
        sample_ocr = """
[100, 500, 60, 18] -> ADD
[152, 507, 275, 23] -> Coca-cola Diet Coke
[400, 700, 60, 18] -> ADD
[452, 707, 275, 23] -> Coca-cola Original
"""
        cands = _blinkit_add_candidates(sample_ocr, "coke", scale=1.0)
        self.assertEqual(len(cands), 2)
        amb = _blinkit_add_ambiguity_message("coke", sample_ocr, scale=1.0)
        self.assertIsNotNone(amb)
        self.assertIn("AMBIGUOUS_PRODUCTS", amb)
        self.assertIn("Do NOT auto-select", amb)

    def test_blinkit_clear_add_not_ambiguous(self):
        from blacky.tools.web import _blinkit_add_ambiguity_message
        sample_ocr = """
[124, 65, 459, 27] -> Showing results for "diet coke"
[525, 507, 259, 18] -> Coca-cola Diet Coke
[717, 645, 58, 18] -> ADD
"""
        self.assertIsNone(_blinkit_add_ambiguity_message("diet coke", sample_ocr, scale=2.0))


class TestScreenLockTools(unittest.TestCase):
    def test_screen_lock_status(self):
        from blacky.tools.macos import get_mac_screen_lock_status
        status = get_mac_screen_lock_status()
        self.assertIn("macOS Screen Status:", status)

    def test_wake_mac_display(self):
        from blacky.tools.macos import wake_mac_display
        res = wake_mac_display()
        self.assertIn("display illuminated", res.lower())


class TestInPageSearchTools(unittest.TestCase):
    def test_find_in_page_search_bar_blinkit(self):
        from blacky.tools.web import find_in_page_search_bar
        sample_ocr = """
[32, 27, 114, 30] -> blinkit
[436, 38, 207, 13] -> Bingo Mad Angles Achari Masti
[401, 96, 386, 13] -> Showing results for "bingo mad angles achari masti"
"""
        lx, ly = find_in_page_search_bar(sample_ocr, site="blinkit", scale=1.0)
        self.assertEqual(lx, int(436 + 207 / 2))
        self.assertEqual(ly, int(38 + 13 / 2))

    def test_find_in_page_search_bar_youtube(self):
        from blacky.tools.web import find_in_page_search_bar
        sample_ocr = """
[100, 20, 80, 25] -> YouTube
[500, 25, 400, 30] -> Search
"""
        lx, ly = find_in_page_search_bar(sample_ocr, site="youtube", scale=1.0)
        self.assertEqual(lx, int(500 + 400 / 2))
        self.assertEqual(ly, int(25 + 30 / 2))

    def test_find_in_page_search_bar_fallbacks(self):
        from blacky.tools.web import find_in_page_search_bar
        lx, ly = find_in_page_search_bar("", site="blinkit", scale=1.0)
        self.assertEqual((lx, ly), (530, 44))
        lx, ly = find_in_page_search_bar("", site="youtube", scale=1.0)
        self.assertEqual((lx, ly), (600, 35))
        lx, ly = find_in_page_search_bar("", site="amazon", scale=1.0)
        self.assertEqual((lx, ly), (550, 48))
        lx, ly = find_in_page_search_bar("", site="flipkart", scale=1.0)
        self.assertEqual((lx, ly), (500, 42))


class TestMultiDisplayTargeting(unittest.TestCase):
    def test_get_display_info_site_targeting(self):
        from blacky.tools.macos import get_display_info
        # Tests that target_site properly resolves to a valid display containing that site
        disp_blinkit = get_display_info("Brave Browser", target_site="blinkit")
        self.assertIn("display_num", disp_blinkit)
        self.assertIn("origin_x", disp_blinkit)
        self.assertIn(disp_blinkit["origin_x"], (0.0, 1920.0))


class TestWhatsAppOrdinalDisambiguation(unittest.TestCase):
    def test_whatsapp_ordinal_resolution(self):
        import blacky.tools.whatsapp as wa
        wa._LAST_DISAMBIGUATION_CANDIDATES = [
            {"name": "Yash Sharma", "norm": "yash sharma", "x": 100, "y": 200},
            {"name": "Yash College", "norm": "yash college", "x": 100, "y": 250},
            {"name": "Yash Gym", "norm": "yash gym", "x": 100, "y": 300},
            {"name": "Yash Brother", "norm": "yash brother", "x": 100, "y": 350},
        ]
        self.assertEqual(wa._resolve_contact_ordinal("first one"), "Yash Sharma")
        self.assertEqual(wa._resolve_contact_ordinal("the 1st one"), "Yash Sharma")
        self.assertEqual(wa._resolve_contact_ordinal("second"), "Yash College")
        self.assertEqual(wa._resolve_contact_ordinal("3rd one"), "Yash Gym")
        self.assertEqual(wa._resolve_contact_ordinal("fourth one"), "Yash Brother")
        self.assertEqual(wa._resolve_contact_ordinal("4th"), "Yash Brother")


class TestPerformanceAndCaching(unittest.TestCase):
    def test_fullscreen_caching_speed(self):
        import time
        from blacky.tools.macos import make_window_fullscreen, _fullscreen_cache
        _fullscreen_cache["Brave Browser"] = time.time()
        start = time.time()
        res = make_window_fullscreen("Brave Browser")
        elapsed = time.time() - start
        self.assertIn("Already in Entire Screen", res)
        # Should return in under 1 millisecond from cache
        self.assertLess(elapsed, 0.01)

    def test_capture_display_screen_direct_jpg(self):
        import os
        from blacky.tools.macos import capture_display_screen
        shot_path = "/tmp/test_perf_capture.jpg"
        if os.path.exists(shot_path):
            os.remove(shot_path)
        disp = capture_display_screen(shot_path, app_name="Brave Browser")
        self.assertTrue(os.path.exists(shot_path))
        self.assertGreater(os.path.getsize(shot_path), 1000)
        self.assertIn("scale", disp)
        if os.path.exists(shot_path):
            os.remove(shot_path)


class TestSearchVsAddCartIntent(unittest.TestCase):
    def test_search_redirect_in_blinkit_add(self):
        from unittest.mock import patch
        import blacky.tools.web as web

        with patch.object(web, "browser_search", return_value="SEARCH_SUCCESS") as mock_search:
            # Query has search intent but NO add intent -> MUST redirect to browser_search
            res = web.blinkit_add_to_cart("search the diet Coke in the Blinkit")
            self.assertEqual(res, "SEARCH_SUCCESS")
            mock_search.assert_called_once()

    def test_browser_search_query_cleaning(self):
        import re
        q = "search the diet Coke in the Blinkit"
        clean = re.sub(r'^(search|find|look for|show me)\s+(for\s+)?(the\s+|a\s+)?', '', q, flags=re.IGNORECASE).strip()
        clean = re.sub(r'\s+(in|on|at)\s+(the\s+)?(blinkit|blanket|amazon|youtube|google|flipkart)\b.*', '', clean, flags=re.IGNORECASE).strip()
        self.assertEqual(clean, "diet Coke")

    def test_youtube_search_redirect_when_no_play(self):
        from unittest.mock import patch
        import blacky.tools.web as web

        with patch.object(web, "browser_search", return_value="SEARCH_SUCCESS") as mock_search:
            # Query has search intent but NO play intent -> MUST redirect to browser_search
            res = web.youtube_play("search for bulleya on youtube")
            self.assertEqual(res, "SEARCH_SUCCESS")
            mock_search.assert_called_once()


if __name__ == "__main__":
    unittest.main()
