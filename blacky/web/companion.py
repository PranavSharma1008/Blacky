"""
macOS Menu Bar Companion & Floating Overlay Window for BlackyAgent Screen Analysis.

Provides:
1. Native macOS Menu Bar (Status Bar) icon (SF Symbol 'sparkles.tv' or '🐾')
2. Movable, floating chatbot companion window (WKWebView with glassmorphic dark UI)
3. One-click toggle from the Menu Bar
4. Instant screen-capture concealment to prevent window occlusion and recursion loops
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import threading
import time
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Global reference to active companion for external coordination (e.g. screen capture hide)
_active_companion: BlackyScreenCompanion | None = None


def get_active_companion() -> BlackyScreenCompanion | None:
    return _active_companion


@contextlib.contextmanager
def companion_capture_guard():
    """
    Temporarily hide the floating companion window while a screenshot is taken,
    so that Blacky never captures its own UI or obstructs underlying windows.
    """
    comp = _active_companion
    if comp is not None and comp.is_window_visible():
        comp.hide_window_sync()
        time.sleep(0.04)  # brief yield for macOS window server buffer flush
        try:
            yield
        finally:
            comp.show_window_sync()
    else:
        yield


class BlackyScreenCompanion:
    """Native macOS Menu Bar item + Floating WKWebView Chatbot Companion."""

    def __init__(
        self,
        port: int = 8010,
        width: int = 390,
        height: int = 600,
        on_quit: Callable[[], None] | None = None,
    ) -> None:
        global _active_companion
        _active_companion = self

        self.port = port
        self.width = width
        self.height = height
        self.url = f"http://127.0.0.1:{port}/screen"
        self.on_quit = on_quit
        self.target_app = "Auto"

        self.app = None
        self.status_bar = None
        self.status_item = None
        self.menu = None
        self.window = None
        self.webview = None
        self.window_delegate = None
        self.menu_delegate = None

    def initialize(self) -> bool:
        """Initialize Cocoa objects on the main thread."""
        try:
            import AppKit
            import Foundation
            import WebKit
        except ImportError as exc:
            logger.warning("Cocoa / AppKit not available: %s", exc)
            return False

        self.app = AppKit.NSApplication.sharedApplication()
        # Accessory mode: Lives in Menu Bar, does not show in the macOS Dock
        self.app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)

        # 1. Setup Status Bar (Menu Bar) Item
        self.status_bar = AppKit.NSStatusBar.systemStatusBar()
        self.status_item = self.status_bar.statusItemWithLength_(AppKit.NSVariableStatusItemLength)

        button = self.status_item.button()
        if button is not None:
            # Use macOS SF Symbol 'sparkles.tv' or 'pawprint' matching modern macOS AI style
            symbol = AppKit.NSImage.imageWithSystemSymbolName_accessibilityDescription_(
                "sparkles.tv", "Blacky Companion"
            )
            if symbol is not None:
                symbol.setTemplate_(True)
                button.setImage_(symbol)
            else:
                button.setTitle_("🐾")
            button.setToolTip_("Blacky Companion — Click to toggle chat window")

        # 2. Build Menu Bar Dropdown
        self._build_menu()

        # Connect button click
        self.menu_delegate = _StatusBarTarget.alloc().initWithCompanion_(self)
        if button is not None:
            button.setTarget_(self.menu_delegate)
            button.setAction_("statusItemClicked:")
            button.sendActionOn_(
                AppKit.NSEventMaskLeftMouseUp | AppKit.NSEventMaskRightMouseUp
            )

        # 3. Create Floating Companion Window
        self._create_floating_window()

        return True

    def _build_menu(self) -> None:
        import AppKit

        self.menu = AppKit.NSMenu.alloc().init()
        self.menu.setAutoenablesItems_(True)

        header_item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Blacky Companion", None, ""
        )
        header_item.setEnabled_(False)
        self.menu.addItem_(header_item)

        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        item_toggle = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "💬 Toggle Chat Window", "toggleWindow:", "t"
        )
        item_toggle.setTarget_(self.menu_delegate)
        self.menu.addItem_(item_toggle)

        item_analyze = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "👁️ Analyze Current Screen", "analyzeScreen:", "a"
        )
        item_analyze.setTarget_(self.menu_delegate)
        self.menu.addItem_(item_analyze)

        self.menu.addItem_(AppKit.NSMenuItem.separatorItem())

        item_quit = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "✖ Quit Blacky Companion", "quitApp:", "q"
        )
        item_quit.setTarget_(self.menu_delegate)
        self.menu.addItem_(item_quit)

    def _create_floating_window(self) -> None:
        import AppKit
        import Foundation
        import WebKit

        # Compute initial position: top-right corner of main screen
        main_screen = AppKit.NSScreen.mainScreen()
        screen_frame = main_screen.visibleFrame() if main_screen else Foundation.NSMakeRect(0, 0, 1440, 900)

        x = screen_frame.origin.x + screen_frame.size.width - self.width - 24
        y = screen_frame.origin.y + screen_frame.size.height - self.height - 24

        rect = Foundation.NSMakeRect(x, y, self.width, self.height)
        style = (
            AppKit.NSWindowStyleMaskTitled
            | AppKit.NSWindowStyleMaskClosable
            | AppKit.NSWindowStyleMaskMiniaturizable
            | AppKit.NSWindowStyleMaskResizable
        )

        self.window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, style, AppKit.NSBackingStoreBuffered, False
        )
        self.window.setTitle_("Blacky Companion")
        # Floating window level: stays over normal application windows
        self.window.setLevel_(AppKit.NSFloatingWindowLevel)
        # Allows moving the window anywhere by clicking and dragging on background/header
        self.window.setMovableByWindowBackground_(True)
        self.window.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )

        # Intercept close button to hide back to Menu Bar rather than terminating
        self.window_delegate = _WindowDelegate.alloc().initWithCompanion_(self)
        self.window.setDelegate_(self.window_delegate)

        # Configure WebKit View
        ucc = WebKit.WKUserContentController.alloc().init()
        script_handler = _ScriptHandler.alloc().initWithCompanion_(self)
        ucc.addScriptMessageHandler_name_(script_handler, "blacky")

        cfg = WebKit.WKWebViewConfiguration.alloc().init()
        cfg.setUserContentController_(ucc)

        self.webview = WebKit.WKWebView.alloc().initWithFrame_configuration_(rect, cfg)
        self.window.setContentView_(self.webview)

        # Load screen interface URL
        req = Foundation.NSURLRequest.requestWithURL_(Foundation.NSURL.URLWithString_(self.url))
        self.webview.loadRequest_(req)

        # Make visible and order front initially
        self.show_window_sync()

    def run(self) -> None:
        """Run the Cocoa event loop on the main thread."""
        if self.app is None:
            if not self.initialize():
                raise RuntimeError("Failed to initialize Cocoa application")
        self.app.run()

    # Window visibility controls
    def is_window_visible(self) -> bool:
        return bool(self.window and self.window.isVisible())

    def toggle_window(self) -> None:
        if self.is_window_visible():
            self.hide_window_sync()
        else:
            self.show_window_sync()

    def show_window_sync(self) -> None:
        if self.window is not None:
            import AppKit
            self.window.performSelectorOnMainThread_withObject_waitUntilDone_(
                "makeKeyAndOrderFront:", None, True
            )
            AppKit.NSApp().activateIgnoringOtherApps_(True)

    def hide_window_sync(self) -> None:
        if self.window is not None:
            self.window.performSelectorOnMainThread_withObject_waitUntilDone_(
                "orderOut:", None, True
            )

    def trigger_analyze(self) -> None:
        """Inject analyze action into the webview."""
        if self.webview is not None:
            script = "if (window.BlackyCompanion) { window.BlackyCompanion.analyze(); }"
            self.webview.evaluateJavaScript_completionHandler_(script, None)
        self.show_window_sync()

    def trigger_solve_mcqs(self) -> None:
        """Inject solve MCQs action into the webview."""
        if self.webview is not None:
            script = "if (window.BlackyCompanion) { window.BlackyCompanion.solveMcqs(); }"
            self.webview.evaluateJavaScript_completionHandler_(script, None)
        self.show_window_sync()

    def set_target_app(self, app_name: str) -> None:
        self.target_app = app_name
        if self.webview is not None:
            import json
            escaped = json.dumps(app_name)
            script = f"if (window.BlackyCompanion) {{ window.BlackyCompanion.setTargetApp({escaped}); }}"
            self.webview.evaluateJavaScript_completionHandler_(script, None)
        self._build_menu()

    def quit(self) -> None:
        global _active_companion
        _active_companion = None
        if self.window is not None:
            self.window.orderOut_(None)
        if self.on_quit:
            try:
                self.on_quit()
            except Exception:
                pass
        import AppKit
        AppKit.NSApp().terminate_(None)


# ----------------------------------------------------------------------
# Cocoa Delegates & Handlers
# ----------------------------------------------------------------------
try:
    import AppKit
    import objc

    class _StatusBarTarget(AppKit.NSObject):
        companion: Any = objc.ivar()

        def initWithCompanion_(self, companion):
            self = objc.super(_StatusBarTarget, self).init()
            if self is not None:
                self.companion = companion
            return self

        def statusItemClicked_(self, sender):
            event = AppKit.NSApp().currentEvent()
            # If right clicked or Control pressed, pop up dropdown menu
            if event and (
                event.type() == AppKit.NSEventTypeRightMouseUp
                or (event.modifierFlags() & AppKit.NSEventModifierFlagControl)
            ):
                if self.companion and self.companion.status_item and self.companion.menu:
                    self.companion.status_item.popUpStatusItemMenu_(self.companion.menu)
            else:
                # Left click: toggle the companion chatbot window!
                if self.companion:
                    self.companion.toggle_window()

        def toggleWindow_(self, sender):
            if self.companion:
                self.companion.toggle_window()

        def analyzeScreen_(self, sender):
            if self.companion:
                self.companion.trigger_analyze()

        def solveMcqs_(self, sender):
            if self.companion:
                self.companion.trigger_solve_mcqs()

        def selectApp_(self, sender):
            if self.companion and sender:
                app_name = str(sender.representedObject() or sender.title())
                self.companion.set_target_app(app_name)

        def quitApp_(self, sender):
            if self.companion:
                self.companion.quit()

    class _WindowDelegate(AppKit.NSObject):
        companion: Any = objc.ivar()

        def initWithCompanion_(self, companion):
            self = objc.super(_WindowDelegate, self).init()
            if self is not None:
                self.companion = companion
            return self

        def windowShouldClose_(self, window):
            # Do not destroy window; hide it back into Menu Bar
            if self.companion:
                self.companion.hide_window_sync()
            return False

    class _ScriptHandler(AppKit.NSObject):
        companion: Any = objc.ivar()

        def initWithCompanion_(self, companion):
            self = objc.super(_ScriptHandler, self).init()
            if self is not None:
                self.companion = companion
            return self

        def userContentController_didReceiveScriptMessage_(self, ucc, message):
            body = str(message.body() or "").strip()
            if not self.companion:
                return
            if body == "hide":
                self.companion.hide_window_sync()
            elif body == "quit":
                self.companion.quit()

except Exception:
    pass
