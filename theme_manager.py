import customtkinter as ctk

# Dark = True, Light = False
def switch_theme(dark_mode: bool):
    if dark_mode:
        ctk.set_appearance_mode("Dark")
        print("[THEME] Switched to Dark Mode")
    else:
        ctk.set_appearance_mode("Light")
        print("[THEME] Switched to Light Mode")
