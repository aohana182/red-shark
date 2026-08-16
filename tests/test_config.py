import sys

from dictate import config


def test_project_root_is_repo_root_when_not_frozen():
    assert (config.PROJECT_ROOT / "dictate" / "config.py").exists()


def test_project_root_is_exe_directory_when_frozen(tmp_path):
    fake_exe = tmp_path / "dictate.exe"
    fake_exe.touch()
    original_frozen = getattr(sys, "frozen", None)
    original_executable = sys.executable
    sys.frozen = True
    sys.executable = str(fake_exe)
    try:
        assert config._resolve_project_root() == tmp_path
    finally:
        if original_frozen is None:
            del sys.frozen
        else:
            sys.frozen = original_frozen
        sys.executable = original_executable
