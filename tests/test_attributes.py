"""Static checks that need no Home Assistant.

The first of these exists because an attribute was read and never assigned, and
both ruff and mypy passed it, because the file cannot be imported without Home
Assistant installed. It shipped and crashed setup.

    python3 -m unittest tests.test_attributes
"""

from __future__ import annotations

import ast
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "custom_components" / "abode_power_tariffs"

# Attributes provided by Home Assistant base classes rather than assigned here.
INHERITED = {
    "hass",
    "entity_id",
    "platform",
    "registry_entry",
    "device_entry",
    "config_entry",
    "runtime_data",
    "options",
    "data",
    "title",
    "entry_id",
    "domain",
    "state",
    "attributes",
    "context",
    "flow_id",
    "handler",
    "cur_step",
    "source",
    "unique_id",
    "config",
    "states",
    "services",
    "bus",
    "loop",
}


def _python_files() -> list[Path]:
    return sorted(PACKAGE.glob("*.py"))


class TestAttributesAreAssigned(unittest.TestCase):
    """Every self.<name> that is read must be assigned somewhere in the class.

    Base classes defined inside this package are followed, so an attribute set
    in the shared base entity counts for every subclass.
    """

    def _class_nodes(self) -> dict[str, tuple[Path, ast.ClassDef]]:
        found: dict[str, tuple[Path, ast.ClassDef]] = {}
        for path in _python_files():
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    found[node.name] = (path, node)
        return found

    @staticmethod
    def _assigned_in(node: ast.ClassDef) -> set[str]:
        assigned: set[str] = set()
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute) and isinstance(child.value, ast.Name):
                if child.value.id == "self" and isinstance(
                    child.ctx, (ast.Store, ast.Del)
                ):
                    assigned.add(child.attr)
            elif isinstance(child, ast.AnnAssign) and isinstance(
                child.target, ast.Attribute
            ):
                target = child.target
                if isinstance(target.value, ast.Name) and target.value.id == "self":
                    assigned.add(target.attr)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assigned.add(child.name)
            elif isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        assigned.add(target.id)
            elif isinstance(child, ast.AnnAssign) and isinstance(
                child.target, ast.Name
            ):
                assigned.add(child.target.id)
        return assigned

    def _assigned_with_bases(
        self, name: str, classes: dict[str, tuple[Path, ast.ClassDef]], seen: set[str]
    ) -> set[str]:
        if name in seen or name not in classes:
            return set()
        seen.add(name)
        _, node = classes[name]
        assigned = self._assigned_in(node)
        for base in node.bases:
            base_name = base.id if isinstance(base, ast.Name) else None
            if base_name:
                assigned |= self._assigned_with_bases(base_name, classes, seen)
        return assigned

    def test_every_attribute_read_is_assigned(self) -> None:
        classes = self._class_nodes()
        failures: list[str] = []

        for class_name, (path, node) in classes.items():
            assigned = self._assigned_with_bases(class_name, classes, set())
            read: dict[str, int] = {}
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Attribute)
                    and isinstance(child.value, ast.Name)
                    and child.value.id == "self"
                    and isinstance(child.ctx, ast.Load)
                ):
                    read.setdefault(child.attr, child.lineno)

            for attribute, line in sorted(read.items()):
                if attribute in assigned or attribute in INHERITED:
                    continue
                if attribute.startswith(("_attr_", "async_", "_abort_", "add_")):
                    continue
                failures.append(
                    f"{path.name}:{line} {class_name}.{attribute} is read but never assigned"
                )

        self.assertEqual(failures, [], "\n" + "\n".join(failures))


class TestNoUnreachableCode(unittest.TestCase):
    """A return in the middle of a body means an edit landed in the wrong place."""

    def test_nothing_follows_a_return(self) -> None:
        failures: list[str] = []
        for path in _python_files():
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for statement in node.body[:-1]:
                    if isinstance(statement, (ast.Return, ast.Raise)):
                        failures.append(
                            f"{path.name}:{statement.lineno} {node.name} has code after "
                            "a return"
                        )
        self.assertEqual(failures, [], "\n".join(failures))


