"""Executable module boundaries for the modular monolith, without a database."""

import ast
import importlib.metadata
import json
import tomllib
from pathlib import Path

from argon2 import PasswordHasher

import onefde

BACKEND = Path(__file__).resolve().parents[2]
PACKAGE = BACKEND / "src/onefde"


def sources():
    return {
        ".".join(
            ("onefde", *p.relative_to(PACKAGE).with_suffix("").parts)
        ).removesuffix(".__init__"): p
        for p in PACKAGE.rglob("*.py")
    }


def imported_modules(path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            yield from (a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"Use explicit absolute production imports: {path}"
            if node.module:
                yield node.module
                yield from (node.module + "." + a.name for a in node.names)


def test_layer_dependencies_point_inward():
    for module, path in sources().items():
        dependencies = list(imported_modules(path))
        assert not any(
            d == "app" or d.startswith(("app.", "tests.", "scripts."))
            for d in dependencies
        ), module
        if module.startswith("onefde.core."):
            assert not any(
                d.startswith(
                    (
                        "onefde.modules",
                        "onefde.infrastructure",
                        "onefde.entrypoints",
                        "onefde.bootstrap",
                        "onefde.worker",
                        "fastapi",
                        "sqlalchemy",
                    )
                )
                for d in dependencies
            ), module
        if (
            module.startswith("onefde.infrastructure.")
            and module != "onefde.infrastructure.db.metadata"
        ):
            assert not any(
                d.startswith(
                    (
                        "onefde.modules",
                        "onefde.entrypoints",
                        "onefde.bootstrap",
                        "onefde.worker",
                    )
                )
                for d in dependencies
            ), module
        if module.startswith("onefde.modules."):
            assert not any(
                d.startswith(
                    (
                        "onefde.entrypoints",
                        "onefde.bootstrap",
                        "onefde.worker",
                        "openhands",
                    )
                )
                for d in dependencies
            ), module
            if not module.endswith((".router", ".dependencies")):
                assert not any(
                    d.startswith(("fastapi", "starlette", "onefde.infrastructure.web"))
                    or d.endswith((".router", ".dependencies"))
                    for d in dependencies
                ), module
            if module.startswith("onefde.modules.auth."):
                assert not any(
                    d.startswith(
                        (
                            "onefde.modules.engagements",
                            "onefde.modules.tasks",
                            "onefde.modules.fde",
                            "onefde.modules.knowledge",
                        )
                    )
                    for d in dependencies
                ), module
            if module.startswith("onefde.modules.engagements."):
                assert not any(
                    d.startswith(
                        (
                            "onefde.modules.tasks",
                            "onefde.modules.fde",
                            "onefde.modules.knowledge",
                        )
                    )
                    for d in dependencies
                ), module
            if module.startswith("onefde.modules.tasks."):
                assert not any(
                    d.startswith(
                        ("onefde.modules.fde", "onefde.modules.knowledge")
                    )
                    for d in dependencies
                ), module
            if module.startswith("onefde.modules.fde."):
                assert not any(
                    d.startswith("onefde.modules.knowledge") for d in dependencies
                ), module


def test_production_import_graph_has_no_cycles():
    files = sources()
    graph = {
        name: {d for d in imported_modules(path) if d in files and d != name}
        for name, path in files.items()
    }
    visited = set()

    def visit(name, stack):
        assert name not in stack, "Import cycle: " + " -> ".join((*stack, name))
        if name in visited:
            return
        for dependency in graph[name]:
            visit(dependency, (*stack, name))
        visited.add(name)

    for name in graph:
        visit(name, ())


def test_business_commands_leave_commit_to_caller():
    for path in (PACKAGE / "modules/tasks/commands").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        commits = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in ("commit", "rollback")
        ]
        assert not commits, f"Command must share the caller transaction: {path.name}"


def test_test_helpers_are_independent_of_test_cases():
    for path in (BACKEND / "tests").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.ImportFrom)
                and node.module
                and node.module.startswith("tests.")
            ):
                assert not any(
                    part.startswith("test_") or part == "conftest"
                    for part in node.module.split(".")
                ), str(path)


def test_application_is_an_installed_src_package():
    assert Path(onefde.__file__).resolve() == (PACKAGE / "__init__.py").resolve()
    distribution = importlib.metadata.distribution("onefde-backend")
    project = tomllib.loads((BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    assert distribution.version == project["project"]["version"]
    assert not (BACKEND / "app").exists(), (
        "Retire the old flat package after moving its sources"
    )


def test_runtime_openapi_matches_committed_contract_without_database():
    from onefde.core.config import Settings
    from onefde.entrypoints.api import create_app

    settings = Settings(
        _env_file=None,
        environment="development",
        cookie_secure=False,
        database_url="postgresql+psycopg://unused:unused@localhost/unused",
        owner_username="founder",
        owner_password_hash=PasswordHasher().hash("architecture-test-only"),
        trusted_origin="http://localhost:8000",
    )
    app = create_app(settings)
    try:
        expected = json.loads(
            (BACKEND.parent / "docs/architecture/openapi.implemented.json").read_text(
                encoding="utf-8"
            )
        )
        assert app.openapi() == expected
    finally:
        app.state.engine.dispose()
