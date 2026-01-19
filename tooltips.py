
import tkinter as tk

class CtkTooltip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tip_window = None
        self.after_id = None

        # Gather all actual hoverable child widgets
        targets = [widget]

        for attr in ("_canvas", "_label", "_text_label", "_fg_label", "_border_frame"):
            if hasattr(widget, attr):
                obj = getattr(widget, attr)
                if obj:
                    targets.append(obj)

        if hasattr(widget, "_windows"):
            for win in widget._windows:
                targets.append(win)

        # Apply bindings to all relevant sub-widgets
        for t in targets:
            try:
                t.bind("<Enter>", self.schedule, add="+")
                t.bind("<Leave>", self.hide, add="+")
                t.bind("<Button-1>", self.hide, add="+")
            except:
                pass

    # ------------------------------------------------------
    # Schedules showing the tooltip
    # ------------------------------------------------------
    
    def schedule(self, event=None):
        # Cancel previous timer
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

        # Start new timer
        self.after_id = self.widget.after(self.delay, self.show)

    # ------------------------------------------------------
    # Shows the tooltip IF globally enabled
    # ------------------------------------------------------
    
    def show(self):
        # Global tooltip toggle (check root window)
        root = self.widget.winfo_toplevel()
        if hasattr(root, "tooltips_enabled"):
            if not root.tooltips_enabled:
                return

        if self.tip_window:
            return

        # Position tooltip near cursor
        x = self.widget.winfo_rootx() + 40
        y = self.widget.winfo_rooty() + 25

        # Create popup
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.lift()
        tw.attributes("-topmost", True)

        label = tk.Label(
            tw,
            text=self.text,
            background="#1E1E1E",
            foreground="white",
            relief="solid",
            borderwidth=1,
            padx=6,
            pady=4,
            font=("Rubik UI", 15)
        )
        label.pack()

    def hide(self, event=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
