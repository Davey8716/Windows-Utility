# screenshot_tool.py

import time
from PIL import ImageGrab
from tkinter import filedialog
from datetime import datetime

def take_desktop_screenshot(app):
    """
    Universal desktop screenshotter:
    - Minimizes the Problem Gone GUI
    - Takes screenshot
    - Prompts for save location
    - Restores the GUI
    """

    try:
        # -------------------------------------------------------
        # 1) Minimize GUI
        # -------------------------------------------------------
        
        app.withdraw()
        app.update()
        time.sleep(0.25)   # small pause ensures clean desktop

        # -------------------------------------------------------
        # 2) Capture full desktop
        # -------------------------------------------------------
        
        img = ImageGrab.grab()

        # -------------------------------------------------------
        # 3) Save dialog
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
        
        # 4) Restore GUI
        # -------------------------------------------------------
        
        try:
            app.deiconify()
            app.after(50, app.lift)
        except:
            pass
