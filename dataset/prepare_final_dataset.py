#!/usr/bin/env python3
"""
Preparador, Enriquecedor e Validador Leve de Dataset para o Silva Agent.
Executa em Python puro sem dependências pesadas (compatível com Celeron / 4GB RAM).
Gera train_clean.jsonl (95%), eval_clean.jsonl (5%) e silva_colab_dataset.jsonl (100%).
"""

import ast
import json
import os
import random
import re
import sys
from collections import Counter
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.json"
TRAIN_PATH = BASE_DIR / "train.jsonl"
SEED_PATH = BASE_DIR / "seed_examples.jsonl"

TRAIN_CLEAN_PATH = BASE_DIR / "train_clean.jsonl"
EVAL_CLEAN_PATH = BASE_DIR / "eval_clean.jsonl"
COLAB_DATASET_PATH = BASE_DIR / "silva_colab_dataset.jsonl"

CALL_TAG_REGEX = re.compile(r"<call>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*</call>", re.DOTALL)
HAS_ALPHA_REGEX = re.compile(r"[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]")


def load_schema(schema_file: Path) -> dict:
    if not schema_file.is_file():
        raise FileNotFoundError(f"Schema não encontrado em: {schema_file}")
    with open(schema_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("tools", {})


def parse_call_args(args_str: str) -> dict:
    """Extrai argumentos nomeados via AST com segurança."""
    args_str = args_str.strip()
    if not args_str:
        return {}

    expr = ast.parse(f"call({args_str})", mode="eval")
    call_node = expr.body
    if call_node.args:
        raise ValueError("Argumentos posicionais não permitidos. Use chave=valor.")

    kwargs = {}
    for kw in call_node.keywords:
        kwargs[kw.arg] = ast.literal_eval(kw.value)
    return kwargs


def validate_args(tool_name: str, args: dict, tool_def: dict) -> list[str]:
    errors = []
    params_def = tool_def.get("parameters", {})

    for a in args:
        if a not in params_def:
            errors.append(f"Parâmetro inesperado '{a}' para '{tool_name}'.")

    for p, meta in params_def.items():
        if meta.get("required", False) and p not in args:
            errors.append(f"Parâmetro obrigatório '{p}' ausente para '{tool_name}'.")

        if p in args:
            val = args[p]
            expected = meta.get("type")
            if expected == "integer" and not isinstance(val, int):
                errors.append(f"'{p}' deve ser int, recebido {type(val).__name__}.")
            elif expected == "boolean" and not isinstance(val, bool):
                errors.append(f"'{p}' deve ser bool, recebido {type(val).__name__}.")
            elif expected == "string" and not isinstance(val, str):
                errors.append(f"'{p}' deve ser str, recebido {type(val).__name__}.")

    return errors


def validate_line(item: dict, tools_schema: dict) -> tuple[bool, str, list[str]]:
    """Valida um registro e retorna (is_valid, reason, tool_names)."""
    prompt = item.get("prompt")
    completion = item.get("completion")

    if not prompt or not isinstance(prompt, str) or not prompt.strip():
        return False, "Prompt ausente ou vazio", []

    if not completion or not isinstance(completion, str) or not completion.strip():
        return False, "Completion ausente ou vazia", []

    matches = CALL_TAG_REGEX.findall(completion.strip())
    if not matches:
        return False, f"Nenhuma tag <call> válida encontrada em: '{completion}'", []

    tools_used = []
    for func_name, args_raw in matches:
        if func_name not in tools_schema:
            return False, f"Ferramenta '{func_name}' não existe no schema", []

        try:
            parsed_kwargs = parse_call_args(args_raw)
        except Exception as e:
            return False, f"Erro ao analisar argumentos de '{func_name}': {e}", []

        errs = validate_args(func_name, parsed_kwargs, tools_schema[func_name])
        if errs:
            return False, f"Erro nos argumentos de '{func_name}': {'; '.join(errs)}", []

        tools_used.append(func_name)

    return True, "OK", tools_used


def generate_named_contact_examples(count_needed: int = 300) -> list[dict]:
    """Gera exemplos realistas em PT-BR para make_call e send_sms com nomes e parentescos."""
    print(f"[*] Gerando {count_needed} exemplos de chamadas e SMS com nomes de contatos/parentescos...")

    contatos = [
        ("Mãe", "a Mãe", "pra Mãe", "para a Mãe"),
        ("Pai", "o Pai", "pro Pai", "para o Pai"),
        ("Amor", "o Amor", "pro Amor", "para o Amor"),
        ("Aline", "a Aline", "pra Aline", "para a Aline"),
        ("Gustavo", "o Gustavo", "pro Gustavo", "para o Gustavo"),
        ("Mariana", "a Mariana", "pra Mariana", "para a Mariana"),
        ("Lucas", "o Lucas", "pro Lucas", "para o Lucas"),
        ("Juliana", "a Juliana", "pra Juliana", "para a Juliana"),
        ("Pedro", "o Pedro", "pro Pedro", "para o Pedro"),
        ("Carlos", "o Carlos", "pro Carlos", "para o Carlos"),
        ("Beatriz", "a Beatriz", "pra Beatriz", "para a Beatriz"),
        ("Felipe", "o Felipe", "pro Felipe", "para o Felipe"),
        ("Camila", "a Camila", "pra Camila", "para a Camila"),
        ("Rodrigo", "o Rodrigo", "pro Rodrigo", "para o Rodrigo"),
        ("Fernanda", "a Fernanda", "pra Fernanda", "para a Fernanda"),
        ("Thiago", "o Thiago", "pro Thiago", "para o Thiago"),
        ("Larissa", "a Larissa", "pra Larissa", "para a Larissa"),
        ("Gabriel", "o Gabriel", "pro Gabriel", "para o Gabriel"),
        ("Bruna", "a Bruna", "pra Bruna", "para a Bruna"),
        ("Rafael", "o Rafael", "pro Rafael", "para o Rafael"),
        ("Letícia", "a Letícia", "pra Letícia", "para a Letícia"),
        ("Marcelo", "o Marcelo", "pro Marcelo", "para o Marcelo"),
        ("Patrícia", "a Patrícia", "pra Patrícia", "para a Patrícia"),
        ("André", "o André", "pro André", "para o André"),
        ("Renata", "a Renata", "pra Renata", "para a Renata"),
        ("Tia Maria", "a Tia Maria", "pra Tia Maria", "para a Tia Maria"),
        ("Tio João", "o Tio João", "pro Tio João", "para o Tio João"),
        ("Vó Maria", "a Vó Maria", "pra Vó Maria", "para a Vó Maria"),
        ("Vô Pedro", "o Vô Pedro", "pro Vô Pedro", "para o Vô Pedro"),
        ("Irmão", "o Irmão", "pro Irmão", "para o Irmão"),
        ("Irmã", "a Irmã", "pra Irmã", "para a Irmã"),
        ("Chefe", "o Chefe", "pro Chefe", "para o Chefe"),
        ("Trabalho", "o Trabalho", "pro Trabalho", "para o Trabalho"),
        ("Doutor Carlos", "o Doutor Carlos", "pro Doutor Carlos", "para o Doutor Carlos"),
        ("Dentista", "o Dentista", "pro Dentista", "para o Dentista"),
        ("Mecânico", "o Mecânico", "pro Mecânico", "para o Mecânico"),
        ("Pizzaria", "a Pizzaria", "pra Pizzaria", "para a Pizzaria"),
        ("Portaria", "a Portaria", "pra Portaria", "para a Portaria")
    ]

    verbos_call = [
        "Silva, liga {prep}",
        "Liga {prep}",
        "Faz uma ligação {prep}",
        "Disca {prep}",
        "Telefona {prep} por favor",
        "Pode ligar {prep} agora?",
        "Chama {prep} no telefone",
        "Efetua uma chamada {prep}",
        "Silva, liga {prep} pra mim",
        "Coloca uma chamada {prep}"
    ]

    templates_sms = [
        ("Silva, manda um SMS {prep} dizendo que {msg}", "{msg}"),
        ("Manda SMS {prep}: {msg}", "{msg}"),
        ("Envia mensagem de texto {prep} avisando que {msg}", "avisando que {msg}"),
        ("Avisa {prep} por SMS que {msg}", "que {msg}"),
        ("Escreve um SMS {prep} com o texto: {msg}", "{msg}"),
        ("Manda um torpedo {prep} dizendo {msg}", "{msg}"),
        ("Passa um SMS {prep} avisando que {msg}", "{msg}"),
        ("Silva, envia SMS {prep} falando que {msg}", "{msg}"),
    ]

    mensagens = [
        "já estou a caminho",
        "chego em 10 minutos",
        "a reunião começou",
        "não esquece de comprar o pão",
        "estou preso no trânsito",
        "pode me ligar quando puder?",
        "já cheguei em casa",
        "ok, combinado!",
        "tudo certo para amanhã",
        "estou na portaria",
        "bom dia!",
        "boa noite!",
        "vou me atrasar um pouco",
        "me manda a sua localização",
        "o almoço está pronto",
        "obrigado pela ajuda",
        "te ligo mais tarde",
        "estou saindo agora",
        "já peguei as chaves",
        "onde você está?",
        "vou demorar mais 15 minutos",
        "pode deixar comigo",
        "já te fiz o Pix",
        "acabei de sair do trabalho",
        "avisa quando chegar"
    ]

    generated = []
    half = count_needed // 2

    # Metade make_call com nomes
    call_samples = []
    while len(call_samples) < half:
        c_nome, c_art, c_pro, c_para = random.choice(contatos)
        v = random.choice(verbos_call)
        prep = c_pro if "pro" in v or "pra" in v else c_para
        prompt = v.format(prep=prep)
        comp = f'<call>make_call(number="{c_nome}")</call>'
        item = {"prompt": prompt, "completion": comp}
        if item not in call_samples:
            call_samples.append(item)

    # Metade send_sms com nomes
    sms_samples = []
    while len(sms_samples) < (count_needed - half):
        c_nome, c_art, c_pro, c_para = random.choice(contatos)
        tpl, msg_format = random.choice(templates_sms)
        msg_text = random.choice(mensagens)
        prep = c_pro if "{prep}" in tpl and ("pro" in tpl or "pra" in tpl) else c_para
        prompt = tpl.format(prep=prep, msg=msg_text)
        final_msg = msg_format.format(msg=msg_text)
        comp = f'<call>send_sms(number="{c_nome}", message="{final_msg}")</call>'
        item = {"prompt": prompt, "completion": comp}
        if item not in sms_samples:
            sms_samples.append(item)

    generated = call_samples + sms_samples
    random.shuffle(generated)
    return generated


def main():
    print("=" * 65)
    print(" SILVA AGENT — PREPARAÇÃO E LIMPEZA LEVE DO DATASET FINAL ")
    print("=" * 65)

    tools_schema = load_schema(SCHEMA_PATH)
    print(f"[*] Schema carregado com {len(tools_schema)} ferramentas registradas.")

    raw_lines = []
    input_files = [TRAIN_PATH, SEED_PATH]

    for p in input_files:
        if not p.is_file():
            print(f"[!] Arquivo não encontrado: {p}")
            continue
        print(f"[*] Lendo arquivo: {p}...")
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            for line_no, raw_line in enumerate(f, start=1):
                s = raw_line.strip()
                if not s:
                    continue
                try:
                    data = json.loads(s)
                    raw_lines.append((p.name, line_no, data))
                except Exception as e:
                    print(f"[DESCARTADO] {p.name}:{line_no} - JSON malformado: {e}")

    print(f"[*] Total de linhas brutas lidas: {len(raw_lines)}")

    valid_samples = []
    discarded_count = 0
    named_contacts_count = 0

    for fname, lno, item in raw_lines:
        is_ok, reason, tools_used = validate_line(item, tools_schema)
        if not is_ok:
            discarded_count += 1
            if discarded_count <= 10:
                print(f"[DESCARTADO] {fname}:{lno} - {reason}")
            continue

        # Verifica uso de nomes em make_call ou send_sms
        completion = item["completion"]
        if "make_call" in completion or "send_sms" in completion:
            for func_name, args_raw in CALL_TAG_REGEX.findall(completion):
                if func_name in ("make_call", "send_sms"):
                    try:
                        args = parse_call_args(args_raw)
                        target_num = str(args.get("number", ""))
                        if HAS_ALPHA_REGEX.search(target_num):
                            named_contacts_count += 1
                    except Exception:
                        pass

        valid_samples.append(item)

    print(f"[*] Linhas validadas com sucesso: {len(valid_samples)} (Descartadas: {discarded_count})")
    print(f"[*] Contatos com nomes/parentescos existentes em make_call/send_sms: {named_contacts_count}")

    # Regra 3: Se < 100 contatos com nomes, gerar 300 exemplos sintéticos
    if named_contacts_count < 100:
        extra_named_examples = generate_named_contact_examples(300)
        valid_samples.extend(extra_named_examples)
        print(f"[+] 300 exemplos com nomes de contatos adicionados com sucesso!")

    # Regra 4: Deduplicação exata de prompts
    print("[*] Removendo duplicatas exatas de prompt...")
    unique_samples = []
    seen_prompts = set()

    for item in valid_samples:
        p_clean = " ".join(item["prompt"].strip().lower().split())
        if p_clean not in seen_prompts:
            seen_prompts.add(p_clean)
            unique_samples.append(item)

    print(f"[*] Total após deduplicação: {len(unique_samples)} amostras únicas.")

    # Embaralhamento com seed=42
    random.seed(42)
    random.shuffle(unique_samples)

    # Divisão 95% treino, 5% avaliação
    total_total = len(unique_samples)
    eval_count = max(1, int(total_total * 0.05))
    train_count = total_total - eval_count

    eval_data = unique_samples[:eval_count]
    train_data = unique_samples[eval_count:]

    # Salva arquivos limpos
    print(f"[*] Salvando {COLAB_DATASET_PATH.name} (100% consolidado: {total_total} linhas)...")
    with open(COLAB_DATASET_PATH, "w", encoding="utf-8") as f:
        for item in unique_samples:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[*] Salvando {TRAIN_CLEAN_PATH.name} (95% treino: {len(train_data)} linhas)...")
    with open(TRAIN_CLEAN_PATH, "w", encoding="utf-8") as f:
        for item in train_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[*] Salvando {EVAL_CLEAN_PATH.name} (5% avaliação: {len(eval_data)} linhas)...")
    with open(EVAL_CLEAN_PATH, "w", encoding="utf-8") as f:
        for item in eval_data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    # Contagem final por ferramenta
    tool_counter = Counter()
    multi_call_count = 0

    for item in unique_samples:
        matches = CALL_TAG_REGEX.findall(item["completion"])
        if len(matches) > 1:
            multi_call_count += 1
        for fn, _ in matches:
            tool_counter[fn] += 1

    print("\n" + "=" * 65)
    print("RELATÓRIO CONSOLIDADO DO DATASET LIMPO (SILVA COLAB)")
    print("=" * 65)
    print(f"Total de amostras únicas: {total_total}")
    print(f"Divisão: Treino={len(train_data)} | Avaliação={len(eval_data)}")
    print(f"Amostras encadeadas (Multi-Call): {multi_call_count}")
    print("\nDistribuição por Ferramenta:")
    print(f"{'Ferramenta':<25} | {'Qtd Chamadas':<14} | {'%':<8}")
    print("-" * 52)
    sum_calls = sum(tool_counter.values())
    for tool in sorted(tools_schema.keys()):
        qtd = tool_counter.get(tool, 0)
        pct = (qtd / sum_calls * 100) if sum_calls > 0 else 0
        status = "!" if qtd == 0 else " "
        print(f"{status} {tool:<23} | {qtd:<14} | {pct:>5.2f}%")

    print("=" * 65)
    print("[OK] Dataset preparado, validado e consolidado para upload no Google Colab!")


if __name__ == "__main__":
    main()
