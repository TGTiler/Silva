"""
Cliente HTTP ultraleve para comunicação com o llama-server local.
Utiliza apenas a biblioteca padrão (urllib) para rodar com zero dependências externas.
"""

import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

try:
    from config import LLAMA_SERVER_URL, LLM_TIMEOUT_SECONDS, SILVA_SYSTEM_PROMPT
    from intent_fallback import match_intent_fallback
    from conversation_context import resolve_anaphora, format_recent_context
    from tools import AVAILABLE_TOOLS
    from tools.memory_schedule import active_recall_search
except ImportError:
    from android_agent.config import LLAMA_SERVER_URL, LLM_TIMEOUT_SECONDS, SILVA_SYSTEM_PROMPT
    from android_agent.intent_fallback import match_intent_fallback
    from android_agent.conversation_context import resolve_anaphora, format_recent_context
    from android_agent.tools import AVAILABLE_TOOLS
    from android_agent.tools.memory_schedule import active_recall_search


def _is_interrogative_question(text: str) -> bool:
    """Identifica perguntas interrogativas em PT-BR para Recordação Ativa Pré-LLM."""
    norm = "".join(
        c for c in unicodedata.normalize("NFKD", (text or "").lower())
        if not unicodedata.combining(c)
    )
    return bool(re.search(r"\b(?:qual|quais|onde|quando|quanto|quantos|quantas|quem|como\s+e)\b", norm))


class SilvaLLMClient:
    def __init__(self, base_url: str = LLAMA_SERVER_URL, timeout: int = LLM_TIMEOUT_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def check_health(self) -> Dict[str, Any]:
        """Verifica se o llama-server está online e respondendo."""
        health_url = f"{self.base_url}/health"
        try:
            req = urllib.request.Request(health_url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return {"online": True, "status": data.get("status", "ok"), "url": self.base_url}
        except Exception:
            # Tenta testar endpoint raiz caso /health retorne 404 em versões antigas
            try:
                req_root = urllib.request.Request(self.base_url, method="GET")
                with urllib.request.urlopen(req_root, timeout=3) as resp:
                    return {"online": True, "status": "ok", "url": self.base_url}
            except Exception as e:
                return {"online": False, "status": "offline", "error": str(e), "url": self.base_url}

    def generate_call(self, user_prompt: str, session_id: str = "default") -> Tuple[Optional[str], float, Optional[str]]:
        """
        Envia o prompt do usuário para o llama-server e retorna:
        (raw_call_output, latency_ms, error_message)
        """
        prompt = user_prompt.strip()
        if not prompt:
            return "<call>none()</call>", 0.0, None

        # 0. Resolução anafórica determinística com contexto de curto prazo
        resolved_prompt = resolve_anaphora(prompt, session_id)
        if resolved_prompt.startswith("<call>") and resolved_prompt.endswith("</call>"):
            return resolved_prompt, 1.5, None

        # 1. Roteamento de ultra-baixa latência (<2ms) para intenções imediatas
        fast_call = match_intent_fallback(resolved_prompt)
        if fast_call:
            return fast_call, 1.5, None

        # 1.5. Recordação Ativa Pré-LLM para perguntas interrogativas abertas
        memory_hint_block = ""
        if _is_interrogative_question(resolved_prompt):
            recall_info = active_recall_search(resolved_prompt)
            recall_level = recall_info.get("level")
            top_mem = recall_info.get("top")
            if recall_level == "high" and top_mem:
                return f"<call>recall_note(query={repr(top_mem['key'])})</call>", 1.5, None
            if recall_level == "medium" and top_mem:
                memory_hint_block = f"[Memória Relevante: {top_mem['key']}: {top_mem['value']}]"

        # 2. Inferência via LLM local (llama-server) para consultas complexas
        ctx_block = format_recent_context(session_id, max_turns=2)
        parts = []
        if memory_hint_block:
            parts.append(memory_hint_block)
        if ctx_block:
            parts.append(f"Contexto recente:\n{ctx_block}")
        if parts:
            parts.append(f"Pedido atual: {resolved_prompt}")
            user_block = "\n\n".join(parts)
        else:
            user_block = resolved_prompt
        formatted_prompt = (
            f"<|im_start|>system\n{SILVA_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{user_block}<|im_end|>\n"
            f"<|im_start|>assistant\n<call>"
        )

        payload = {
            "prompt": formatted_prompt,
            "temperature": 0.0,
            "n_predict": 48,
            "stop": ["\n", "<|im_end|>", "<|endoftext|>"],
            "stream": False,
            "cache_prompt": True,
        }

        completion_url = f"{self.base_url}/completion"
        start_time = time.perf_counter()

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                completion_url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_body = resp.read().decode("utf-8")
                latency_ms = (time.perf_counter() - start_time) * 1000.0
                resp_json = json.loads(raw_body)
                content = resp_json.get("content", "").strip()

                # Reconstitui o texto se o modelo completou a partir do prefixo '<call>'
                if not content.startswith("<call>"):
                    raw_text = f"<call>{content}"
                else:
                    raw_text = content

                if "</call>" not in raw_text:
                    raw_text = f"{raw_text}</call>"

                # Extrai todas as tags <call>...</call>
                call_contents = re.findall(r"<call>(.*?)</call>", raw_text, re.DOTALL)
                valid_calls = []

                for inner in call_contents:
                    inner_clean = inner.strip()
                    func_name = inner_clean.split("(")[0].strip()
                    if func_name in AVAILABLE_TOOLS and func_name != "none":
                        valid_calls.append(f"<call>{inner_clean}</call>")

                if valid_calls:
                    full_output = "".join(valid_calls)
                else:
                    full_output = "<call>none()</call>"

                return full_output, round(latency_ms, 2), None

        except urllib.error.URLError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            err_str = str(e)
            if "111" in err_str or "Connection refused" in err_str or isinstance(getattr(e, "reason", None), (ConnectionRefusedError, ConnectionError)):
                err_msg = "Não reconheci esse comando no modo rápido (o servidor do modelo local está offline no momento). Tente reformular o pedido ou inicie o llama-server."
            else:
                err_msg = f"LLM indisponível (conexão): {e}"
            return "<call>none()</call>", round(latency_ms, 2), err_msg
        except (ConnectionRefusedError, ConnectionError):
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return "<call>none()</call>", round(latency_ms, 2), "Não reconheci esse comando no modo rápido (o servidor do modelo local está offline no momento). Tente reformular o pedido ou inicie o llama-server."
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            err_str = str(e)
            if "111" in err_str or "Connection refused" in err_str:
                err_msg = "Não reconheci esse comando no modo rápido (o servidor do modelo local está offline no momento). Tente reformular o pedido ou inicie o llama-server."
            else:
                err_msg = f"LLM indisponível: {e}"
            return "<call>none()</call>", round(latency_ms, 2), err_msg
