import importlib
import sys
from types import ModuleType


def test_ensure_langchain_pydantic_v1_shim_registers_module_when_missing(monkeypatch):
    target = "experiments.tools.scisage_outline_only_live"
    if target in sys.modules:
        del sys.modules[target]

    module = importlib.import_module(target)

    original_import_module = importlib.import_module
    original_langchain_module = sys.modules.pop("langchain_core.pydantic_v1", None)

    def fake_import_module(name, package=None):
        if name == "langchain_core.pydantic_v1":
            raise ModuleNotFoundError(name)
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    try:
        if "langchain_core.pydantic_v1" in sys.modules:
            del sys.modules["langchain_core.pydantic_v1"]

        module.ensure_langchain_pydantic_v1_shim()

        shim = sys.modules.get("langchain_core.pydantic_v1")
        assert isinstance(shim, ModuleType)
        assert hasattr(shim, "Field")
        assert hasattr(shim, "root_validator")
        assert hasattr(shim, "Extra")
    finally:
        if original_langchain_module is not None:
            sys.modules["langchain_core.pydantic_v1"] = original_langchain_module
        else:
            sys.modules.pop("langchain_core.pydantic_v1", None)


def test_ensure_langchain_schema_shim_registers_str_output_parser(monkeypatch):
    target = "experiments.tools.scisage_outline_only_live"
    if target in sys.modules:
        del sys.modules[target]

    module = importlib.import_module(target)

    original_import_module = importlib.import_module
    original_schema_module = sys.modules.pop("langchain.schema", None)

    def fake_import_module(name, package=None):
        if name == "langchain.schema":
            raise ModuleNotFoundError(name)
        return original_import_module(name, package)

    monkeypatch.setattr(importlib, "import_module", fake_import_module)

    try:
        if "langchain.schema" in sys.modules:
            del sys.modules["langchain.schema"]

        module.ensure_langchain_schema_shim()

        shim = sys.modules.get("langchain.schema")
        assert isinstance(shim, ModuleType)
        assert hasattr(shim, "StrOutputParser")
    finally:
        if original_schema_module is not None:
            sys.modules["langchain.schema"] = original_schema_module
        else:
            sys.modules.pop("langchain.schema", None)
