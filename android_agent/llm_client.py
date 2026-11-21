"""
Cliente HTTP ultraleve para comunicação com o llama-server local.
Utiliza apenas a biblioteca padrão (urllib) para rodar com zero dependências externas.
"""

import json
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Tuple

from config import LLAMA_SERVER_URL, LLM_TIMEOUT_SECONDS, SILVA_SYSTEM_PROMPT
from intent_fallback import match_intent_fallback
from tools import AVAILABLE_TOOLS


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

    def generate_call(self, user_prompt: str) -> Tuple[Optional[str], float, Optional[str]]:
        """
        Envia o prompt do usuário para o llama-server e retorna:
        (raw_call_output, latency_ms, error_message)
        """
        prompt = user_prompt.strip()
        if not prompt:
            return "<call>none()</call>", 0.0, None

        # 1. Roteamento de ultra-baixa latência (<2ms) para intenções imediatas
        fast_call = match_intent_fallback(prompt)
        if fast_call:
            return fast_call, 1.5, None

        # 2. Inferência via LLM local (llama-server) para consultas complexas
        formatted_prompt = (
            f"<|im_start|>system\n{SILVA_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
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

                # Reconstitui a tag se o modelo completou a partir do prefixo '<call>'
                if not content.startswith("<call>"):
                    full_output = f"<call>{content}"
                else:
                    full_output = content

                if not full_output.endswith("</call>"):
                    if "</call>" in full_output:
                        full_output = full_output.split("</call>")[0] + "</call>"
                    else:
                        full_output = f"{full_output}</call>"

                # Valida se a chamada corresponde a alguma ferramenta na whitelist
                has_valid_tool = False
                for tool_name in AVAILABLE_TOOLS:
                    if tool_name != "none" and (f"<{tool_name}(" in full_output or f"<call>{tool_name}(" in full_output):
                        has_valid_tool = True
                        break

                if not has_valid_tool:
                    full_output = "<call>none()</call>"

                return full_output, round(latency_ms, 2), None

        except urllib.error.URLError as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return "<call>none()</call>", round(latency_ms, 2), None
        except Exception as e:
            latency_ms = (time.perf_counter() - start_time) * 1000.0
            return "<call>none()</call>", round(latency_ms, 2), None
