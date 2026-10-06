# desktop_icon_layout.py
import ctypes
from ctypes import wintypes
import win32con
import win32gui
import win32api
import win32process
import json
from pathlib import Path

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

LVM_FIRST = 0x1000
LVM_GETITEMCOUNT = LVM_FIRST + 4
LVM_GETITEMTEXTW = LVM_FIRST + 115
LVM_GETITEMPOSITION = LVM_FIRST + 16
LVM_SETITEMPOSITION32 = LVM_FIRST + 49

LVIF_TEXT = 0x0001

class LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", wintypes.UINT),
        ("iItem", ctypes.c_int),
        ("iSubItem", ctypes.c_int),
        ("state", wintypes.UINT),
        ("stateMask", wintypes.UINT),
        ("pszText", wintypes.LPWSTR),
        ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int),
        ("lParam", wintypes.LPARAM),
        ("iIndent", ctypes.c_int),
        ("iGroupId", ctypes.c_int),
        ("cColumns", wintypes.UINT),
        ("puColumns", wintypes.PUINT),
        ("piColFmt", wintypes.PINT),
        ("iGroup", ctypes.c_int),
    ]

def _find_desktop_listview_hwnd() -> int | None:
    """
    Returns the HWND of the Desktop's SysListView32 ("FolderView") control.
    Works on Win10/11 for the real desktop (not an Explorer window).
    """
    # 1) Try Progman
    progman = win32gui.FindWindow("Progman", None)
    if progman:
        sheldll = win32gui.FindWindowEx(progman, 0, "SHELLDLL_DefView", None)
        if sheldll:
            lv = win32gui.FindWindowEx(sheldll, 0, "SysListView32", "FolderView")
            if lv:
                return lv

    # 2) WorkerW fallback (common on Win10/11)
    def enum_windows_cb(hwnd, result_list):
        cls = win32gui.GetClassName(hwnd)
        if cls == "WorkerW":
            try:
                sheldll = win32gui.FindWindowEx(hwnd, 0, "SHELLDLL_DefView", None)
                if sheldll:
                    lv = win32gui.FindWindowEx(sheldll, 0, "SysListView32", "FolderView")
                    if lv:
                        result_list.append(lv)
            except Exception:
                pass

    found = []
    win32gui.EnumWindows(enum_windows_cb, found)
    return found[0] if found else None


def desktop_icons_visible() -> bool | None:
    lv_hwnd = _find_desktop_listview_hwnd()
    if not lv_hwnd:
        return None
    return bool(win32gui.IsWindowVisible(lv_hwnd))


def set_desktop_icons_visible(visible: bool) -> bool:
    lv_hwnd = _find_desktop_listview_hwnd()
    if not lv_hwnd:
        return False

    win32gui.ShowWindow(lv_hwnd, win32con.SW_SHOW if visible else win32con.SW_HIDE)
    win32gui.InvalidateRect(lv_hwnd, None, True)
    return True

