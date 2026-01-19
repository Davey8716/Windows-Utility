import customtkinter as ctk

# ===================================================================
#  Collapsible Section with Auto-Theme Arrow Colour
# ===================================================================

class CollapsibleSection:
    def __init__(self, parent, title_text, section_id, initial_open=True):
        self.parent = parent
        self.section_id = section_id   # NEW
        self.open = initial_open

        # A wrapper that keeps header + content together
        self.wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        self.wrapper.pack(fill="x", pady=(10, 0))

        # Header row
        self.header = ctk.CTkFrame(self.wrapper, fg_color="transparent")
        self.header.pack(fill="x", pady=(0, 4))


        self.label = ctk.CTkLabel(
            self.header,
            text=title_text,
            font=("Rubik UI", 15, "bold"),
            text_color="#008DFA"    # ← CTk Blue
            
        )
        self.label.pack(side="left", padx=10)

        # Toggle button
        self.button = ctk.CTkButton(
            self.header,
            text="▼" if initial_open else "▶",
            width=30,
            height=20,
            command=self.toggle,
            font=("Rubik UI", 18),
            fg_color="transparent",
            hover_color="#202020"
        )
        self.button.pack(side="right", padx=10)

        # Apply correct arrow colour depending on theme
        self.update_arrow_color()

        # Content frame
        self.content = ctk.CTkFrame(self.wrapper)

        if initial_open:
            self.content.pack(fill="x", expand=True, pady=(0, 10), padx=10)

    # ---------------------------------------------------------
    # NEW: automatic arrow colour based on Dark/Light mode
    # ---------------------------------------------------------
    
    def update_arrow_color(self):
        mode = ctk.get_appearance_mode()
        if mode == "Dark":
            self.button.configure(text_color="white")
        else:
            self.button.configure(text_color="black")

    def toggle(self):
        if self.open:
            self.content.pack_forget()
            self.button.configure(text="▶")
        else:
            self.content.pack(fill="x", pady=(0, 10), padx=10)
            self.button.configure(text="▼")

        self.open = not self.open

        # Notify app to shrink/expand window
        try:
            app = self.parent.winfo_toplevel()
            if hasattr(app, "resize_to_fit"):
                app.resize_to_fit()
        except Exception:
            pass

        # Save section states
        try:
            app = self.parent.winfo_toplevel()
            if hasattr(app, "save_section_states"):
                app.save_section_states()
        except Exception:
            pass