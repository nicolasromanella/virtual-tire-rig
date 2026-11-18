# =============================================================================
# TYRE RIG
# Starts the window of the virtual tyre test rig. Run: python main.py
# =============================================================================

try:
    from interface._theme import ThemedApp as App     # optional extra; without it the normal app runs
except ImportError:
    from interface.app import App

if __name__ == "__main__":
    App().run()