def capture_desktop_icon_layout() -> list[dict]:
    """
    Returns: [{"name": "...", "x": 123, "y": 456}, ...]
    """
    lv_hwnd = _find_desktop_listview_hwnd()
    if not lv_hwnd:
        raise RuntimeError("Could not find Desktop ListView handle (FolderView).")

    # Get Explorer PID
    _, pid = win32process.GetWindowThreadProcessId(lv_hwnd)
    h_process = win32api.OpenProcess(
        win32con.PROCESS_VM_OPERATION
        | win32con.PROCESS_VM_READ
        | win32con.PROCESS_VM_WRITE,
        False,
        pid,
    )

    try:
        count = win32gui.SendMessage(lv_hwnd, LVM_GETITEMCOUNT, 0, 0)

        # Remote buffers in explorer.exe
        # - text buffer (wide chars)
        # - LVITEMW struct
        # - POINT struct for LVM_GETITEMPOSITION
        text_max = 520
        text_bytes = text_max * ctypes.sizeof(wintypes.WCHAR)
        lvitem_size = ctypes.sizeof(LVITEMW)
        point_size = ctypes.sizeof(wintypes.POINT)

        remote_text = kernel32.VirtualAllocEx(h_process.handle, 0, text_bytes, 0x3000, 0x04)
        remote_lvitem = kernel32.VirtualAllocEx(h_process.handle, 0, lvitem_size, 0x3000, 0x04)
        remote_point = kernel32.VirtualAllocEx(h_process.handle, 0, point_size, 0x3000, 0x04)

        if not remote_text or not remote_lvitem or not remote_point:
            raise RuntimeError("VirtualAllocEx failed (could not allocate in explorer.exe).")

        layout = []








        for i in range(count):
            # Build LVITEMW locally
            buf = ctypes.create_unicode_buffer(text_max)

            item = LVITEMW()
            item.mask = LVIF_TEXT
            item.iItem = i
            item.iSubItem = 0
            item.pszText = ctypes.cast(remote_text, wintypes.LPWSTR)
            item.cchTextMax = text_max

            # Write LVITEM to remote
            written = ctypes.c_size_t(0)
            ok = kernel32.WriteProcessMemory(
                h_process.handle,
                remote_lvitem,
                ctypes.byref(item),
                lvitem_size,
                ctypes.byref(written),
            )
            if not ok:
                continue

            # Ask listview to fill the remote buffers
            win32gui.SendMessage(lv_hwnd, LVM_GETITEMTEXTW, i, remote_lvitem)

            # Read back text
            read = ctypes.c_size_t(0)
            kernel32.ReadProcessMemory(
                h_process.handle,
                remote_text,
                ctypes.byref(buf),
                text_bytes,
                ctypes.byref(read),
            )
            name = buf.value

            # Position
            win32gui.SendMessage(lv_hwnd, LVM_GETITEMPOSITION, i, remote_point)
            pt = wintypes.POINT()
            kernel32.ReadProcessMemory(
                h_process.handle,
                remote_point,
                ctypes.byref(pt),
                point_size,
                ctypes.byref(read),
            )

            layout.append({"name": name, "x": int(pt.x), "y": int(pt.y)})

        # Free remote allocations
        kernel32.VirtualFreeEx(h_process.handle, remote_text, 0, 0x8000)
        kernel32.VirtualFreeEx(h_process.handle, remote_lvitem, 0, 0x8000)
        kernel32.VirtualFreeEx(h_process.handle, remote_point, 0, 0x8000)

        return layout

    finally:
        try:
            win32api.CloseHandle(h_process)
        except Exception:
            pass


def _grid_pitch(coordinates: list[int]) -> int | None:
    """Return the smallest observed spacing on one Desktop grid axis."""
    unique_coordinates = sorted(set(coordinates))
    gaps = [
        right - left
        for left, right in zip(unique_coordinates, unique_coordinates[1:])
        if right > left
    ]
    return min(gaps) if gaps else None


