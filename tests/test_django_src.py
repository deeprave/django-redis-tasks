import io
import re
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.django_src import (
    DjangoTasksSourceError,
    apply_redis_default_to_tasktestcase,
    archive_url,
    cache_dir_name,
    extract_tasks_from_archive,
    installed_django_version,
    is_ignored_django_task_module,
    pytest_ignore_collect,
    register_django_tasks_collection,
    resolve_django_tasks_root,
    should_collect_django_tasks,
    should_skip_django_task_item,
)

# Resolver unit tests pass a version string in; they do not pin the suite to 6.1.
# Production uses django.get_version() (6.1.0 → "6.1", 6.1.1 → "6.1.1", 6.2 → "6.2").
_VERSIONS = ("6.1", "6.1.1", "6.2")


def _archive_bytes(version: str) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:

        def add(name: str, content: bytes) -> None:
            info = tarfile.TarInfo(name=name)
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))

        add(f"django-{version}/tests/tasks/__init__.py", b"")
        add(f"django-{version}/tests/tasks/test_tasks.py", b"# django tasks tests\n")
        add(f"django-{version}/tests/tasks/tasks.py", b"noop = None\n")
        add(f"django-{version}/tests/runtests.py", b"SHOULD_NOT_EXTRACT\n")
        add(f"django-{version}/django/__init__.py", b"SHOULD_NOT_EXTRACT\n")
    return buffer.getvalue()


def test_installed_django_version_is_django_get_version():
    import django

    assert installed_django_version() == django.get_version()


@pytest.mark.parametrize("version", _VERSIONS)
def test_cache_dir_name_matches_gitignore_tool_cache_pattern(version: str):
    assert cache_dir_name(version) == f".django-src-{version}_cache"


@pytest.mark.parametrize("version", _VERSIONS)
def test_archive_url_uses_github_tag_for_that_version(version: str):
    assert archive_url(version) == (
        f"https://github.com/django/django/archive/refs/tags/{version}.tar.gz"
    )


@pytest.mark.parametrize("version", _VERSIONS)
def test_resolve_uses_django_tests_root_env(tmp_path, monkeypatch, version: str):
    tests_root = tmp_path / "checkout" / "tests"
    (tests_root / "tasks").mkdir(parents=True)
    (tests_root / "tasks" / "test_tasks.py").write_text("# local\n", encoding="utf-8")
    monkeypatch.setenv("DJANGO_TESTS_ROOT", str(tests_root))

    resolved = resolve_django_tasks_root(
        version=version,
        project_root=tmp_path,
        download=lambda url, dest: pytest.fail("must not download"),
    )

    assert resolved == tests_root
    assert (resolved / "tasks" / "test_tasks.py").is_file()


@pytest.mark.parametrize("version", _VERSIONS)
def test_resolve_reuses_existing_version_cache_without_download(tmp_path, version: str):
    cache = tmp_path / cache_dir_name(version)
    (cache / "tasks").mkdir(parents=True)
    (cache / "tasks" / "test_tasks.py").write_text("# cached\n", encoding="utf-8")

    resolved = resolve_django_tasks_root(
        version=version,
        project_root=tmp_path,
        download=lambda url, dest: pytest.fail("must not download"),
    )

    assert resolved == cache
    assert (resolved / "tasks" / "test_tasks.py").read_text(encoding="utf-8") == (
        "# cached\n"
    )


def test_resolve_does_not_use_sibling_version_cache(tmp_path):
    old = tmp_path / cache_dir_name("6.1")
    (old / "tasks").mkdir(parents=True)
    (old / "tasks" / "test_tasks.py").write_text("# old\n", encoding="utf-8")
    archive = _archive_bytes("6.2")

    def download(url: str, dest: Path) -> None:
        assert url == archive_url("6.2")
        dest.write_bytes(archive)

    resolved = resolve_django_tasks_root(
        version="6.2",
        project_root=tmp_path,
        download=download,
    )

    assert resolved == tmp_path / cache_dir_name("6.2")
    assert not (resolved / "django").exists()
    assert not (resolved / "runtests.py").exists()
    assert (resolved / "tasks" / "test_tasks.py").is_file()
    assert (old / "tasks" / "test_tasks.py").read_text(encoding="utf-8") == "# old\n"


@pytest.mark.parametrize("version", _VERSIONS)
def test_extract_tasks_from_archive_only_keeps_tests_tasks(tmp_path, version: str):
    archive_path = tmp_path / "django.tar.gz"
    archive_path.write_bytes(_archive_bytes(version))
    dest = tmp_path / "extracted"
    extract_tasks_from_archive(archive_path, dest)
    names = {
        path.relative_to(dest).as_posix() for path in dest.rglob("*") if path.is_file()
    }
    assert names == {
        "tasks/__init__.py",
        "tasks/test_tasks.py",
        "tasks/tasks.py",
    }


@pytest.mark.parametrize("version", _VERSIONS)
def test_resolve_fails_with_version_and_expected_path(tmp_path, version: str):
    def download(url: str, dest: Path) -> None:
        dest.write_bytes(b"not a tar")

    expected = tmp_path / cache_dir_name(version) / "tasks" / "test_tasks.py"
    with pytest.raises(DjangoTasksSourceError, match=re.escape(version)) as exc_info:
        resolve_django_tasks_root(
            version=version,
            project_root=tmp_path,
            download=download,
        )
    assert str(expected) in str(exc_info.value)


