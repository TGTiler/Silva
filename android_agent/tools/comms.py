"""
Módulo Comunicação do Silva: SMS, Chamadas, Notificações e Clipboard.
"""

import difflib
import json
import re
import subprocess
import time
import unicodedata
from typing import Any, Dict, Optional, Tuple

from .core import (
    SIMULATE_HARDWARE,
    _run_termux_cmd,
    _exec_android_intent,
    resolve_contact_or_number,
    sanitize_phone_number,
)

_CONTACTS_CACHE: Dict[str, Any] = {"timestamp": 0.0, "contacts": []}


def _resolve_contact_number(target: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve número ou nome de contato:
    - Se contiver letras, busca na agenda telefônica via termux-contact-list.
      Busca correspondência exata, substring ou aproximada (difflib sem acentos).
    - Se for apenas dígitos/+, sanitiza e valida número de telefone.
    Retorna (numero_limpo, nome_formatado) ou (None, None).
    """
    raw = str(target or "").strip()
    if not raw:
        return None, None

    has_letters = bool(re.search(r"[a-zA-ZáéíóúâêîôûãõçÁÉÍÓÚÂÊÎÔÛÃÕÇ]", raw))
    if not has_letters:
        clean = sanitize_phone_number(raw)
        digits_only = re.sub(r"\D", "", clean)
        if len(digits_only) >= 3:
            return clean, clean
        return None, None

    # Alvo com letras: consulta agenda de contatos
    contacts = []
    now = time.time()
    if now - _CONTACTS_CACHE.get("timestamp", 0.0) < 30.0 and _CONTACTS_CACHE.get("contacts"):
        contacts = _CONTACTS_CACHE["contacts"]
    else:
        try:
            res = _run_termux_cmd(["termux-contact-list"], timeout=4)
            if res.returncode == 0 and res.stdout.strip():
                contacts = json.loads(res.stdout)
                _CONTACTS_CACHE["timestamp"] = now
                _CONTACTS_CACHE["contacts"] = contacts
        except Exception:
            contacts = []

    if not contacts:
        return None, None

    def _norm(s: str) -> str:
        deaccent = unicodedata.normalize("NFKD", str(s or "")).encode("ASCII", "ignore").decode("ASCII")
        return re.sub(r"[^\w\s]", "", deaccent).strip().lower()

    target_norm = _norm(raw)
    candidates = []
    for c in contacts:
        c_name = c.get("name", "") or ""
        c_num = c.get("number") or c.get("phone") or ""
        if isinstance(c_num, list) and c_num:
            c_num = c_num[0]
        if c_name and c_num:
            clean_num = sanitize_phone_number(str(c_num))
            if clean_num:
                candidates.append((c_name, _norm(c_name), clean_num))

    if not candidates:
        return None, None

    # 1. Correspondência Exata
    for c_name, c_norm, clean_num in candidates:
        if target_norm == c_norm:
            return clean_num, c_name

    # 2. Correspondência por Substring / Palavra
    target_words = set(target_norm.split())
    for c_name, c_norm, clean_num in candidates:
        c_words = set(c_norm.split())
        if target_norm in c_norm or c_norm in target_norm or (target_words and target_words.issubset(c_words)):
            return clean_num, c_name

    # 3. Correspondência Aproximada (Fuzzy Matching via difflib)
    cand_map = {c_norm: (c_name, clean_num) for c_name, c_norm, clean_num in candidates}
    matches = difflib.get_close_matches(target_norm, list(cand_map.keys()), n=1, cutoff=0.60)
    if matches:
        matched_name, clean_num = cand_map[matches[0]]
        return clean_num, matched_name

    return None, None

def get_last_sms(limit: int = 5) -> Dict[str, Any]:
    """Lê as últimas mensagens SMS recebidas."""
    limit = max(1, min(int(limit), 20))
    if SIMULATE_HARDWARE:
        simulated_raw = [
            {"sender": "11987654321", "number": "11987654321", "date": "2026-11-20 20:30", "received": "2026-11-20 20:30", "body": "Chegando em 10 minutos!"},
            {"sender": "Nubank", "number": "Nubank", "date": "2026-11-20 18:45", "received": "2026-11-20 18:45", "body": "Compra de R$ 45,00 aprovada."},
            {"sender": "Google", "number": "Google", "date": "2026-11-20 12:15", "received": "2026-11-20 12:15", "body": "Seu código de verificação é 839201."}
        ][:limit]
        lines = [f"Silva: Últimos SMS recebidos ({len(simulated_raw)}):"]
        for idx, sms in enumerate(simulated_raw, 1):
            s_body = sms["body"].strip()
            if len(s_body) > 240:
                s_body = s_body[:237] + "..."
            lines.append(f"{idx}. De: {sms['sender']} ({sms['date']})\n   \"{s_body}\"")
        return {
            "status": "ok",
            "message": "\n".join(lines) + " [Simulado]",
            "data": simulated_raw
        }

    try:
        res = _run_termux_cmd(["termux-sms-list", "-l", str(limit)], timeout=8)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao obter SMS: {res.stderr.strip()}"}

        raw_messages = json.loads(res.stdout)
        formatted = []
        for sms in raw_messages:
            sender = sms.get("number") or sms.get("sender") or "Desconhecido"
            date_str = sms.get("received") or sms.get("date") or ""
            body_str = (sms.get("body") or "").strip()
            formatted.append({
                "sender": sender,
                "number": sender,
                "date": date_str,
                "received": date_str,
                "body": body_str
            })

        if not formatted:
            return {
                "status": "ok",
                "message": "Silva: Nenhuma mensagem SMS encontrada.",
                "data": []
            }

        lines = [f"Silva: Últimos SMS recebidos ({len(formatted)}):"]
        for idx, sms in enumerate(formatted, 1):
            s_body = sms["body"]
            if len(s_body) > 240:
                s_body = s_body[:237] + "..."
            lines.append(f"{idx}. De: {sms['sender']} ({sms['date']})\n   \"{s_body}\"")

        return {
            "status": "ok",
            "message": "\n".join(lines),
            "data": formatted
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao listar SMS: {str(e)}"}


def send_sms(number: str, message: str) -> Dict[str, Any]:
    """Envia SMS para o número ou contato especificado."""
    clean_target = resolve_contact_or_number(number)
    if not clean_target:
        return {"status": "error", "message": "Destinatário do SMS inválido."}

    clean_text = str(message).strip()
    if not clean_text:
        return {"status": "error", "message": "Mensagem SMS vazia."}

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: SMS enviado com sucesso para {clean_target}: '{clean_text}'. [Simulado]",
            "data": {"number": clean_target, "message": clean_text}
        }

    try:
        res = _run_termux_cmd(["termux-sms-send", "-n", clean_target, clean_text], timeout=10)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao enviar SMS: {res.stderr.strip()}"}
        return {
            "status": "ok",
            "message": f"Silva: SMS enviado com sucesso para {clean_target}.",
            "data": {"number": clean_target, "message": clean_text}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao disparar SMS: {str(e)}"}



def make_call(number: str = "", target: str = "") -> Dict[str, Any]:
    """
    Inicia uma chamada telefônica para o número ou contato informado.
    Utiliza discagem resiliente em 2 camadas:
      - Camada 1: termux-telephony-call direto.
      - Camada 2: Fallback universal via Intent ACTION_DIAL nativo.
    """
    raw_target = (target or number).strip()
    if not raw_target:
        return {"status": "error", "message": "Destinatário de discagem inválido. Informe o número ou contato."}

    clean_num, matched_name = _resolve_contact_number(raw_target)
    if not clean_num:
        return {
            "status": "error",
            "message": f"Contato '{raw_target}' não encontrado na agenda. Informe o número com DDD.",
            "data": {"target": raw_target}
        }

    display_target = f"{matched_name} ({clean_num})" if matched_name and matched_name != clean_num else clean_num

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Iniciando chamada direta para {display_target}... [Simulado]",
            "data": {"number": clean_num, "target": raw_target, "method": "simulated"}
        }

    # Camada 1: Discagem direta
    try:
        res = _run_termux_cmd(["termux-telephony-call", clean_num], timeout=6)
        if res.returncode == 0:
            return {
                "status": "ok",
                "message": f"Silva: Iniciando chamada direta para {display_target}.",
                "data": {"number": clean_num, "target": raw_target, "method": "telephony_call"}
            }
    except Exception:
        pass

    # Camada 2 (Fallback Universal): Abrir tela de discagem nativa via Intent DIAL
    try:
        res_intent = _exec_android_intent(f'am start -a android.intent.action.DIAL -d "tel:{clean_num}"', timeout=6)
        if res_intent.returncode == 0:
            return {
                "status": "ok",
                "message": f"Silva: Abrindo discador com o número {clean_num} pronto para chamada.",
                "data": {"number": clean_num, "target": raw_target, "method": "dial_intent"}
            }
        return {
            "status": "error",
            "message": f"Falha ao acionar discador nativo: {res_intent.stderr.strip()}",
            "data": {"number": clean_num, "target": raw_target}
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Erro ao acionar discador nativo: {str(e)}",
            "data": {"number": clean_num, "target": raw_target}
        }



def get_clipboard() -> Dict[str, Any]:
    """Lê o conteúdo da área de transferência."""
    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": "Silva: Conteúdo da área de transferência lido com sucesso. [Simulado]",
            "data": {"clipboard": "https://github.com/silva-agent"}
        }

    try:
        res = _run_termux_cmd(["termux-clipboard-get"], timeout=5)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao ler clipboard: {res.stderr.strip()}"}
        content = res.stdout
        clean_content = content.strip() if content else ""
        if clean_content:
            preview = (clean_content[:80] + "...") if len(clean_content) > 80 else clean_content
            msg = f"Silva: Área de transferência: '{preview}'"
        else:
            msg = "Silva: Área de transferência vazia (ou bloqueada em segundo plano pelo Android — libere READ_CLIPBOARD via ADB para o Termux:API)."
        return {
            "status": "ok",
            "message": msg,
            "data": {"clipboard": content}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao ler clipboard: {str(e)}"}


def set_clipboard(text: str) -> Dict[str, Any]:
    """Escreve um texto na área de transferência."""
    txt = str(text)
    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": "Silva: Texto copiado para a área de transferência. [Simulado]",
            "data": {"clipboard": txt}
        }

    try:
        # Usa input via stdin para evitar problemas de escaping
        proc = subprocess.run(
            ["termux-clipboard-set"],
            input=txt,
            text=True,
            capture_output=True,
            timeout=5
        )
        if proc.returncode != 0:
            return {"status": "error", "message": f"Falha ao gravar no clipboard: {proc.stderr.strip()}"}
        return {
            "status": "ok",
            "message": "Silva: Texto copiado para a área de transferência.",
            "data": {"clipboard": txt}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao copiar para clipboard: {str(e)}"}



def get_notifications(app: str = "") -> Dict[str, Any]:
    """Lê as notificações recentes do Android filtrando opcionalmente por app."""
    app_filter = str(app).strip().lower()

    if SIMULATE_HARDWARE:
        sim_notifs = [
            {"app": "WhatsApp", "title": "Mariana", "content": "Não esquece do documento amanhã!"},
            {"app": "Nubank", "title": "Transferência Recebida", "content": "Você recebeu R$ 150,00 de Carlos."},
            {"app": "Gmail", "title": "Alerta de Segurança", "content": "Novo login detectado."},
            {"app": "Instagram", "title": "Novo seguidor", "content": "lucas_dev começou a seguir você."}
        ]
        if app_filter:
            sim_notifs = [n for n in sim_notifs if app_filter in n["app"].lower() or app_filter in n["title"].lower()]

        if not sim_notifs:
            msg = f"Silva: Nenhuma notificação recente{f' do app {app_filter}' if app_filter else ''}. [Simulado]"
            return {"status": "ok", "message": msg, "data": []}

        formatted = [f"[{n['app']}] {n['title']}: {n['content']}" for n in sim_notifs[:5]]
        msg = "Silva: Notificações recentes:\n" + "\n".join(formatted) + " [Simulado]"
        return {"status": "ok", "message": msg, "data": sim_notifs[:5]}

    try:
        res = _run_termux_cmd(["termux-notification-list"], timeout=8)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao ler notificações: {res.stderr.strip()}"}

        notifs = json.loads(res.stdout) if res.stdout.strip() else []
        filtered = []
        for n in notifs:
            pkg = n.get("packageName", "").lower()
            appName = n.get("appName", "").lower()
            title = n.get("title", "")
            content = n.get("content", "")
            display_app = n.get("appName") or n.get("packageName", "App")

            if app_filter:
                if app_filter not in pkg and app_filter not in appName and app_filter not in title.lower():
                    continue

            filtered.append({
                "app": display_app,
                "title": title,
                "content": content
            })

        if not filtered:
            msg = f"Silva: Nenhuma notificação encontrada{f' para o aplicativo {app_filter}' if app_filter else ''}."
            return {"status": "ok", "message": msg, "data": []}

        formatted = [f"[{item['app']}] {item['title']}: {item['content']}" for item in filtered[:5]]
        msg = f"Silva: {len(filtered[:5])} notificação(ões) recente(s):\n" + "\n".join(formatted)
        return {"status": "ok", "message": msg, "data": filtered[:5]}
    except Exception as e:
        return {"status": "error", "message": f"Erro ao acessar notificações: {str(e)}"}


