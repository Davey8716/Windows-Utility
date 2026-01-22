# screenshot_tool.py

import time
from PIL import ImageGrab
from tkinter import filedialog
from datetime import datetime

def take_desktop_screenshot(app):
    """
    Universal desktop screenshotter:
    - Minimizes main GUI
    - Minimizes right panel if open
    - Takes screenshot
    - Prompts for save location
    - Restores previous GUI state
    """


    right_was_open = False

    try:
        # -------------------------------------------------------
        # 1) Capture current state
        # -------------------------------------------------------

        if (
            hasattr(app, "advanced_panel")
            and app.advanced_panel
            and app.advanced_panel.winfo_viewable()
        ):
            right_was_open = True
            app.advanced_panel.withdraw()

        # -------------------------------------------------------
        # 2) Minimize main GUI
        # -------------------------------------------------------

        app.withdraw()
        app.update_idletasks()
        time.sleep(0.3)  # ensure desktop is clean

        # -------------------------------------------------------
        # 3) Capture full desktop
        # -------------------------------------------------------

        img = ImageGrab.grab()

        # -------------------------------------------------------
        # 4) Save dialog
        # -------------------------------------------------------

        default_name = f"DesktopScreenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

        save_path = filedialog.asksaveasfilename(
            title="Save Desktop Screenshot",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[("PNG Image", "*.png")],
        )

        if save_path:
            img.save(save_path)
            print(f"[SCREENSHOT] Saved: {save_path}")
        else:
            print("[SCREENSHOT] Cancelled by user")

    except Exception as e:
        print("[SCREENSHOT] Error:", e)

    finally:
        # -------------------------------------------------------
        # 5) Restore GUI exactly as before
        # -------------------------------------------------------

        try:
            app.deiconify()
            app.after(50, app.lift)

            if right_was_open:
                app.advanced_panel.deiconify()
                app.after(60, lambda: app._sync_windows("main"))

        except Exception:
            pass
