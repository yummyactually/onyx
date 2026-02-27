# conftest.py
import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "qt: Qt widget tests requiring qtbot")

@pytest.fixture(autouse=False)
def isolated_window(qtbot, tmp_path, monkeypatch):
    """MainWindow that never loads / saves real cfg."""
    import main
    cfg_attr = next((a for a in ("CFG_PATH", "CFG") if hasattr(main, a)), None)
    if cfg_attr:
        monkeypatch.setattr(main, cfg_attr, tmp_path / "test_cfg.json")
    w = main.MainWindow()
    qtbot.addWidget(w)
    yield w
