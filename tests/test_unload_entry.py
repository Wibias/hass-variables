import ast
from pathlib import Path
import unittest


class UnloadEntryRegistryTests(unittest.TestCase):
    def test_unload_entry_does_not_remove_entity_registry_entries(self) -> None:
        """Reloads use async_unload_entry and must preserve entity registry rows."""
        source = Path("custom_components/variable/__init__.py").read_text()
        module = ast.parse(source)

        unload_entry = next(
            node
            for node in module.body
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "async_unload_entry"
        )

        calls = [
            node
            for node in ast.walk(unload_entry)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "async_remove"
        ]

        self.assertEqual([], calls)


if __name__ == "__main__":
    unittest.main()
