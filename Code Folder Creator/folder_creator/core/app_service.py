from folder_creator.core.state_manager import StateManager
from folder_creator.features.templates.template_IO_layer import TemplatePaths, TemplateService
from folder_creator.features.tree.nested_folder_manager import NestedFolderManager
from pathlib import Path
from shutil import copy

class AppService:

    def __init__(self, tree_widget):
        self.nested_manager = NestedFolderManager(tree_widget)
        self.template_service = TemplateService()
        self.state_manager = StateManager()
        self.template_paths =  TemplatePaths()
        self.state = self.state_manager.load_state()

    def add_folder(self):
        self.nested_manager.add_root_folder()

    def add_subfolder(self):
        self.nested_manager.add_subfolder()

    def remove_selected(self):
        self.nested_manager.remove_selected_folders()

    def remove_all(self):
        self.nested_manager.remove_all_folders()

    def build_tree(self, base_path, timestamp_mode=None):
        return self.nested_manager.build_folders(base_path, timestamp_mode)

    def save_template(self, parent):
        return self.template_service.save_from_tree(parent, self.nested_manager)
    
    def load_template_data(self, path):
        data = self.template_service.load_template(
            path,
            self.nested_manager.parse_indented_text
        )
        return data if data is not None else None

    def save_to_user_templates(self, path):
        src = Path(path)
        dst = self.template_paths.user_dir / src.name

        if src.resolve() != dst.resolve():
            copy(src, dst)

    def get_state(self, key, default=None):
        return self.state.get(key, default)

    def set_state(self, key, value):
        state = self.state_manager.load_state()
        state[key] = value
        self.state_manager.save_state(state)
        self.state = state
