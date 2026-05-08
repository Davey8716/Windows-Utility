# Windows 11 Folder Creator

If this tool saved you time or simplified your workflow, consider giving the repo a ⭐.

There’s also a sponsor option available if you’d like to support what ive made.

A Windows desktop app for building nested folder structures from a simple visual tree.

The app is built with Python and PySide6. It is designed for Windows 11 workflows where you regularly need project folders, client folders, content folders, development layouts, or repeatable template structures.

## Features

- Build nested folder structures from a drag-and-drop tree
- Add placeholder files such as `README.md`, `index.html`, `styles.css`, `.env`, `run.bat`, and more
- Save and load reusable templates
- Load templates from `.json`, `.txt`, and `.md` files
- Import real folder structures by dragging folders into the tree
- Sort folder trees alphabetically
- Search for folders inside large trees
- Set the nested build output to Desktop or any other directory
- Add optional date stamps using ISO, UK, or US date formats
- Choose light or dark accessible themes
- Remember app state between launches
- Optional build actions: open output folder, minimize app, or close app after build

## Screenshots

Screenshots are included in the repository under:

/Gui Examples/

## Requirements

- Windows 11
- Python 3.10 or newer
- PySide6

This project uses Windows APIs for Desktop folder detection and app behavior, so it is intended for Windows.

## Run From Source

Clone the repository, then run the app from the `Build` folder:

```powershell
git clone https://github.com/Davey8716/Win-11-Folder_Creator.git
cd Win-11-Folder_Creator\Build
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install PySide6
python main.py


## Usage

### Nested Folder Creator

Use this mode when you want to build a larger folder structure.

1. Choose an output location.
2. Add folders and subfolders to the tree.
3. Optionally add default files to selected folders.
4. Optionally enable date stamping.
5. Click the build button to create the structure.

You can drag folders around in the tree to change hierarchy:

- Drag onto another folder to make it a subfolder.
- Drag below folders to create a new parent-level item.

## Templates

Templates can be saved and loaded as:

- `.json`
- `.txt`
- `.md`

User templates and app state are stored in:

%LOCALAPPDATA%\FolderCreator

The app also includes default templates for common workflows, including:

- Architects
- Creative writers
- Data scientists
- Game developers
- IT administrators
- Photographers
- Project management
- Researchers
- Software developers
- Video editing

Right-click the `User Templates` dropdown in the app to open the user templates folder.

## Text Template Format

Text and Markdown templates use indentation to define the folder hierarchy.

Example:

```text
Project
    Assets
        Images
        Video
    Documents
    Exports
```

Blank lines are ignored. Lines starting with `#` are treated as comments.

## Hotkeys

| Shortcut | Action |
| --- | --- |
| `Ctrl + N` | Add folder |
| `Ctrl + Shift + N` | Add subfolder |
| `Ctrl + S` | Save template |
| `Ctrl + O` | Load template |
| `F2` | Rename selected folder |
| `Delete` | Remove selected folder |

## Building An EXE

You can package the app into an .Exe complete with icon using my other handy app found here..

https://github.com/Davey8716/Win-11-Python-EXE-Builder


## Project Structure

Build/
    main.py                     App entry point and main window
    app_service.py              Coordinates managers and persistent state
    nested_folder_manager.py    Tree serialization, parsing, and folder building
    nested_ui_controller.py     Nested builder UI behavior
    system_paths.py             Windows path helpers
    smart_tree_widget.py        Drag/drop and keyboard-enabled tree widget
    template_IO_layer.py        Template loading and saving
    state_manager.py            Persistent app state
    theme_controller.py         Theme loading and application
    Default Templates/          Bundled starter templates
    Icons/                      App icons
    themes/                     Theme files


## Notes

- Folder names are limited to 64 characters in the app.
- Invalid Windows folder characters are blocked: `< > : " / \ | ? *`
- Files dropped into the tree are ignored when importing folder structures.
- Default templates are copied into `%LOCALAPPDATA%\FolderCreator\default_templates` on first run.

## License

This is published under the MIT License.
