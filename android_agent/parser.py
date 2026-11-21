"""
Extrator e validador seguro de chamadas de função do Silva.
Suporta chamadas únicas e múltiplas sequenciais (<call>...</call><call>...</call>),
analisa argumentos tipados via AST e executa apenas funções autorizadas na whitelist de tools.py.
"""

import ast
import inspect
import re
from typing import Any, Dict, List, Optional, Tuple

from tools import AVAILABLE_TOOLS

# Regex robusto para extrair o conteúdo de cada tag <call>...</call>
CALL_TAG_PATTERN = re.compile(r"<call>(.*?)</call>", re.DOTALL)
INNER_CALL_PATTERN = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*$", re.DOTALL)


def parse_function_calls(model_output: str) -> List[Tuple[str, Dict[str, Any]]]:
    """
    Extrai e valida todas as chamadas <call>...</call> encontradas na saída do modelo.
    Retorna uma lista de tuplas (nome_da_funcao, kwargs).
    Se houver outras ferramentas junto com 'none', 'none' é descartado.
    Se nenhuma tag válida for encontrada ou apenas 'none', retorna [('none', {})].
    """
    raw_text = (model_output or "").strip()
    raw_blocks = CALL_TAG_PATTERN.findall(raw_text)

    if not raw_blocks:
        return [("none", {})]

    valid_calls: List[Tuple[str, Dict[str, Any]]] = []

    for block in raw_blocks:
        match = INNER_CALL_PATTERN.match(block.strip())
        if not match:
            continue

        func_name = match.group(1).strip()
        raw_args = match.group(2).strip()

        # 1. Whitelist check
        if func_name not in AVAILABLE_TOOLS:
            continue

        # 2. Parsing de argumentos seguro via AST
        kwargs = {}
        if raw_args:
            try:
                expr = ast.parse(f"call({raw_args})", mode="eval")
                call_node = expr.body
                if call_node.args:  # rejeita argumentos posicionais sem chave
                    continue
                for kw in call_node.keywords:
                    kwargs[kw.arg] = ast.literal_eval(kw.value)
            except Exception:
                continue

        # 3. Validação de assinatura e tipagem booleana
        target_func = AVAILABLE_TOOLS[func_name]
        sig = inspect.signature(target_func)
        try:
            bound = sig.bind(**kwargs)
            bound.apply_defaults()

            # Valida estritamente parâmetros booleanos
            type_error = False
            for param_name, param_val in bound.arguments.items():
                param_obj = sig.parameters.get(param_name)
                if param_obj and param_obj.annotation is bool:
                    if not isinstance(param_val, bool):
                        type_error = True
                        break
            if type_error:
                continue
        except TypeError:
            continue

        valid_calls.append((func_name, kwargs))

    # Regra de filtro de 'none':
    # Se houver ferramentas reais acompanhadas de 'none', descarta 'none'
    non_none_calls = [c for c in valid_calls if c[0] != "none"]
    if non_none_calls:
        return non_none_calls

    if any(c[0] == "none" for c in valid_calls):
        return [("none", {})]

    return [("none", {})]


def parse_function_call(model_output: str) -> Dict[str, Any]:
    """Mantém compatibilidade com o validador unitário de chamada única."""
    calls = parse_function_calls(model_output)
    func_name, args = calls[0]
    raw_call = f"<call>{func_name}(" + ", ".join(f"{k}={repr(v)}" for k, v in args.items()) + ")</call>"
    return {
        "is_valid": True,
        "func_name": func_name,
        "args": args,
        "raw_call": raw_call,
        "error": None
    }


def execute_call(model_output: str) -> Dict[str, Any]:
    """
    Executa todas as chamadas sequenciais extraídas da resposta do modelo.
    Consolida mensagens, metadados e imagem gerada (se houver).
    """
    calls = parse_function_calls(model_output)
    executed_details = []
    messages = []
    raw_calls = []
    latest_image_url = None
    latest_video_url = None

    for func_name, args in calls:
        target_func = AVAILABLE_TOOLS[func_name]
        args_str = ", ".join(f"{k}={repr(v)}" for k, v in args.items())
        raw_call_str = f"<call>{func_name}({args_str})</call>"
        raw_calls.append(raw_call_str)

        try:
            tool_res = target_func(**args)
            status = tool_res.get("status", "ok")
            msg = tool_res.get("message", "Operação concluída.")
            img_url = tool_res.get("image_url")
            if img_url:
                latest_image_url = img_url

            vid_url = tool_res.get("video_url")
            if vid_url:
                latest_video_url = vid_url

            messages.append(msg)
            executed_details.append({
                "func_name": func_name,
                "args": args,
                "status": status,
                "data": tool_res.get("data")
            })
        except Exception as e:
            err_msg = f"Silva: Erro ao executar '{func_name}': {str(e)}"
            messages.append(err_msg)
            executed_details.append({
                "func_name": func_name,
                "args": args,
                "status": "error",
                "error": str(e)
            })

    consolidated_message = "\n".join(messages)
    consolidated_raw_call = "".join(raw_calls)

    return {
        "status": "ok",
        "message": consolidated_message,
        "raw_call": consolidated_raw_call,
        "func_name": calls[0][0] if len(calls) == 1 else "multi_call",
        "calls": executed_details,
        "data": [d.get("data") for d in executed_details if d.get("data") is not None],
        "image_url": latest_image_url,
        "video_url": latest_video_url
    }
