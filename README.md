
# Windows Resurface


Windows Resurface is a Windows 11 desktop utility hub built with Python and PySide6.

It brings a set of everyday Windows actions into one always-available app: window moving, desktop cleanup, backup helpers, bookmark export, recycle bin cleanup, external drive reminders, and quick access to deeper Windows tools. The app runs as a single instance, stays available in the system tray, and remembers its state between launches.

> If you just want to use it, download the packaged release, extract it, and run `Windows Resurface.exe`. You do not need to set up Python unless you want to inspect or modify the source.

Windows Resurface is already usable as-is, and you are welcome to run with it. It is still a work in progress, and I will keep refining it over time, but the current build is here to be used, tested, and built on.

Feel free to clone the repo, explore the code, adapt it to your own setup, and make it part of your own workflow.

## Features

- Move, minimize, or maximize windows from a contrast-aware title-bar dock, with configurable mouse activation and global keyboard shortcuts
- Activate supported minimize, maximize, restore, and close buttons by dwelling over them, with calibration for custom title bars and optional taskbar-preview restoration
- Keep the app always on top, switch theme, toggle tooltips, and enable Zen Mode to hide desktop icons
- Warn before lock, log out, restart, or shutdown when external drives are still connected
- Show plug and unplug notifications for removable drives
- Capture desktop screenshots per monitor into a backup folder
- Save and restore desktop icon layouts
- Back up pinned taskbar shortcuts
- Export bookmarks to HTML from Brave, Chrome, Edge, Firefox, Opera, Opera GX, Vivaldi, and Chromium
- Create a desktop folder from a typed name
- Launch the bundled `Code Folder Creator` companion tool if it is present
- Open, empty, or auto-clean the Recycle Bin by age
- Open useful Windows tools such as Control Panel, Device Manager, Services, Event Viewer, Firewall, Startup Apps, Storage Sense, and more
- Run quick maintenance actions such as `ipconfig`, DNS flush, DHCP renew, temp cleanup, SFC, DISM, and CHKDSK
- View drive usage and safely eject removable drives from the advanced panel

## Requirements

- Windows 11
- Python 3.10 or newer if running from source
- Python packages:
  - `PySide6`
  - `pywin32`
  - `psutil`
  - `pynput`
  - `Pillow`
  - `uiautomation`
  - `opencv-python-headless`

AutoHotkey v2 is optional. It is required only for restoring a minimized window
by dwelling over its taskbar preview; caption-button hover controls continue to
work without it.

This app uses Windows-specific APIs and utilities, so it is not intended for macOS or Linux.

## Run A Packaged Release

If you downloaded a release build, extract it and run the included `Windows Resurface.exe`.

When you close the main window, the app hides to the system tray instead of fully exiting. Click the tray icon to reopen it, or use the tray menu to quit.

## Run From Source

From the repository root:

```powershell
cd "Code Windows Resurface"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

## How It Is Organised

### Main window

The left side is the everyday tools area:

- `User Interface`: theme, always-on-top, tooltips, desktop Zen Mode, power actions, minimize-after-use
- `Screen Mover`: master enable control, mouse trigger, and configurable keyboard shortcuts for moving, minimizing, or maximizing the foreground window
- `Hover Window Controls`: dwell timing, caption-button activation, taskbar status, calibration, export, and learned-profile management
- `Monitor Rules`: automatically place newly opened application windows on an assigned display, preserving their current size, restoring captured geometry, or maximizing them
- `External Drive Reminder Options`: connected drive display plus leave and plug/unplug reminders
- `General Organising Utilities`: screenshots, desktop layout backup/restore, bookmarks export, taskbar backup, master backup path
- `Folder Utilities`: launch Folder Creator or create a named desktop folder
- `Recycle Bin Actions`: open, empty, or auto-clean older items

### Advanced panel

The right side panel contains:

- `Windows Utilities`: grouped launchers for built-in Windows tools
- `Maintenance & Quick Actions`: cleanup, quick-open, repair, and networking shortcuts with live output
- `Drive Space Display`: drive usage list, open-on-double-click, safe removal on removable drives

## Saved Files And Settings

The app stores its settings here:

- `%LOCALAPPDATA%\Windows Resurface\app_state.json`
- `%LOCALAPPDATA%\Windows Resurface\hover-window-controls\vision-cache` for learned caption profiles

On the first integrated run, compatible preferences and learned profiles are
copied from the standalone `%LOCALAPPDATA%\Hover Window Controls` location (and
its older `No Click Min Max Restore` location). The originals are not removed.

Screen Mover settings are stored with the rest of Windows Resurface. They are
independent of the standalone Browser App Mover application and are not imported
from or written to its settings file.

The Screen Mover supports shortcuts for Far Left, Left, Right, Far Right,
Minimize, and Maximize. Empty shortcut fields are disabled. The tray menu's
`Screen Mover Enabled` action mirrors the master control in the main window, and
`Reset Screen Mover Defaults` restores the middle mouse trigger and clears all
shortcuts without changing other app settings.

Monitor Rules are evaluated from top to bottom while Windows Resurface is open
or hidden in the system tray. Rules can match an exact executable path or an
executable name, with optional title and window-class filters. Existing windows
are left untouched until a rule is explicitly tested; newly opened matching
windows are moved automatically. A rule can optionally be reapplied if its
managed window is dragged to another monitor. If the assigned display is not
connected, the window is left alone.

The visible title-bar mover dock is suppressed for executables installed beneath
a Steam library's `steamapps\common` directory. Configured keyboard shortcuts
and mouse-trigger mover actions remain available for those game windows.

The master backup path is configurable inside the app and defaults to your home folder. Depending on which tools you use, Windows Resurface can create files such as:

- `TaskBarApps\` for taskbar shortcut backups
- `Bookmarks\` for exported browser bookmark files
- `Desktop Icon Layout\desktop_icon_layout.json` for desktop icon positions
- `Desktop Screenshots\DesktopScreenshot_Monitor*.png` for per-monitor screenshots

## Notes

- Launching the app again focuses the existing instance instead of opening a second copy.
- Some actions may prompt for administrator approval depending on the Windows tool being opened or command being run.
- A few Windows utilities depend on Windows edition or permissions. For example, some management consoles may not be available on all Home installations.
- The `Folder Creator` button expects the companion tool to remain in the repo at `Code Folder Creator/`.
- Packaged builds should include the `Icon Pngs/` folder beside the executable or as bundled application data. The Screen Mover falls back to blue text symbols if those images are unavailable.

## Project Structure

- `Code Windows Resurface/main.py` main app launcher; `resurface/` contains core, UI, and feature packages
- `Icon Pngs/` black and white Screen Mover dock actions
- `Code Folder Creator/main.py` companion launcher; `folder_creator/` contains core, UI, and feature packages
- `Shared/` shared app state defaults and JSON state manager
- `Tests/` automated tests for shared state handling and screen mover behavior