class TestConstructorsAreComplete(unittest.TestCase):
    """Every self._x read must be assigned in an __init__ in its class chain."""

    def test_every_private_attribute_is_initialised(self) -> None:
        """A ``self._x`` that is read must be assigned somewhere in its family.

        The fault this guards against shipped once and crashed setup: an
        attribute read that nothing ever assigned, which neither ruff nor mypy
        catches because the files cannot be imported without Home Assistant.

        Resolution follows base classes, across files. The entity classes are
        two and three deep now — a rate-scoped sensor reads what
        ``TariffEntity.__init__`` set two levels up and in another module —
        and a guard that only looked at one class body would force every
        subclass to re-declare what its base already sets, which is how a
        guard stops being obeyed. What it still catches is the real fault: a
        name assigned in no ``__init__`` anywhere in the chain.
        """
        assigned_by: dict[str, set[str]] = {}
        methods_by: dict[str, set[str]] = {}
        bases_of: dict[str, list[str]] = {}
        classes: list[tuple[Path, ast.ClassDef]] = []

        for path in _python_files():
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.ClassDef):
                    continue
                classes.append((path, node))
                inits = [
                    m
                    for m in node.body
                    if isinstance(m, ast.FunctionDef) and m.name == "__init__"
                ]
                assigned_by[node.name] = {
                    a.attr
                    for init in inits
                    for a in ast.walk(init)
                    if isinstance(a, ast.Attribute) and isinstance(a.ctx, ast.Store)
                }
                methods_by[node.name] = {
                    m.name
                    for m in node.body
                    if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                }
                bases_of[node.name] = [
                    base.id for base in node.bases if isinstance(base, ast.Name)
                ]

        def gather(
            source: dict[str, set[str]], name: str, seen: frozenset[str]
        ) -> set[str]:
            if name in seen or name not in source:
                return set()
            found = set(source[name])
            for base in bases_of.get(name, []):
                found |= gather(source, base, seen | {name})
            return found

        failures: list[str] = []
        for path, node in classes:
            assigned = gather(assigned_by, node.name, frozenset())
            methods = gather(methods_by, node.name, frozenset())
            if not assigned:
                # Nothing in the chain has an __init__ of its own, so there is
                # nothing to check it against.
                continue
            for a in ast.walk(node):
                if (
                    isinstance(a, ast.Attribute)
                    and isinstance(a.ctx, ast.Load)
                    and isinstance(a.value, ast.Name)
                    and a.value.id == "self"
                    and a.attr.startswith("_")
                    and not a.attr.startswith("_attr_")
                    and not a.attr.startswith("_abort")
                    and a.attr not in assigned
                    and a.attr not in methods
                ):
                    failures.append(
                        f"{path.name}:{a.lineno} {node.name}.{a.attr} is never "
                        "set in __init__"
                    )
        self.assertEqual(failures, [], "\n".join(failures))


