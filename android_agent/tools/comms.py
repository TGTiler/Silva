"""
Módulo Comunicação do Silva: SMS, Chamadas, Notificações e Clipboard.
"""

import difflib
import json
import re
import subprocess
import time
import unicodedata
import urllib.parse
from typing import Any, Dict, Optional, Tuple

from .core import (
    SIMULATE_HARDWARE,
    _run_termux_cmd,
    _exec_android_intent,
    resolve_contact_or_number,
    sanitize_phone_number,
)
from .adb_bridge import ensure_adb_connected, run_adb_shell
from .contacts import (
    resolve_contact_detailed,
    save_contact_to_memory,
    format_disambiguation_message,
)
from .ui_automator import (
    dump_ui_nodes,
    find_ui_node,
    tap_coords,
    tap_element,
    type_text_unicode,
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


def _format_whatsapp_phone(raw_phone: str) -> Optional[str]:
    """Normaliza telefone para formato internacional sem '+' (adiciona DDI 55 se BR)."""
    digits = re.sub(r"\D", "", str(raw_phone or ""))
    if len(digits) < 8:
        return None
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    return digits


def _resolve_whatsapp_target(recipient: str) -> Tuple[Optional[str], str]:
    """
    Resolve destinatário do WhatsApp usando o resolvedor unificado de contatos
    (número direto -> memory.db -> agenda Android).
    """
    clean_recipient = str(recipient or "").strip()
    if not clean_recipient:
        return None, ""

    info = resolve_contact_detailed(clean_recipient)
    if info.get("number"):
        wa_num = _format_whatsapp_phone(info["number"])
        display = info.get("name") or clean_recipient
        return wa_num, display

    return None, clean_recipient


def _automate_whatsapp_send(recipient: str, message: str) -> Dict[str, Any]:
    """
    Automatiza o envio de mensagem no WhatsApp:
    1. Resolve contato (memory.db / agenda) para DDI 55.
    2. Abre chat via Deep Link oficial (ou busca na UI quando só há nome).
    3. Se ADB local conectado, localiza e toca no botão 'Enviar' via uiautomator.
    """
    clean_recipient = str(recipient or "").strip()
    clean_message = str(message or "").strip()
    if not clean_recipient:
        return {"status": "error", "message": "Destinatário do WhatsApp inválido."}
    if not clean_message:
        return {"status": "error", "message": "Mensagem do WhatsApp vazia."}

    wa_num, display_target = _resolve_whatsapp_target(clean_recipient)
    adb_serial = ensure_adb_connected()

    if SIMULATE_HARDWARE and not adb_serial:
        return {
            "status": "ok",
            "message": f"Silva: Mensagem enviada no WhatsApp para {display_target}: '{clean_message}'. [Simulado]",
            "data": {"recipient": display_target, "phone": wa_num, "message": clean_message, "channel": "whatsapp"},
        }

    opened = False
    if wa_num:
        encoded_msg = urllib.parse.quote(clean_message)
        deep_link = f"https://api.whatsapp.com/send?phone={wa_num}&text={encoded_msg}"
        for pkg in ("com.whatsapp", "com.whatsapp.w4b"):
            if adb_serial:
                ok_am, out_am = run_adb_shell(
                    ["am", "start", "-a", "android.intent.action.VIEW", "-d", deep_link, "-p", pkg],
                    timeout=6.0,
                )
                if ok_am and "Error:" not in out_am:
                    opened = True
                    break
            else:
                if _exec_android_intent(["am", "start", "-a", "android.intent.action.VIEW", "-d", deep_link, "-p", pkg]):
                    opened = True
                    break
    elif adb_serial:
        # Fallback por nome sem telefone: abre WhatsApp, pesquisa contato e digita mensagem
        ok_open, _ = run_adb_shell(
            ["monkey", "-p", "com.whatsapp", "-c", "android.intent.category.LAUNCHER", "1"],
            timeout=6.0,
        )
        if ok_open:
            time.sleep(1.2)
            ok_search, _ = tap_element("Pesquisar", timeout=3.0)
            if not ok_search:
                ok_search, _ = tap_element("com.whatsapp:id/menuitem_search", timeout=2.0)
            if ok_search:
                type_text_unicode(clean_recipient)
                time.sleep(0.8)
                tap_element(clean_recipient, timeout=3.0)
                time.sleep(0.8)
                type_text_unicode(clean_message)
                opened = True

    if not opened:
        return {
            "status": "error",
            "message": f"Não foi possível abrir o WhatsApp para '{display_target}'.",
            "data": {"recipient": display_target, "phone": wa_num, "channel": "whatsapp"},
        }

    if adb_serial:
        time.sleep(1.5)
        nodes = dump_ui_nodes()
        send_node = (
            find_ui_node("Enviar", nodes=nodes, clickable_only=True)
            or find_ui_node("Send", nodes=nodes, clickable_only=True)
            or find_ui_node("com.whatsapp:id/send", nodes=nodes, clickable_only=True)
        )
        if send_node:
            ok_tap, _ = tap_coords(send_node["cx"], send_node["cy"])
            if ok_tap:
                return {
                    "status": "ok",
                    "message": f"Mensagem enviada no WhatsApp para {display_target}: '{clean_message}'.",
                    "data": {
                        "recipient": display_target,
                        "phone": wa_num,
                        "message": clean_message,
                        "channel": "whatsapp",
                        "sent": True,
                    },
                }

    return {
        "status": "ok",
        "message": (
            f"Conversa aberta no WhatsApp para {display_target} com a mensagem pronta. "
            "Toque em enviar (conecte o ADB local para envio automático sem toques)."
        ),
        "data": {
            "recipient": display_target,
            "phone": wa_num,
            "message": clean_message,
            "channel": "whatsapp",
            "sent": False,
        },
    }


def save_contact(name: str, phone: str) -> Dict[str, Any]:
    """Cadastra ou atualiza um contato (nome e telefone) na memória persistente (memory.db)."""
    return save_contact_to_memory(name, phone)


def get_contact(name: str) -> Dict[str, Any]:
    """Consulta um contato no memory.db e na agenda nativa do Android."""
    clean_name = str(name or "").strip()
    if not clean_name:
        return {"status": "error", "message": "Informe o nome do contato para consultar."}

    info = resolve_contact_detailed(clean_name)
    if info.get("ambiguous"):
        return {
            "status": "ok",
            "message": format_disambiguation_message(clean_name, info.get("candidates", [])),
            "data": {"found": True, "ambiguous": True, "candidates": info.get("candidates", [])},
        }

    if info.get("number"):
        disp_name = info.get("name") or clean_name
        num = info["number"]
        src = info.get("source", "agenda")
        return {
            "status": "ok",
            "message": f"Silva: Contato encontrado — {disp_name}: {num} (fonte: {src}).",
            "data": {"found": True, "name": disp_name, "phone": num, "source": src},
        }

    return {
        "status": "ok",
        "message": f"Silva: Não encontrei nenhum contato chamado '{clean_name}' na memória ou na agenda.",
        "data": {"found": False, "name": clean_name},
    }


def send_whatsapp(contact_name: str, message: str) -> Dict[str, Any]:
    """
    Envia mensagem diretamente no WhatsApp combinando resolução de contatos,
    deep link https://wa.me/{phone}?text=... e clique automático no botão Enviar via ADB/ui_automator.
    """
    clean_contact = str(contact_name or "").strip()
    clean_message = str(message or "").strip()
    if not clean_contact:
        return {"status": "error", "message": "Nome ou telefone do destinatário não informado."}
    if not clean_message:
        return {"status": "error", "message": "Mensagem do WhatsApp vazia."}

    info = resolve_contact_detailed(clean_contact)
    if info.get("ambiguous"):
        return {
            "status": "error",
            "message": format_disambiguation_message(clean_contact, info.get("candidates", [])),
            "data": {"ambiguous": True, "candidates": info.get("candidates", [])},
        }

    if not info.get("number"):
        return {
            "status": "error",
            "message": (
                f"Contato '{clean_contact}' não encontrado na memória ou na agenda. "
                "Salve o número com save_contact ou informe o telefone diretamente."
            ),
            "data": {"found": False, "contact_name": clean_contact},
        }

    wa_num = _format_whatsapp_phone(info["number"])
    display_target = info.get("name") or clean_contact
    adb_serial = ensure_adb_connected()

    if SIMULATE_HARDWARE and not adb_serial:
        return {
            "status": "ok",
            "message": f"Silva: Mensagem enviada no WhatsApp para {display_target} ({wa_num}): '{clean_message}'. [Simulado]",
            "data": {"recipient": display_target, "phone": wa_num, "message": clean_message, "channel": "whatsapp"},
        }

    encoded_msg = urllib.parse.quote(clean_message)
    deep_link = f"https://wa.me/{wa_num}?text={encoded_msg}"
    opened = False
    for pkg in ("com.whatsapp", "com.whatsapp.w4b"):
        if adb_serial:
            ok_am, out_am = run_adb_shell(
                ["am", "start", "-a", "android.intent.action.VIEW", "-d", deep_link, "-p", pkg],
                timeout=6.0,
            )
            if ok_am and "Error:" not in out_am:
                opened = True
                break
        else:
            if _exec_android_intent(["am", "start", "-a", "android.intent.action.VIEW", "-d", deep_link, "-p", pkg]):
                opened = True
                break

    if not opened:
        return {
            "status": "error",
            "message": f"Não foi possível abrir o WhatsApp para '{display_target}'.",
            "data": {"recipient": display_target, "phone": wa_num},
        }

    if adb_serial:
        time.sleep(1.5)
        nodes = dump_ui_nodes()
        send_node = (
            find_ui_node("com.whatsapp:id/send", nodes=nodes, clickable_only=True)
            or find_ui_node("Enviar", nodes=nodes, clickable_only=True)
            or find_ui_node("Send", nodes=nodes, clickable_only=True)
        )
        if send_node:
            ok_tap, _ = tap_coords(send_node["cx"], send_node["cy"])
            if ok_tap:
                return {
                    "status": "ok",
                    "message": f"Silva: Mensagem enviada no WhatsApp para {display_target}: '{clean_message}'.",
                    "data": {"recipient": display_target, "phone": wa_num, "message": clean_message, "sent": True},
                }

    return {
        "status": "ok",
        "message": (
            f"Silva: A mensagem para {display_target} já foi preenchida na tela do WhatsApp e aguarda toque manual "
            "(ADB offline ou tela bloqueada)."
        ),
        "data": {"recipient": display_target, "phone": wa_num, "message": clean_message, "sent": False},
    }


_NOISE_PACKAGES = {
    "android",
    "com.android.systemui",
    "com.android.providers.downloads",
    "com.samsung.android.incallui",
    "com.sec.android.app.launcher",
}
_NOISE_KEYWORDS = (
    "carregando", "charging", "bateria", "usb conectado", "depuração usb",
    "usb debugging", "executando em segundo plano", "running in the background",
)
_FRIENDLY_APP_MAP = {
    "com.whatsapp": "WhatsApp",
    "com.whatsapp.w4b": "WhatsApp Business",
    "com.nu.production": "Bancos",
    "br.com.intermedium": "Bancos",
    "com.itau": "Bancos",
    "br.com.bb.android": "Bancos",
    "com.bradesco": "Bancos",
    "com.santander.app": "Bancos",
    "com.google.android.gm": "Gmail",
    "com.android.mms": "SMS",
    "com.google.android.apps.messaging": "SMS",
    "com.samsung.android.messaging": "SMS",
    "com.instagram.android": "Instagram",
    "org.telegram.messenger": "Telegram",
}


def _parse_dumpsys_notifications(raw_dump: str) -> list:
    items = []
    cur_pkg = ""
    cur_title = ""
    cur_text = ""
    for line in (raw_dump or "").splitlines():
        s = line.strip()
        if s.startswith("NotificationRecord("):
            if cur_pkg and (cur_title or cur_text):
                items.append({"packageName": cur_pkg, "title": cur_title, "text": cur_text})
            cur_pkg = ""
            cur_title = ""
            cur_text = ""
            m_pkg = re.search(r"pkg=([^\s]+)", s)
            if m_pkg:
                cur_pkg = m_pkg.group(1)
        elif "android.title=" in s:
            cur_title = s.split("android.title=", 1)[1].strip(" ()'\"")
        elif "android.text=" in s:
            cur_text = s.split("android.text=", 1)[1].strip(" ()'\"")
    if cur_pkg and (cur_title or cur_text):
        items.append({"packageName": cur_pkg, "title": cur_title, "text": cur_text})
    return items


def summarize_notifications(app_filter: str = "") -> Dict[str, Any]:
    """Coleta, filtra ruídos técnicos e resume notificações ativas agrupadas por app."""
    raw_filter = str(app_filter or "").strip().lower()
    raw_notifs = []
    adb_serial = ensure_adb_connected()

    if SIMULATE_HARDWARE and not adb_serial:
        raw_notifs = [
            {"packageName": "com.whatsapp", "title": "João", "text": "Reunião confirmada às 15h"},
            {"packageName": "com.nu.production", "title": "Nubank", "text": "Compra aprovada de R$ 42,00"},
            {"packageName": "com.android.systemui", "title": "Sistema", "text": "Carregando lentamente"},
        ]
    else:
        got_termux = False
        if not SIMULATE_HARDWARE:
            try:
                res = _run_termux_cmd(["termux-notification-list"], timeout=5)
                if res.returncode == 0 and res.stdout.strip():
                    parsed = json.loads(res.stdout)
                    if isinstance(parsed, list):
                        raw_notifs = parsed
                        got_termux = True
            except Exception:
                pass
        if not got_termux and adb_serial:
            ok_adb, out_adb = run_adb_shell(["dumpsys", "notification", "--noredact"], timeout=8.0)
            if ok_adb and out_adb:
                raw_notifs = _parse_dumpsys_notifications(out_adb)

    grouped: Dict[str, list] = {}
    seen_entries = set()

    for n in raw_notifs:
        pkg = str(n.get("packageName") or "").strip()
        title = str(n.get("title") or "").strip()
        body = str(n.get("content") or n.get("text") or "").strip()
        if not pkg or pkg in _NOISE_PACKAGES:
            continue
        combined_low = f"{title} {body}".lower()
        if not combined_low.strip() or any(kw in combined_low for kw in _NOISE_KEYWORDS):
            continue

        friendly = _FRIENDLY_APP_MAP.get(pkg, pkg.split(".")[-1].capitalize())
        if raw_filter and raw_filter not in friendly.lower() and raw_filter not in pkg.lower():
            continue

        snippet = f"{title}: {body}" if title and body else (title or body)
        dedup_key = (friendly, snippet)
        if dedup_key in seen_entries:
            continue
        seen_entries.add(dedup_key)
        grouped.setdefault(friendly, []).append(snippet)

    if not grouped:
        scope = f" de '{app_filter}'" if raw_filter else ""
        return {
            "status": "ok",
            "message": f"Silva: Nenhuma notificação importante{scope} encontrada no momento.",
            "data": {"total": 0, "groups": {}},
        }

    total = sum(len(v) for v in grouped.values())
    lines = [f"Silva: Resumo de {total} notificação(ões):"]
    for app_name, msgs in grouped.items():
        preview = "; ".join(msgs[:3])
        extra = f" (+{len(msgs) - 3})" if len(msgs) > 3 else ""
        lines.append(f"• {app_name} ({len(msgs)}): {preview}{extra}")

    return {
        "status": "ok",
        "message": "\n".join(lines),
        "data": {"total": total, "groups": grouped},
    }


def send_sms(number: str, message: str, channel: str = "sms") -> Dict[str, Any]:
    """Envia SMS ou mensagem no WhatsApp (quando channel='whatsapp') para o contato/número."""
    if str(channel or "sms").strip().lower() in ("whatsapp", "zap", "wpp"):
        return _automate_whatsapp_send(number, message)

    info = resolve_contact_detailed(number)
    if info.get("ambiguous"):
        return {
            "status": "error",
            "message": format_disambiguation_message(number, info.get("candidates", [])),
            "data": {"candidates": info.get("candidates", [])},
        }

    clean_target = info.get("number") or resolve_contact_or_number(number)
    if not clean_target:
        return {"status": "error", "message": f"Contato ou número '{number}' não encontrado."}

    display_name = info.get("name")
    display_target = f"{display_name} ({clean_target})" if display_name and display_name != clean_target else clean_target

    clean_text = str(message).strip()
    if not clean_text:
        return {"status": "error", "message": "Mensagem SMS vazia."}

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: SMS enviado com sucesso para {display_target}: '{clean_text}'. [Simulado]",
            "data": {"number": clean_target, "name": display_name, "message": clean_text}
        }

    try:
        res = _run_termux_cmd(["termux-sms-send", "-n", clean_target, clean_text], timeout=10)
        if res.returncode != 0:
            return {"status": "error", "message": f"Falha ao enviar SMS: {res.stderr.strip()}"}
        return {
            "status": "ok",
            "message": f"Silva: SMS enviado com sucesso para {display_target}.",
            "data": {"number": clean_target, "name": display_name, "message": clean_text}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao disparar SMS: {str(e)}"}



def make_call(number: str = "", target: str = "") -> Dict[str, Any]:
    """
    Inicia uma chamada telefônica para o número ou contato informado.
    Utiliza resolvedor unificado de contatos + discagem resiliente em 2 camadas:
      - Camada 0/1: ADB ACTION_CALL / termux-telephony-call direto.
      - Camada 2: Fallback universal via Intent ACTION_DIAL nativo.
    """
    raw_target = (target or number).strip()
    if not raw_target:
        return {"status": "error", "message": "Destinatário de discagem inválido. Informe o número ou contato."}

    info = resolve_contact_detailed(raw_target)
    if info.get("ambiguous"):
        return {
            "status": "error",
            "message": format_disambiguation_message(raw_target, info.get("candidates", [])),
            "data": {"target": raw_target, "candidates": info.get("candidates", [])},
        }

    clean_num = info.get("number")
    matched_name = info.get("name")
    if not clean_num:
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

    # Camada 0: ADB Local privilegiado (ACTION_CALL direta sem parar no discador)
    ok_adb, out_adb = run_adb_shell(
        ["am", "start", "-a", "android.intent.action.CALL", "-d", f"tel:{clean_num}"],
        timeout=6.0,
    )
    if ok_adb and not any(err in out_adb for err in ("Error:", "SecurityException", "Permission")):
        return {
            "status": "ok",
            "message": f"Silva: Iniciando chamada direta para {display_target}.",
            "data": {"number": clean_num, "target": raw_target, "method": "adb_call"}
        }

    # Camada 1: Discagem direta via Termux:API
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


