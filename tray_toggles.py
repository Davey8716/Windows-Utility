import threading
import pystray
from PIL import Image, ImageDraw
from screen_mover import SCREEN_MOVER

# ===================================================================
#  Tray Icon Manager (Monolithic Class)
# ===================================================================

class TrayIconManager:
    def __init__(self, app):
        """
        Holds tray icon state and callbacks.
        `app` = your main UtilityControlApp instance.
        """
        self.app = app
        self.tray_icon = None
        self.tray_thread = None

    # ===================================================================
    #  Create Tray Icon
    # ===================================================================

    def create_tray_icon(self):
        """Create and start the system tray icon in a background thread."""

        # Create a simple blue square icon (matches your CTk blue theme)
        def make_icon_image(size=32):
            img = Image.new("RGBA", (size, size), (26, 115, 232, 255))  # blue-ish
            draw = ImageDraw.Draw(img)

            margin = size // 8
            draw.rectangle(
                [margin, margin, size - margin, size - margin],
                fill=(0, 120, 255, 255)
            )

            return img

        image = make_icon_image()

        # Tray menu
        menu = pystray.Menu(
            pystray.MenuItem("Toggle Window", self.tray_menu_toggle, default=True),
            pystray.MenuItem("Quit", self.tray_menu_quit)
        )

        self.tray_icon = pystray.Icon(
            "WindowsUtility",
            image,
            "Utility Suite",
            menu
        )

        # Threaded run loop
        def run_tray():
            self.tray_icon.run()

        self.tray_thread = threading.Thread(target=run_tray, daemon=True)
        self.tray_thread.start()

    # ===================================================================
    #  Tray Menu Callbacks (Run in Tray Thread)
    # ===================================================================

    def tray_menu_toggle(self, icon, item):
        """Double-click → toggle window show/hide."""
        self.app.after(0, self._toggle_window)

    def tray_menu_quit(self, icon, item):
        self.app.after(0, self._quit_from_tray)

    # ===================================================================
    #  Helpers (Executed on Tk thread)
    # ===================================================================
    
    def _show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def _toggle_window(self):
        if self.app.state() == "withdrawn":
            self.app._show_window()

            # 🔴 reset leadership + resync after restore
            self.app._clear_drag_owner()
            self.app.after(20, lambda: self.app._sync_windows("main"))
        else:
            self.app.withdraw()


    def _quit_from_tray(self):
        print("[INFO] Quitting from tray…")

        try:
            SCREEN_MOVER.stop()
        except:
            pass

        if self.tray_icon:
            try:
                self.tray_icon.visible = False
                self.tray_icon.stop()
            except:
                pass

        self.app.destroy()

    # ===================================================================
    #  Hide-on-close behaviour
    # ===================================================================

    def on_close_to_tray(self):
        # close right panel first
        if (
            hasattr(self.app, "advanced_panel")
            and self.app.advanced_panel
            and self.app.advanced_panel.winfo_viewable()
        ):
            self.app.toggle_side_panel()

        self.app.withdraw()
