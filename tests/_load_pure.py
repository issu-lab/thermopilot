"""Load dependency-light integration modules without Home Assistant installed."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "custom_components" / "thermopilot"
PACKAGE = "thermopilot_pure"


def _load(name: str):
    package = sys.modules.setdefault(PACKAGE, ModuleType(PACKAGE))
    package.__path__ = [str(SOURCE)]
    full_name = f"{PACKAGE}.{name}"
    if full_name in sys.modules:
        return sys.modules[full_name]
    spec = spec_from_file_location(full_name, SOURCE / f"{name}.py")
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {name}")
    module = module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


const = _load("const")
models = _load("models")