def test_should_collect_django_tasks_for_ini_testpaths_only():
    root = Path("/repo").resolve()
    default_config = SimpleNamespace(
        rootpath=root,
        args=["tests"],
        getini=lambda name: ["tests"] if name == "testpaths" else [],
    )
    file_config = SimpleNamespace(
        rootpath=root,
        args=["tests/test_redis_backend.py"],
        getini=lambda name: ["tests"] if name == "testpaths" else [],
    )
    assert should_collect_django_tasks(default_config) is True
    assert should_collect_django_tasks(file_config) is False


def test_ignored_django_backend_modules():
    assert is_ignored_django_task_module(Path("tasks/test_dummy_backend.py"))
    assert is_ignored_django_task_module(Path("tasks/test_immediate_backend.py"))
    assert is_ignored_django_task_module(Path("tasks/test_custom_backend.py"))
    assert not is_ignored_django_task_module(Path("tasks/test_tasks.py"))


def test_skip_dummy_and_immediate_tasktestcase_methods():
    dummy_results = SimpleNamespace(
        cls=SimpleNamespace(__name__="TaskTestCase", __module__="tasks.test_tasks"),
        originalname="test_enqueue_task",
        name="test_enqueue_task",
    )
    default_is_dummy = SimpleNamespace(
        cls=SimpleNamespace(__name__="TaskTestCase", __module__="tasks.test_tasks"),
        originalname="test_using_correct_backend",
        name="test_using_correct_backend",
    )
    immediate_errors = SimpleNamespace(
        cls=SimpleNamespace(__name__="TaskTestCase", __module__="tasks.test_tasks"),
        originalname="test_task_error_invalid_exception",
        name="test_task_error_invalid_exception",
    )
    kept = SimpleNamespace(
        cls=SimpleNamespace(__name__="TaskTestCase", __module__="tasks.test_tasks"),
        originalname="test_module_path",
        name="test_module_path",
    )
    assert should_skip_django_task_item(dummy_results)
    assert should_skip_django_task_item(default_is_dummy)
    assert should_skip_django_task_item(immediate_errors)
    assert not should_skip_django_task_item(kept)


def test_register_collection_uses_cache_and_skips_download(tmp_path, monkeypatch):
    import sys

    cache = tmp_path / cache_dir_name("6.1")
    (cache / "tasks").mkdir(parents=True)
    (cache / "tasks" / "test_tasks.py").write_text("# cached\n", encoding="utf-8")
    config = SimpleNamespace(
        rootpath=tmp_path,
        args=["tests"],
        option=SimpleNamespace(ignore=None),
        getini=lambda name: ["tests"] if name == "testpaths" else [],
    )
    monkeypatch.chdir(tmp_path)

    resolved = register_django_tasks_collection(
        config,
        version="6.1",
        project_root=tmp_path,
        download=lambda url, dest: pytest.fail("must not download"),
    )

    assert resolved == cache
    assert str(cache) in sys.path
    assert str(cache) in config.args
    assert str(cache / "tasks" / "test_dummy_backend.py") in config.option.ignore
    assert str(cache / "tasks" / "test_immediate_backend.py") in config.option.ignore
    assert str(cache / "tasks" / "test_custom_backend.py") in config.option.ignore


def test_register_collection_skips_explicit_file_path(tmp_path):
    config = SimpleNamespace(
        rootpath=tmp_path,
        args=["tests/test_redis_backend.py"],
        getini=lambda name: ["tests"] if name == "testpaths" else [],
    )
    resolved = register_django_tasks_collection(
        config,
        version="6.1",
        project_root=tmp_path,
        download=lambda url, dest: pytest.fail("must not download"),
    )
    assert resolved is None
    assert config.args == ["tests/test_redis_backend.py"]


def test_pytest_ignore_collect_drops_dummy_immediate_custom_modules():
    config = SimpleNamespace()
    assert pytest_ignore_collect(Path("tasks/test_dummy_backend.py"), config) is True
    assert (
        pytest_ignore_collect(Path("tasks/test_immediate_backend.py"), config) is True
    )
    assert pytest_ignore_collect(Path("tasks/test_custom_backend.py"), config) is True
    assert pytest_ignore_collect(Path("tasks/test_tasks.py"), config) is None


def test_apply_redis_default_keeps_immediate_and_missing_aliases():
    cls = SimpleNamespace(
        _overridden_settings={
            "TASKS": {
                "default": {
                    "BACKEND": "django.tasks.backends.dummy.DummyBackend",
                    "QUEUES": ["default", "queue_1"],
                },
                "immediate": {
                    "BACKEND": "django.tasks.backends.immediate.ImmediateBackend",
                    "QUEUES": [],
                },
                "missing": {"BACKEND": "does.not.exist"},
            }
        }
    )
    apply_redis_default_to_tasktestcase(cls)
    tasks_cfg = cls._overridden_settings["TASKS"]
    assert tasks_cfg["default"]["BACKEND"] == "redis_tasks.backend.RedisBackend"
    assert tasks_cfg["default"]["QUEUES"] == ["default", "queue_1"]
    assert tasks_cfg["immediate"]["BACKEND"].endswith("ImmediateBackend")
    assert tasks_cfg["missing"]["BACKEND"] == "does.not.exist"


def test_django_task_source_is_not_committed():
    import subprocess

    listed = subprocess.check_output(
        ["git", "ls-files", ".django-src-*_cache", "**/tasks/test_tasks.py"],
        text=True,
    )
    assert listed.strip() == ""
