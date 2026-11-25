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
        """Verifica se existem exatamente 64 ferramentas e se coincidem com o schema."""
        self.assertEqual(len(AVAILABLE_TOOLS), 64, "AVAILABLE_TOOLS deve conter exatamente 64 ferramentas")
        self.assertEqual(len(self.schema_tools), 64, "schema.json deve conter exatamente 64 ferramentas")
        self.assertEqual(
            set(AVAILABLE_TOOLS.keys()),
            set(self.schema_tools.keys()),
            "As ferramentas de AVAILABLE_TOOLS e schema.json devem ser idênticas"
        )

    def test_system_prompt_synchronization(self):
        """Verifica se todas as 63 ferramentas aparecem no prompt de config.py e colab_train_silva.py."""
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

    def test_python_signatures_match_schema_and_seed_coverage(self):
        """
        Auditoria profunda via inspect.signature:
        - Nomes, tipos e obrigatoriedade dos parâmetros batem 100% entre AVAILABLE_TOOLS e schema.json.
        - Cada ferramenta em AVAILABLE_TOOLS possui pelo menos 2 exemplos em seed_examples.jsonl.
        """
        import inspect
        import re
        from collections import Counter

        type_map = {
            "string": (str,),
            "integer": (int,),
            "number": (int, float),
            "float": (int, float),
            "boolean": (bool,),
        }

        for tool_name, fn in AVAILABLE_TOOLS.items():
            with self.subTest(tool=tool_name):
                sig = inspect.signature(fn)
                schema_params = self.schema_tools[tool_name].get("parameters", {})
                self.assertEqual(
                    set(sig.parameters.keys()),
                    set(schema_params.keys()),
                    f"Parâmetros de '{tool_name}' diferem entre Python e schema.json",
                )
                for p_name, p_obj in sig.parameters.items():
                    sc_param = schema_params[p_name]
                    py_required = (p_obj.default is inspect.Parameter.empty)
                    sc_required = bool(sc_param.get("required", False))
                    self.assertEqual(
                        py_required,
                        sc_required,
                        f"Obrigatoriedade de '{tool_name}.{p_name}' difere (py={py_required}, schema={sc_required})",
                    )
                    ann = p_obj.annotation
                    expected_types = type_map.get(sc_param.get("type", ""))
                    if ann is not inspect.Parameter.empty and expected_types and isinstance(ann, type):
                        self.assertIn(
                            ann,
                            expected_types,
                            f"Tipo anotado de '{tool_name}.{p_name}' ({ann}) incompatível com schema ({sc_param.get('type')})",
                        )

        seed_path = BASE_DIR / "dataset" / "seed_examples.jsonl"
        seed_counts = Counter()
        with open(seed_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                comp = json.loads(line).get("completion", "")
                for fn_name in re.findall(r"<call>([a-zA-Z0-9_]+)\(", comp):
                    seed_counts[fn_name] += 1

        for tool_name in AVAILABLE_TOOLS.keys():
            self.assertGreaterEqual(
                seed_counts[tool_name],
                2,
                f"Ferramenta '{tool_name}' possui apenas {seed_counts[tool_name]} exemplo(s) em seed_examples.jsonl (mínimo: 2)",
            )


if __name__ == "__main__":
    unittest.main()
