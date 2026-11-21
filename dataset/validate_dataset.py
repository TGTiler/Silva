#!/usr/bin/env python3
"""
Silva Dataset Validator
Valida a sintaxe do arquivo JSONL, a formatação das tags <call>,
a conformidade dos parâmetros contra o schema.json e o balanceamento de classes.
"""

import sys
import os
import json
import re
import ast
from collections import Counter
from pathlib import Path

CALL_FIND_REGEX = re.compile(r"<call>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*</call>", re.DOTALL)


def load_schema(schema_path: Path) -> dict:
    if not schema_path.is_file():
        raise FileNotFoundError(f"Schema não encontrado em: {schema_path}")
    with open(schema_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tools", {})


def parse_call_args(args_str: str) -> dict:
    """Extrai os argumentos com segurança usando ast."""
    args_str = args_str.strip()
    if not args_str:
        return {}

    # Envolve em chamada de função fictícia para parsing via ast
    expr_str = f"func({args_str})"
    parsed = ast.parse(expr_str, mode="eval")
    call_node = parsed.body
    kwargs = {}

    for kw in call_node.keywords:
        kwargs[kw.arg] = ast.literal_eval(kw.value)

    # Argumentos posicionais não nomeados
    if call_node.args:
        raise ValueError("Todos os argumentos devem ser nomeados no formato chave=valor.")

    return kwargs


def validate_args_against_schema(tool_name: str, args: dict, tool_def: dict) -> list[str]:
    errors = []
    params_def = tool_def.get("parameters", {})

    # Verifica parâmetros não suportados
    for arg_name in args:
        if arg_name not in params_def:
            errors.append(f"Parâmetro inesperado '{arg_name}' para ferramenta '{tool_name}'.")

    # Verifica parâmetros obrigatórios e tipos
    for param_name, meta in params_def.items():
        if meta.get("required", False) and param_name not in args:
            errors.append(f"Parâmetro obrigatório '{param_name}' ausente para ferramenta '{tool_name}'.")
        
        if param_name in args:
            val = args[param_name]
            expected_type = meta.get("type")
            if expected_type == "integer" and not isinstance(val, int):
                errors.append(f"Tipo inválido para '{param_name}': esperado int, recebido {type(val).__name__}.")
            elif expected_type == "boolean" and not isinstance(val, bool):
                errors.append(f"Tipo inválido para '{param_name}': esperado bool, recebido {type(val).__name__}.")
            elif expected_type == "string" and not isinstance(val, str):
                errors.append(f"Tipo inválido para '{param_name}': esperado str, recebido {type(val).__name__}.")

    return errors


def validate_dataset(jsonl_path: Path, schema_path: Path) -> bool:
    print(f"[*] Validando dataset: {jsonl_path}")
    print(f"[*] Usando schema: {schema_path}")
    
    tools_schema = load_schema(schema_path)
    print(f"[*] Ferramentas registradas no schema: {len(tools_schema)}")

    if not jsonl_path.is_file():
        print(f"[ERRO] Arquivo não encontrado: {jsonl_path}")
        return False

    errors_found = 0
    total_samples = 0
    class_counts = Counter()

    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line_no, raw_line in enumerate(f, start=1):
            line = raw_line.strip()
            if not line:
                continue
            total_samples += 1

            # 1. Validação JSON
            try:
                item = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[ERRO Linha {line_no}] JSON malformado: {e}")
                errors_found += 1
                continue

            # 2. Campos prompt e completion
            prompt = item.get("prompt")
            completion = item.get("completion")

            if not prompt or not isinstance(prompt, str):
                print(f"[ERRO Linha {line_no}] Campo 'prompt' ausente ou inválido.")
                errors_found += 1

            if not completion or not isinstance(completion, str):
                print(f"[ERRO Linha {line_no}] Campo 'completion' ausente ou inválido.")
                errors_found += 1
                continue

            # 3. Regex de extração de uma ou mais tags <call>...</call>
            matches = CALL_FIND_REGEX.findall(completion.strip())
            if not matches:
                print(f"[ERRO Linha {line_no}] Formato de chamada inválido: '{completion}'. Deve conter ao menos uma tag <call>func(...)</call>")
                errors_found += 1
                continue

            for func_name, args_raw in matches:
                class_counts[func_name] += 1

                # 4. Verificar se a função existe no schema
                if func_name not in tools_schema:
                    print(f"[ERRO Linha {line_no}] Ferramenta desconhecida '{func_name}'. Não consta no schema.")
                    errors_found += 1
                    continue

                # 5. Parsing e validação de argumentos
                try:
                    args = parse_call_args(args_raw)
                except Exception as e:
                    print(f"[ERRO Linha {line_no}] Falha ao analisar argumentos de '<call>{func_name}({args_raw})</call>': {e}")
                    errors_found += 1
                    continue

                schema_errors = validate_args_against_schema(func_name, args, tools_schema[func_name])
                for err in schema_errors:
                    print(f"[ERRO Linha {line_no}] {err}")
                    errors_found += 1

    print("\n" + "=" * 60)
    print("RELATÓRIO DE VALIDAÇÃO DO DATASET")
    print("=" * 60)
    print(f"Total de amostras avaliadas: {total_samples}")
    print(f"Erros encontrados: {errors_found}")
    print("\nDistribuição de Classes:")
    print(f"{'Ferramenta':<25} | {'Qtd':<6} | {'Proporção (%)':<12}")
    print("-" * 50)
    for tool in sorted(tools_schema.keys()):
        count = class_counts.get(tool, 0)
        pct = (count / total_samples * 100) if total_samples > 0 else 0
        status_flag = "!" if count == 0 else " "
        print(f"{status_flag} {tool:<23} | {count:<6} | {pct:>6.2f}%")

    # Amostras de classes extras (se houver)
    extras = set(class_counts.keys()) - set(tools_schema.keys())
    if extras:
        print("\n[ALERTA] Funções detectadas fora do schema:")
        for ext in extras:
            print(f"  - {ext}: {class_counts[ext]} amostras")

    print("=" * 60)

    if errors_found == 0 and total_samples > 0:
        print("[SUCESSO] Todos os exemplos estão sintaticamente válidos e em conformidade com o schema!")
        return True
    else:
        print("[FALHA] Validação concluída com inconsistências.")
        return False


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    target_jsonl = Path(sys.argv[1]) if len(sys.argv) > 1 else base_dir / "seed_examples.jsonl"
    target_schema = Path(sys.argv[2]) if len(sys.argv) > 2 else base_dir / "schema.json"

    success = validate_dataset(target_jsonl, target_schema)
    sys.exit(0 if success else 1)
