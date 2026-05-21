import json
import tempfile
import unittest
from pathlib import Path

from promptcraft.config import PromptCraftConfig, load_config


class ConfigTests(unittest.TestCase):
    def test_loads_state_store_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "promptcraft.config.json"
            path.write_text(
                json.dumps({"state_store": ".promptcraft/state.json"}),
                encoding="utf-8",
            )

            config = load_config(path)

        self.assertEqual(config.state_store, ".promptcraft/state.json")

    def test_ignores_unknown_fields(self):
        config = PromptCraftConfig.from_mapping(
            {
                "state_store": ".promptcraft/state.json",
                "unknown": True,
            }
        )

        self.assertEqual(config.state_store, ".promptcraft/state.json")
        self.assertFalse(hasattr(config, "unknown"))


if __name__ == "__main__":
    unittest.main()
