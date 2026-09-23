"""Smoke-check each Streamlit screen by opening it with AppTest."""

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "ui"


def ui_scripts():
    """Return existing Streamlit entry points, in a stable order."""
    candidates = [UI_ROOT / "app.py", UI_ROOT / "viewer.py"]
    pages_dir = UI_ROOT / "pages"
    if pages_dir.is_dir():
        candidates.extend(sorted(pages_dir.glob("*.py")))
    return [path for path in candidates if path.is_file()]


class UiSmokeTests(unittest.TestCase):
    def test_existing_streamlit_screens_open_without_exceptions(self):
        # AppTest executes scripts in-process. Make the project packages
        # importable even when this file is started as `python tests/...`.
        if str(ROOT) not in sys.path:
            sys.path.insert(0, str(ROOT))

        from streamlit.testing.v1 import AppTest

        scripts = ui_scripts()
        if not scripts:
            self.skipTest(f"No Streamlit scripts found under {UI_ROOT}")

        failures = []
        for script in scripts:
            with self.subTest(script=str(script.relative_to(ROOT))):
                try:
                    app = AppTest.from_file(str(script), default_timeout=30).run()
                except Exception as exc:
                    failures.append(
                        f"{script.relative_to(ROOT)} raised {type(exc).__name__}: {exc}"
                    )
                    continue

                exceptions = list(app.exception)
                if exceptions:
                    details = "\n".join(
                        f"  {type(item.value).__name__}: {item.value}" for item in exceptions
                    )
                    failures.append(
                        f"{script.relative_to(ROOT)} raised Streamlit exception(s):\n{details}"
                    )

        if failures:
            self.fail("One or more Streamlit screens failed to open:\n" + "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
