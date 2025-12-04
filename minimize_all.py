# ===================================================================
#  Minimize / Restore All Windows Except GUI
# ===================================================================

import win32gui
import win32con

# ------------------------------------------------------------
#  Helper: Should we skip this hwnd?
# ------------------------------------------------------------

def _should_skip(hwnd, skip_hwnd):
    if hwnd == skip_hwnd:
        return True

    if not win32gui.IsWindowVisible(hwnd):
        return True

    # Skip shell windows without title
    title = win32gui.GetWindowText(hwnd)
    if not title.strip():
        return True

    # Only handle top-level windows
    if win32gui.GetParent(hwnd) != 0:
        return True

    return False

# ------------------------------------------------------------
#  Minimize All Except GUI
# ------------------------------------------------------------

def minimize_all_except_gui(skip_hwnd):
    print("[MIN/MAX] Minimizing all windows except GUI…")

    def enum_handler(hwnd, _):
        if _should_skip(hwnd, skip_hwnd):
            return

        try:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
        except Exception:
            pass

    win32gui.EnumWindows(enum_handler, None)

# ------------------------------------------------------------
#  Restore All Except GUI
# ------------------------------------------------------------

def restore_all_except_gui(skip_hwnd):
    print("[MIN/MAX] Restoring all minimized windows except GUI…")

    def enum_handler(hwnd, _):

        if _should_skip(hwnd, skip_hwnd):
            return

        # Check if minimized
        placement = win32gui.GetWindowPlacement(hwnd)
        show_cmd = placement[1]

        if show_cmd == win32con.SW_SHOWMINIMIZED:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            except Exception:
                pass

    win32gui.EnumWindows(enum_handler, None)
