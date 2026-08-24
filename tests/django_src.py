"""Resolve Django's tests/tasks tree for the installed Django version."""

from __future__ import annotations

import os
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

DJANGO_TESTS_ROOT_ENV = "DJANGO_TESTS_ROOT"
IGNORED_TASK_MODULES = frozenset(
    {
        "test_dummy_backend.py",
        "test_immediate_backend.py",
        "test_custom_backend.py",
    }
)
SKIP_TASKTESTCASE_METHODS = frozenset(
    {
        "test_using_correct_backend",
        "test_enqueue_task",
        "test_enqueue_task_async",
        "test_get_backend",
        "test_task_error_invalid_exception",
        "test_task_error_unknown_module",
    }
)

Download = Callable[[str, Path], None]


class DjangoTasksSourceError(Exception):
    """Django's tests/tasks tree could not be resolved for this version."""


def installed_django_version() -> str:
    """PEP 440 string matching Django's GitHub tag (``6.1``, ``6.1.1``, ``6.2``)."""
    import django

    return django.get_version()


def cache_dir_name(version: str) -> str:
    return f".django-src-{version}_cache"


def archive_url(version: str) -> str:
    return f"https://github.com/django/django/archive/refs/tags/{version}.tar.gz"


def cache_root(project_root: Path, version: str) -> Path:
    return project_root / cache_dir_name(version)


def expected_test_tasks_path(pythonpath_root: Path) -> Path:
    return pythonpath_root / "tasks" / "test_tasks.py"


def is_ignored_django_task_module(path: Path) -> bool:
    return path.name in IGNORED_TASK_MODULES and path.parent.name == "tasks"


def should_skip_django_task_item(item: Any) -> bool:
    cls = getattr(item, "cls", None)
    if cls is None:
        return False
    if getattr(cls, "__name__", None) != "TaskTestCase":
        return False
    if getattr(cls, "__module__", None) != "tasks.test_tasks":
        return False
    name = getattr(item, "originalname", None) or getattr(item, "name", "")
    return name in SKIP_TASKTESTCASE_METHODS


def should_collect_django_tasks(config: Any) -> bool:
    root = Path(config.rootpath)
    testpaths = [Path(path) for path in (config.getini("testpaths") or [])]
    allowed_dirs = {
        path.resolve() if path.is_absolute() else (root / path).resolve()
        for path in testpaths
    }
    args = list(getattr(config, "args", []) or [])
    if not args:
        return True
    for arg in args:
        path_str = str(arg).split("::", 1)[0]
        path = Path(path_str)
        resolved = path.resolve() if path.is_absolute() else (root / path).resolve()
        if resolved.is_file() or resolved.suffix == ".py":
            return False
        if allowed_dirs and resolved not in allowed_dirs:
            return False
    return True


def extract_tasks_from_archive(archive_path: Path, dest_root: Path) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tar:
        for member in tar.getmembers():
            parts = Path(member.name).parts
            if ".." in parts:
                continue
            try:
                tests_index = parts.index("tests")
            except ValueError:
                continue
            if tests_index + 1 >= len(parts) or parts[tests_index + 1] != "tasks":
                continue
            relative = Path(*parts[tests_index + 1 :])
            if ".." in relative.parts:
                continue
            target = dest_root / relative
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with extracted, target.open("wb") as output:
                shutil.copyfileobj(extracted, output)


def download_url_to_path(url: str, dest: Path) -> None:
    try:
        with urllib.request.urlopen(url) as response, dest.open("wb") as output:
            shutil.copyfileobj(response, output)
    except (urllib.error.URLError, OSError) as exc:
        raise DjangoTasksSourceError(
            f"Could not download Django source from {url}"
        ) from exc


def _unpack_archive_into_cache(
    archive_path: Path, dest_root: Path, version: str
) -> None:
    expected = expected_test_tasks_path(dest_root)
    parent = dest_root.parent
    with tempfile.TemporaryDirectory(
        prefix=f".django-src-{version}_", dir=parent
    ) as tmp:
        extracted = Path(tmp) / "extracted"
        try:
            extract_tasks_from_archive(archive_path, extracted)
        except tarfile.TarError as exc:
            raise DjangoTasksSourceError(
                f"Could not resolve Django {version} tests/tasks; expected {expected}"
            ) from exc
        if not expected_test_tasks_path(extracted).is_file():
            raise DjangoTasksSourceError(
                f"Could not resolve Django {version} tests/tasks; expected {expected}"
            )
        staging = parent / f".django-src-{version}_cache.tmp"
        if staging.exists():
            shutil.rmtree(staging)
        shutil.move(str(extracted), str(staging))
        os.replace(staging, dest_root)


