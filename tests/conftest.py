import ascii_colors
import pytest


@pytest.fixture(autouse=True, scope="session")
def _cleanup_ascii_colors_handlers():
    yield
    try:
        ascii_colors.ASCIIColors.clear_handlers()
    except Exception:
        pass
