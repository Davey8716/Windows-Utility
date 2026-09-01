from folder_creator.core.state_manager import StateManager
from folder_creator.features.templates.template_IO_layer import TemplatePaths, TemplateService
from folder_creator.features.tree.filesystem_builder import FolderStructureBuilder
from folder_creator.features.tree.outline_parser import parse_indented_text
from folder_creator.features.tree.tree_controller import TreeController
from pathlib import Path
from shutil import copy

class AppService:

    def __init__(self, tree_widget):
        self.tree_controller = TreeController(tree_widget)
        self.folder_builder = FolderStructureBuilder()
        self.template_service = TemplateService()
        self.state_manager = StateManager()
        self.template_paths =  TemplatePaths()
        self.state = self.state_manager.load_state()

    def add_folder(self):
        self.tree_controller.add_root_folder()

    def add_subfolder(self):
        self.tree_controller.add_subfolder()

    def remove_selected(self):
        self.tree_controller.remove_selected_folders()

    def remove_all(self):
        self.tree_controller.remove_all_folders()

    def build_tree(self, base_path, timestamp_mode=None):
        nodes = self.tree_controller.serialize_build_tree()
        return self.folder_builder.build(nodes, base_path, timestamp_mode)

    def save_template(self, parent):
        return self.template_service.save_from_tree(parent, self.tree_controller)
    
    def load_template_data(self, path):
        data = self.template_service.load_template(
            path,
            parse_indented_text,
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
