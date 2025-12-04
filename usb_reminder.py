# ===================================================================
#  USB Reminder – UI Helpers (pure GUI logic, safe to import anywhere)
# ===================================================================

# ---------------------------------------------------------------
#  Grey out / enable the three sub-toggles
# ---------------------------------------------------------------
def toggle_usb_options(self, enable: bool):
    state = "normal" if enable else "disabled"
    self.opt_idle.configure(state=state)
    self.opt_download.configure(state=state)
    self.opt_plug.configure(state=state)

# ---------------------------------------------------------------
#  Used when main USB switch is clicked
# ---------------------------------------------------------------

def on_usb_toggle(app, enabled: bool):
    print(f"[INFO] USB Reminder toggled → {enabled}")
    toggle_usb_options(app, enabled)

def toggle_mover_options(app, enable: bool):
    """
    Enable/disable the Screen Mover sub-switches (MMB + auto-align).
    """
    state = "normal" if enable else "disabled"
    app.mmb_switch.configure(state=state)
    app.auto_align_switch.configure(state=state)   # NEW stays here

def on_usb_reminder_toggle(self):
    enabled = self.screen_mover_var.get()
    on_usb_toggle(self, enabled)
    self.save_all_settings()