class TestTranslationsMatch(unittest.TestCase):
    """Every translation key referenced in code must exist in strings.json."""

    def setUp(self) -> None:
        self.strings = json.loads((PACKAGE / "strings.json").read_text())

    def test_en_matches_strings(self) -> None:
        english = json.loads((PACKAGE / "translations" / "en.json").read_text())
        self.assertEqual(english, self.strings, "translations/en.json is out of date")

    def test_flow_steps_have_strings(self) -> None:
        source = (PACKAGE / "config_flow.py").read_text()
        declared = set(re.findall(r'step_id="([a-z_]+)"', source))
        described = set(self.strings["options"]["step"]) | set(
            self.strings["config"]["step"]
        )
        missing = declared - described
        self.assertEqual(
            missing, set(), f"steps with no strings entry: {sorted(missing)}"
        )

    def test_every_placeholder_is_supplied(self) -> None:
        """A step showing {x} must pass x, or the user gets an empty error dialog."""
        source = (PACKAGE / "config_flow.py").read_text()
        failures: list[str] = []
        for section in ("config", "options"):
            for name, step in self.strings[section]["step"].items():
                text = f"{step.get('title', '')} {step.get('description', '')}"
                for placeholder in set(re.findall(r"\{([a-z_]+)\}", text)):
                    if f'"{placeholder}"' not in source:
                        failures.append(f"{section}.{name} needs {{{placeholder}}}")
        self.assertEqual(failures, [], "\n".join(failures))

    def test_no_placeholders_in_titles(self) -> None:
        """Titles are formatted separately and are the usual source of this fault."""
        offenders = [
            f"{section}.{name}"
            for section in ("config", "options")
            for name, step in self.strings[section]["step"].items()
            if re.search(r"\{[a-z_]+\}", step.get("title", ""))
        ]
        self.assertEqual(offenders, [])

    def test_no_placeholder_wrapped_in_single_quotes(self) -> None:
        """hassfest rejects a placeholder quoted with '{x}' anywhere in strings.json.

        Caught by hassfest in CI, not by anything in this suite — nothing
        here parsed the string text closely enough to notice the quoting.
        Walks every string value in the whole file, not just steps, since
        hassfest's own check isn't scoped to steps either.
        """

        def walk(node: object, path: str) -> list[str]:
            found: list[str] = []
            if isinstance(node, dict):
                for key, value in node.items():
                    found.extend(walk(value, f"{path}.{key}"))
            elif isinstance(node, str) and re.search(r"'\{[a-z_]+\}'", node):
                found.append(path)
            return found

        offenders = walk(self.strings, "strings")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_no_empty_error_dict(self) -> None:
        """hassfest rejects an 'error' key present but empty — {} is not the
        same as "this step has no errors" to its schema; omit the key
        entirely instead. Also caught by hassfest in CI, not by this suite.
        """
        offenders = [
            f"{section}.step.{name}"
            for section in ("config", "options")
            for name, step in self.strings[section]["step"].items()
            if "error" in step and step["error"] == {}
        ]
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_flow_errors_have_strings(self) -> None:
        source = (PACKAGE / "config_flow.py").read_text()
        used = set(re.findall(r'errors\[[^\]]+\] = "([a-z_]+)"', source))
        declared = set(self.strings["options"]["error"]) | set(
            self.strings["config"]["error"]
        )
        missing = used - declared
        self.assertEqual(
            missing, set(), f"errors with no strings entry: {sorted(missing)}"
        )

    def test_exception_keys_have_strings(self) -> None:
        keys: set[str] = set()
        for path in _python_files():
            keys |= set(re.findall(r'translation_key="([a-z_]+)"', path.read_text()))
        described = (
            set(self.strings["exceptions"])
            | set(self.strings["issues"])
            | set(self.strings["entity"]["sensor"])
            | set(self.strings["selector"])
        )
        # Constraint sensors are named by the user and carry no translation.
        missing = {key for key in keys - described if not key.startswith("constraint_")}
        self.assertEqual(
            missing, set(), f"translation keys with no strings entry: {sorted(missing)}"
        )

    def test_entity_keys_have_icons(self) -> None:
        icons = json.loads((PACKAGE / "icons.json").read_text())
        named = set(self.strings["entity"]["sensor"])
        iconed = set(icons["entity"]["sensor"])
        self.assertEqual(named - iconed, set(), "sensors without an icon")


class TestPureModulesStayPure(unittest.TestCase):
    """The pure modules must not grow a Home Assistant import."""

    PURE = (
        "const.py",
        "plan.py",
        "validate.py",
        "intervals.py",
        "allowance.py",
        "accounting.py",
        "strip.py",
        "serialise.py",
    )

    def test_no_home_assistant_imports(self) -> None:
        offenders: list[str] = []
        for name in self.PURE:
            source = (PACKAGE / name).read_text()
            if re.search(r"^\s*(from|import)\s+homeassistant", source, re.MULTILINE):
                offenders.append(name)
        self.assertEqual(
            offenders, [], f"pure modules importing Home Assistant: {offenders}"
        )

    def test_all_pure_modules_are_listed(self) -> None:
        ha_free = []
        for path in _python_files():
            if path.name in ("__init__.py",):
                continue
            source = path.read_text()
            if not re.search(
                r"^\s*(from|import)\s+homeassistant", source, re.MULTILINE
            ):
                ha_free.append(path.name)
        self.assertEqual(
            sorted(ha_free),
            sorted(self.PURE),
            "a module became pure or impure without this list being updated",
        )


class TestManifest(unittest.TestCase):
    def test_manifest_fields(self) -> None:
        manifest = json.loads((PACKAGE / "manifest.json").read_text())
        for key in (
            "domain",
            "name",
            "codeowners",
            "config_flow",
            "documentation",
            "iot_class",
            "issue_tracker",
            "version",
        ):
            self.assertIn(key, manifest)
        self.assertEqual(manifest["domain"], PACKAGE.name)
        self.assertTrue(
            manifest["codeowners"], "integration-owner requires a code owner"
        )

    def test_no_site_data_in_source(self) -> None:
        """No address, no entity id from one house, no real prices."""
        banned = ("oxley", "868", "ovo_energy", "meremortals70/hvac")
        offenders: list[str] = []
        for path in sorted(PACKAGE.rglob("*")):
            if path.is_dir() or path.suffix not in (".py", ".json", ".yaml"):
                continue
            lowered = path.read_text().lower()
            for token in banned:
                if token in lowered:
                    offenders.append(f"{path.name}: {token}")
        self.assertEqual(offenders, [], f"site data in source: {offenders}")


if __name__ == "__main__":
    unittest.main()