def resolve_django_tasks_root(
    *,
    version: str,
    project_root: Path,
    env: Mapping[str, str] | None = None,
    download: Download | None = None,
) -> Path:
    """Return the pythonpath root whose ``tasks`` package is Django's tests/tasks."""
    environ = os.environ if env is None else env
    tests_root = environ.get(DJANGO_TESTS_ROOT_ENV)
    if tests_root:
        root = Path(tests_root)
        expected = expected_test_tasks_path(root)
        if not expected.is_file():
            raise DjangoTasksSourceError(
                f"Could not resolve Django {version} tests/tasks; expected {expected}"
            )
        return root

    dest_root = cache_root(project_root, version)
    expected = expected_test_tasks_path(dest_root)
    if expected.is_file():
        return dest_root

    url = archive_url(version)
    fetch = download_url_to_path if download is None else download
    parent = dest_root.parent
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".django-src-{version}_dl_", dir=parent
    ) as tmp:
        archive_path = Path(tmp) / "django.tar.gz"
        try:
            fetch(url, archive_path)
        except DjangoTasksSourceError:
            raise
        except OSError as exc:
            raise DjangoTasksSourceError(
                f"Could not resolve Django {version} tests/tasks; expected {expected}"
            ) from exc
        _unpack_archive_into_cache(archive_path, dest_root, version)
    if not expected.is_file():
        raise DjangoTasksSourceError(
            f"Could not resolve Django {version} tests/tasks; expected {expected}"
        )
    return dest_root


REDIS_TASK_BACKEND = "redis_tasks.backend.RedisBackend"


def apply_redis_default_to_tasktestcase(cls: Any) -> None:
    """Keep Django's TaskTestCase aliases; point default at RedisBackend."""
    overridden = getattr(cls, "_overridden_settings", None)
    if not isinstance(overridden, dict):
        return
    tasks_cfg = overridden.get("TASKS")
    if not isinstance(tasks_cfg, dict) or "default" not in tasks_cfg:
        return
    default_cfg = dict(tasks_cfg["default"])
    default_cfg["BACKEND"] = REDIS_TASK_BACKEND
    tasks_cfg = dict(tasks_cfg)
    tasks_cfg["default"] = default_cfg
    overridden["TASKS"] = tasks_cfg


def register_django_tasks_collection(
    config: Any,
    *,
    version: str | None = None,
    project_root: Path | None = None,
    download: Download | None = None,
) -> Path | None:
    """Put Django's tests/tasks on sys.path and pytest's collection args."""
    if not should_collect_django_tasks(config):
        return None
    resolved_version = version or installed_django_version()
    root = project_root or Path(config.rootpath)
    pythonpath_root = resolve_django_tasks_root(
        version=resolved_version,
        project_root=root,
        download=download,
    )
    root_str = str(pythonpath_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    add_line = getattr(config, "addinivalue_line", None)
    if callable(add_line):
        add_line("pythonpath", root_str)
    args = getattr(config, "args", None)
    if isinstance(args, list) and root_str not in args:
        args.append(root_str)
    option = getattr(config, "option", None)
    if option is not None:
        ignored = list(getattr(option, "ignore", None) or [])
        for name in IGNORED_TASK_MODULES:
            ignored.append(str(pythonpath_root / "tasks" / name))
        option.ignore = ignored
    return pythonpath_root


def pytest_ignore_collect(collection_path: Path, config: Any) -> bool | None:
    if is_ignored_django_task_module(Path(collection_path)):
        return True
    return None


def pytest_collection_modifyitems(config: Any, items: list[Any]) -> None:
    import pytest

    skip = pytest.mark.skip(
        reason="DummyBackend or ImmediateBackend behaviour excluded for RedisBackend"
    )
    for item in items:
        item_path = getattr(item, "path", None) or getattr(item, "fspath", None)
        ignored_module = item_path is not None and is_ignored_django_task_module(
            Path(str(item_path))
        )
        if ignored_module or should_skip_django_task_item(item):
            item.add_marker(skip)


def pytest_collection_finish(session: Any) -> None:
    try:
        from tasks.test_tasks import TaskTestCase
    except ImportError:
        return
    apply_redis_default_to_tasktestcase(TaskTestCase)