def desktop_icon_groups(layout: list[dict]) -> list[list[dict]]:
    """Split positioned icons into clusters separated by at least one grid cell.

    The Desktop has no native concept of manually arranged groups.  We infer
    them from the blank grid space between icons, which keeps a user's visual
    clusters intact without inventing persistent group metadata.
    """
    if not layout:
        return []

    x_pitch = _grid_pitch([int(item["x"]) for item in layout])
    y_pitch = _grid_pitch([int(item["y"]) for item in layout])
    x_limit = x_pitch * 1.5 if x_pitch is not None else 0
    y_limit = y_pitch * 1.5 if y_pitch is not None else 0
    parent = list(range(len(layout)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def join(left: int, right: int) -> None:
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, left in enumerate(layout):
        for right_index in range(left_index + 1, len(layout)):
            right = layout[right_index]
            if (
                abs(int(left["x"]) - int(right["x"])) <= x_limit
                and abs(int(left["y"]) - int(right["y"])) <= y_limit
            ):
                join(left_index, right_index)

    groups: dict[int, list[dict]] = {}
    for index, item in enumerate(layout):
        groups.setdefault(find(index), []).append(item)
    return list(groups.values())


def grouped_alphabetical_positions(layout: list[dict]) -> list[tuple[int, int]]:
    """Return target positions that alphabetise each detected group in-place.

    Desktop columns are read from top to bottom before moving to the next
    column.  The returned list deliberately follows the input ListView order,
    making it safe to apply directly to the captured icon list.
    """
    target_positions: dict[int, tuple[int, int]] = {}
    item_indices = {id(item): index for index, item in enumerate(layout)}
    for group in desktop_icon_groups(layout):
        slots = sorted(group, key=lambda item: (int(item["x"]), int(item["y"])))
        names = sorted((str(item["name"]) for item in group), key=str.casefold)
        for slot, name in zip(slots, names):
            # Match duplicate visible names deterministically in their current
            # ListView order, rather than collapsing them into one dictionary key.
            source = next(
                item for item in group
                if str(item["name"]) == name and id(item) not in target_positions
            )
            target_positions[id(source)] = (int(slot["x"]), int(slot["y"]))
    return [target_positions[id(item)] for item in layout]


def _apply_positions_by_index(positions: list[tuple[int, int]]) -> int:
    """Apply positions to the current Desktop ListView items in index order."""
    lv_hwnd = _find_desktop_listview_hwnd()
    if not lv_hwnd:
        raise RuntimeError("Desktop ListView not found")

    _, pid = win32process.GetWindowThreadProcessId(lv_hwnd)
    h_process = win32api.OpenProcess(
        win32con.PROCESS_VM_OPERATION | win32con.PROCESS_VM_WRITE,
        False,
        pid,
    )
    remote_point = None
    applied = 0
    try:
        remote_point = kernel32.VirtualAllocEx(
            h_process.handle, 0, ctypes.sizeof(wintypes.POINT), 0x3000, 0x04
        )
        if not remote_point:
            raise RuntimeError("VirtualAllocEx failed while arranging Desktop icons.")

        count = min(
            len(positions), win32gui.SendMessage(lv_hwnd, LVM_GETITEMCOUNT, 0, 0)
        )
        win32gui.SendMessage(lv_hwnd, win32con.WM_SETREDRAW, 0, 0)
        for index, (x, y) in enumerate(positions[:count]):
            point = wintypes.POINT(x, y)
            if kernel32.WriteProcessMemory(
                h_process.handle, remote_point, ctypes.byref(point),
                ctypes.sizeof(point), None,
            ):
                win32gui.SendMessage(lv_hwnd, LVM_SETITEMPOSITION32, index, remote_point)
                applied += 1
    finally:
        try:
            win32gui.SendMessage(lv_hwnd, win32con.WM_SETREDRAW, 1, 0)
            win32gui.InvalidateRect(lv_hwnd, None, True)
            win32gui.UpdateWindow(lv_hwnd)
        except Exception:
            pass
        if remote_point:
            kernel32.VirtualFreeEx(h_process.handle, remote_point, 0, 0x8000)
        try:
            win32api.CloseHandle(h_process)
        except Exception:
            pass
    return applied


def alphabetise_desktop_icon_groups() -> tuple[int, int]:
    """Alphabetise each visually separated Desktop icon group in place.

    Returns the number of groups detected and icons repositioned.
    """
    layout = capture_desktop_icon_layout()
    groups = desktop_icon_groups(layout)
    return len(groups), _apply_positions_by_index(grouped_alphabetical_positions(layout))

def save_desktop_icon_layout(out_path: str) -> int:
    """
    Saves layout to JSON. Returns count of icons captured.
    """
    layout = capture_desktop_icon_layout()
    payload = {
        "version": 1,
        "layout": layout,
    }
    output_path = Path(out_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    return len(layout)

def restore_desktop_icon_layout(json_path: str) -> int:
    """
    Restores desktop icon positions from a saved layout file.
    Uses remote (explorer.exe) memory for BOTH:
    - LVM_GETITEMTEXTW (read names)
    - LVM_SETITEMPOSITION32 (write positions via remote POINT*)
    Returns number of icons restored.
    """

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    layout = {item["name"]: (int(item["x"]), int(item["y"])) for item in data.get("layout", [])}

    lv_hwnd = _find_desktop_listview_hwnd()
    if not lv_hwnd:
        raise RuntimeError("Desktop ListView not found")

    _, pid = win32process.GetWindowThreadProcessId(lv_hwnd)
    h_process = win32api.OpenProcess(
        win32con.PROCESS_VM_OPERATION | win32con.PROCESS_VM_READ | win32con.PROCESS_VM_WRITE,
        False,
        pid,
    )

    restored = 0

    text_max = 520
    text_bytes = text_max * ctypes.sizeof(wintypes.WCHAR)
    lvitem_size = ctypes.sizeof(LVITEMW)
    point_size = ctypes.sizeof(wintypes.POINT)
    remote_text = None
    remote_lvitem = None
    remote_point = None

    try:
        count = win32gui.SendMessage(lv_hwnd, LVM_GETITEMCOUNT, 0, 0)

        remote_text = kernel32.VirtualAllocEx(h_process.handle, 0, text_bytes, 0x3000, 0x04)
        remote_lvitem = kernel32.VirtualAllocEx(h_process.handle, 0, lvitem_size, 0x3000, 0x04)
        remote_point = kernel32.VirtualAllocEx(h_process.handle, 0, point_size, 0x3000, 0x04)

        if not remote_text or not remote_lvitem or not remote_point:
            raise RuntimeError("VirtualAllocEx failed during restore.")

        buf = ctypes.create_unicode_buffer(text_max)

        # optional: reduce flicker / “shuffle”
        win32gui.SendMessage(lv_hwnd, win32con.WM_SETREDRAW, 0, 0)

        for i in range(count):
            item = LVITEMW()
            item.mask = LVIF_TEXT
            item.iItem = i
            item.iSubItem = 0
            item.pszText = ctypes.cast(remote_text, wintypes.LPWSTR)
            item.cchTextMax = text_max

            written = ctypes.c_size_t(0)
            ok = kernel32.WriteProcessMemory(
                h_process.handle,
                remote_lvitem,
                ctypes.byref(item),
                lvitem_size,
                ctypes.byref(written),
            )
            if not ok:
                continue

            win32gui.SendMessage(lv_hwnd, LVM_GETITEMTEXTW, i, remote_lvitem)

            read = ctypes.c_size_t(0)
            ok = kernel32.ReadProcessMemory(
                h_process.handle,
                remote_text,
                ctypes.byref(buf),
                text_bytes,
                ctypes.byref(read),
            )
            if not ok:
                continue

            name = buf.value
            if not name:
                continue

            pos = layout.get(name)
            if not pos:
                continue

            x, y = pos
            pt = wintypes.POINT(x, y)
            ok = kernel32.WriteProcessMemory(
                h_process.handle,
                remote_point,
                ctypes.byref(pt),
                point_size,
                None
            )
            if not ok:
                continue

            win32gui.SendMessage(lv_hwnd, LVM_SETITEMPOSITION32, i, remote_point)
            restored += 1

    finally:
        # re-enable redraw and refresh view (safe)
        try:
            win32gui.SendMessage(lv_hwnd, win32con.WM_SETREDRAW, 1, 0)
            win32gui.InvalidateRect(lv_hwnd, None, True)
            win32gui.UpdateWindow(lv_hwnd)
        except Exception:
            pass

        if remote_text:
            kernel32.VirtualFreeEx(h_process.handle, remote_text, 0, 0x8000)
        if remote_lvitem:
            kernel32.VirtualFreeEx(h_process.handle, remote_lvitem, 0, 0x8000)
        if remote_point:
            kernel32.VirtualFreeEx(h_process.handle, remote_point, 0, 0x8000)

        try:
            win32api.CloseHandle(h_process)
        except Exception:
            pass

    return restored

