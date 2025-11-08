
"""
Entry point for the Dark Mode API Testing Tool.
"""

import os
from ui.main_window import APITesterApp


def main():
    os.makedirs("data", exist_ok=True)
    os.makedirs("asserts/icons", exist_ok=True)
    app = APITesterApp()
    app.mainloop()


if __name__ == "__main__":
    main()
