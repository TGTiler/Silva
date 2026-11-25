"""
Testes de integridade de contratos, schemas, prompts e dataset.
"""

import json
import os
import sys
import unittest
from pathlib import Path

# Ajusta caminhos para permitir importações locais
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
sys.path.insert(0, str(BASE_DIR / "android_agent"))
sys.path.insert(0, str(BASE_DIR / "dataset"))
sys.path.insert(0, str(BASE_DIR / "pc_training"))

from android_agent.config import SILVA_SYSTEM_PROMPT
from android_agent.tools import AVAILABLE_TOOLS
from dataset.validate_dataset import validate_dataset


class TestContracts(unittest.TestCase):
    """Validação estrita de ferramentas, contratos e schemas."""

    def setUp(self):
        self.schema_path = BASE_DIR / "dataset" / "schema.json"
        self.dataset_path = BASE_DIR / "dataset" / "silva_colab_dataset.jsonl"
        with open(self.schema_path, "r", encoding="utf-8") as f:
            self.schema_data = json.load(f)
        self.schema_tools = self.schema_data.get("tools", {})

    def test_tool_count_and_keys(self):
        """Verifica se existem exatamente 59 ferramentas e se coincidem com o schema."""
        self.assertEqual(len(AVAILABLE_TOOLS), 59, "AVAILABLE_TOOLS deve conter exatamente 59 ferramentas")
        self.assertEqual(len(self.schema_tools), 59, "schema.json deve conter exatamente 59 ferramentas")
        self.assertEqual(
            set(AVAILABLE_TOOLS.keys()),
            set(self.schema_tools.keys()),
            "As ferramentas de AVAILABLE_TOOLS e schema.json devem ser idênticas"
        )

    def test_system_prompt_synchronization(self):
        """Verifica se todas as 59 ferramentas aparecem no prompt de config.py e colab_train_silva.py."""
        # 1. Checa config.py
        for tool_name in AVAILABLE_TOOLS.keys():
            self.assertIn(
                tool_name,
                SILVA_SYSTEM_PROMPT,
                f"Ferramenta '{tool_name}' não encontrada no SILVA_SYSTEM_PROMPT de config.py"
            )

        # 2. Checa colab_train_silva.py
        colab_path = BASE_DIR / "pc_training" / "colab_train_silva.py"
        with open(colab_path, "r", encoding="utf-8") as f:
            colab_code = f.read()

        for tool_name in AVAILABLE_TOOLS.keys():
            self.assertIn(
                tool_name,
                colab_code,
                f"Ferramenta '{tool_name}' não encontrada no prompt de pc_training/colab_train_silva.py"
            )

    def test_colab_dataset_conformance(self):
        """Valida que dataset/silva_colab_dataset.jsonl passa 100% no validador com 0 erros."""
        self.assertTrue(self.dataset_path.is_file(), "silva_colab_dataset.jsonl deve existir")
        is_valid = validate_dataset(self.dataset_path, self.schema_path)
        self.assertTrue(is_valid, "Dataset deve passar 100% no validate_dataset com 0 erros")


if __name__ == "__main__":
    unittest.main()
