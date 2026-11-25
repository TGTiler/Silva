"""
Módulo Apps, Mobilidade e Utilidades do Silva: Abertura de Apps, Uber/99, iFood, Play Store, Piadas e Capacidades.
"""

import difflib
import json
import random
import re
import shlex
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

from .core import (
    APP_PACKAGES,
    RESOLVED_APP_ACTIVITIES,
    SIMULATE_HARDWARE,
    _exec_android_intent,
    load_last_location,
)
from .adb_bridge import ensure_adb_connected, is_screen_unlocked, run_adb_shell
from .ui_automator import _UI_LOCK, dump_ui_nodes, get_screen_dimensions, press_key, tap_coords, tap_element, type_text_unicode
from .comms import set_clipboard
from .memory_schedule import _load_memory, _normalize_text, recall_note
from .weather_web import set_location_state

JOKES_PTBR = [
    "Por que o computador foi ao médico? Porque ele estava com um vírus!",
    "Existem 10 tipos de pessoas no mundo: as que entendem binário e as que não entendem.",
    "O que o botão zero disse para o botão um? 'Você está no meu espaço!'.",
    "Por que os programadores preferem o modo escuro? Porque a luz atrai bugs!",
    "Qual é o café favorito do desenvolvedor? O Java.",
    "O que a chave de fenda foi fazer no baile? Foi desenroscar os passos.",
    "Por que o livro de matemática ficou triste? Porque tinha problemas demais.",
    "O que uma impressora disse para a outra? 'Essa folha é sua ou é impressão minha?'.",
    "Qual é o cúmulo da paciência? Jogar xadrez contra o espelho e esperar a jogada do adversário.",
    "Por que o JavaScript foi ao psicólogo? Porque ele tinha problemas de escopo e não se sentia definido.",
    "O que o pato disse para a pata? 'Vem quá!'.",
    "Qual é o peixe que caiu do décimo andar? Aaaaatum!",
    "O que o zero disse para o oito? 'Belo cinto!'",
    "Por que o esqueleto não brigou com ninguém? Porque ele não tinha estômago para isso.",
    "Qual é o animal que não vale mais nada? O javali.",
    "Por que o desenvolvedor não gosta de florestas? Tem muitos bugs e pouca memória ram.",
    "O que o tomate foi fazer no banco? Foi tirar o extrato.",
    "Como as estrelas lavam o cabelo? Com Milky Way.",
    "Por que o alarme do celular tocou feliz hoje? Porque acordou com disposição!",
    "O que o Wi-Fi disse para o smartphone? 'Sinto uma forte conexão entre nós'.",
    "Qual a fórmula da água benta? H Deus O.",
    "Por que a aranha é o animal mais conectado do mundo? Porque vive na web.",
    "O que o ponto de exclamação falou pro de interrogação? 'Nossa, que cara curioso você é!'.",
    "Como se chama uma cobra que resolve equações? Uma píton (Python) matemática.",
    "Por que o banco de dados terminou o namoro? Porque não aguentava mais queries e relacionamentos complicados.",
    "O que um algoritmo disse para o outro? 'Siga meus passos!'.",
    "Qual é a cidade que não tem táxi? Uberlândia."
]

_LAST_JOKE: Optional[str] = None

APP_NOISE_WORDS = {
    "o", "a", "os", "as", "um", "uma", "uns", "umas",
    "de", "do", "da", "dos", "das", "em", "no", "na", "nos", "nas",
    "pra", "para", "pro", "com", "sem",
    "app", "aplicativo", "abra", "abrir", "abre",
    "hoje", "agora", "por favor", "pfv", "silva", "ei silva", "ai", "aí"
}

def interact_screen(action: str, label: str = "") -> Dict[str, Any]:
    """
    Interage com a tela atual do Android via uiautomator + ADB local:
    - action='tap': localiza 'label' e toca no botão/container clicável.
    - action='read': lê e resume os textos visíveis na tela atual.
    """
    act = str(action or "").strip().lower()
    clean_label = str(label or "").strip()

    if not ensure_adb_connected():
        return {
            "status": "error",
            "message": "ADB local não conectado. Conecte a depuração por Wi-Fi para interagir com a tela.",
        }

    if act == "read":
        nodes = dump_ui_nodes()
        texts = []
        seen = set()
        for n in nodes:
            txt = (n.get("text") or n.get("content_desc") or "").strip()
            if txt and txt not in seen:
                seen.add(txt)
                texts.append(txt)
        if not texts:
            return {"status": "ok", "message": "Nenhum texto visível foi encontrado na tela atual.", "data": []}
        preview = " | ".join(texts[:25])
        return {
            "status": "ok",
            "message": f"Elementos visíveis na tela ({len(texts)}): {preview}",
            "data": texts[:25],
        }

    if act == "tap":
        if not clean_label:
            return {"status": "error", "message": "Informe o texto do botão ou elemento para tocar."}
        adb_ser = ensure_adb_connected()
        if adb_ser:
            unlocked, lock_msg = is_screen_unlocked(serial=adb_ser)
            if not unlocked:
                return {"status": "error", "message": lock_msg, "data": {"action": "tap", "label": clean_label, "locked": True}}
        ok, msg = tap_element(clean_label, timeout=4.0)
        return {
            "status": "ok" if ok else "error",
            "message": f"Silva: {msg}",
            "data": {"action": "tap", "label": clean_label, "success": ok},
        }

    return {"status": "error", "message": f"Ação de tela desconhecida: '{action}'."}


def open_app(app_name: str, action: str = "", label: str = "") -> Dict[str, Any]:
    """Abre um aplicativo pelo nome ou pacote Android, ou executa interação na tela atual."""
    act = str(action or "").strip().lower()
    raw_name = str(app_name or "").strip()
    if act in ("tap", "read"):
        return interact_screen(act, label=label or raw_name)
    if raw_name.startswith("ui:"):
        parts = raw_name.split(":", 2)
        ui_act = parts[1] if len(parts) > 1 else "read"
        ui_label = parts[2] if len(parts) > 2 else ""
        return interact_screen(ui_act, label=label or ui_label)

    raw_key = str(app_name).strip().lower()

    # 1. Limpeza de termos de cortesia/tempo/ruído nas bordas
    tokens = raw_key.split()
    while tokens and tokens[0] in APP_NOISE_WORDS:
        tokens.pop(0)
    while tokens and tokens[-1] in APP_NOISE_WORDS:
        tokens.pop()

    clean_key = " ".join(tokens) if tokens else raw_key
    clean_key_unaccent = unicodedata.normalize("NFKD", clean_key).encode("ASCII", "ignore").decode("utf-8").strip()
    raw_key_unaccent = unicodedata.normalize("NFKD", raw_key).encode("ASCII", "ignore").decode("utf-8").strip()

    # 2. Resolução do pacote
    package = None
    matched_app = None

    # 2a. Busca direta no APP_PACKAGES
    for candidate in [clean_key, clean_key_unaccent, raw_key, raw_key_unaccent]:
        if candidate in APP_PACKAGES:
            matched_app = candidate
            package = APP_PACKAGES[candidate]
            break

    # 2b. Verificação de substring caso ainda não tenha encontrado
    if not package:
        for app_k, pkg in APP_PACKAGES.items():
            app_k_unaccent = unicodedata.normalize("NFKD", app_k).encode("ASCII", "ignore").decode("utf-8").strip()
            if clean_key_unaccent and (app_k_unaccent == clean_key_unaccent or app_k_unaccent in clean_key_unaccent or clean_key_unaccent in app_k_unaccent):
                matched_app = app_k
                package = pkg
                break

    # 2c. Fuzzy matching com difflib (cutoff=0.72)
    if not package and clean_key_unaccent:
        all_app_keys = list(APP_PACKAGES.keys())
        close_matches = difflib.get_close_matches(clean_key_unaccent, all_app_keys, n=1, cutoff=0.72)
        if close_matches:
            matched_app = close_matches[0]
            package = APP_PACKAGES[matched_app]

    key = matched_app if matched_app else (clean_key or raw_key)
    if not package:
        package = key

    packages_to_try = [package]
    if key == "tiktok" or package in ("com.zhiliaoapp.musically", "com.ss.android.ugc.trill"):
        packages_to_try = ["com.zhiliaoapp.musically", "com.ss.android.ugc.trill"]

    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Abrindo aplicativo '{key}' ({packages_to_try[0]}). [Simulado]",
            "data": {"app": key, "package": packages_to_try[0]}
        }

    try:
        opened_pkg = None
        if ensure_adb_connected():
            for pkg in packages_to_try:
                if "/" in pkg:
                    ok_adb, out_adb = run_adb_shell(["am", "start", "-n", pkg], timeout=5.0)
                else:
                    ok_adb, out_adb = run_adb_shell(
                        ["monkey", "-p", pkg, "-c", "android.intent.category.LAUNCHER", "1"],
                        timeout=5.0,
                    )
                if ok_adb and not any(err in out_adb for err in ("Error:", "No activities found", "aborted")):
                    opened_pkg = pkg
                    break

        if not opened_pkg:
            for pkg in packages_to_try:
                # 1. Componente explícito se fornecido (ex: pkg/activity)
                if "/" in pkg:
                    res_c = _exec_android_intent(f"am start -n {pkg}")
                    if res_c.returncode == 0 and "Error:" not in res_c.stdout:
                        opened_pkg = pkg
                        break

                # 2. Resolução exata via mapa de Activities verificadas no dispositivo
                if pkg in RESOLVED_APP_ACTIVITIES and RESOLVED_APP_ACTIVITIES[pkg]:
                    act_comp = RESOLVED_APP_ACTIVITIES[pkg]
                    res_act = _exec_android_intent(f"am start -n {act_comp}")
                    if res_act.returncode == 0 and "Error:" not in res_act.stdout:
                        opened_pkg = pkg
                        break

                # 3. Fallback am start com categoria LAUNCHER
                res_am = _exec_android_intent(f"am start -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -p {pkg}")
                if res_am.returncode == 0 and "Error:" not in res_am.stdout:
                    opened_pkg = pkg
                    break

                # 4. Fallback am start direto em Activities comuns
                for act in [".MainActivity", ".Main", ".Calculator", ".HomeActivity", ".SplashActivity"]:
                    res_act = _exec_android_intent(f"am start -n {pkg}/{act}")
                    if res_act.returncode == 0 and "Error:" not in res_act.stdout:
                        opened_pkg = pkg
                        break
                if opened_pkg:
                    break

        if not opened_pkg:
            return {
                "status": "error",
                "message": f"Não foi possível abrir o app '{key}'. Verifique se o pacote '{packages_to_try[0]}' está instalado."
            }

        return {
            "status": "ok",
            "message": f"Silva: Abrindo {key}.",
            "data": {"app": key, "package": opened_pkg}
        }
    except Exception as e:
        return {"status": "error", "message": f"Erro ao abrir aplicativo: {str(e)}"}



def tell_joke() -> Dict[str, Any]:
    """Retorna uma piada curta aleatória em Português do Brasil sem repetir consecutivamente."""
    global _LAST_JOKE
    candidates = [j for j in JOKES_PTBR if j != _LAST_JOKE] if len(JOKES_PTBR) > 1 else JOKES_PTBR
    chosen = random.choice(candidates)
    _LAST_JOKE = chosen
    return {
        "status": "ok",
        "message": f"Silva: {chosen}",
        "data": {"joke": chosen}
    }



def none() -> Dict[str, Any]:
    """Chamada quando o comando não aciona nenhuma ferramenta do smartphone."""
    return {
        "status": "ok",
        "message": (
            "Silva: Sou um micro-agente focado no controle do seu celular (bateria, lanterna, fotos, SMS, apps). "
            "Não encontrei uma ferramenta específica para essa solicitação."
        ),
        "data": {}
    }



def _clean_ride_destination(raw_dest: str) -> str:
    """
    Remove prefixos conversacionais e sufixos de cortesia de um destino de corrida.
    Exemplos:
      "mim ir ao Shopping Recife" -> "Shopping Recife"
      "eu ir pro aeroporto pfv" -> "aeroporto"
      "aqui pra mim pra casa da minha mãe agora por favor" -> "casa da minha mãe"
    """
    if not raw_dest:
        return ""
    text = str(raw_dest).strip()

    # 1. Sufixos de cortesia e ruídos no final
    suffix_pat = (
        r"(?i)\s+(?:pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|rapidinho|r[aá]pido|"
        r"aqui|blz|beleza|valeu|vlw|obrigad[oa]|silva|logo|j[aá]|aí|ai|"
        r"de\s+uber|de\s+99|no\s+uber|na\s+99|no\s+99|na\s+99\s*pop|no\s+99\s*pop|"
        r"pelo\s+uber|pela\s+99|pelo\s+99)$"
    )
    for _ in range(6):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    # 2. Prefixos conversacionais no início (repetidos até limpar completamente)
    prefix_patterns = [
        r"(?i)^(?:de\s+onde\s+estou|daqui|aqui)\b\s*",
        r"(?i)^(?:pra\s+mim|para\s+mim|mim|eu|gente|nós|nos)\b\s*",
        r"(?i)^(?:por\s+favor|pfv|pfvr|rapidinho|r[aá]pido|agora|agr|j[aá]|logo)\b\s*",
        r"(?i)^(?:me\s+levar|me\s+leva|me\s+leve|levar|leva|leve|chegar|voltar|ir)\b\s*",
        r"(?i)^(?:para|pra|pro|pras|pros)\b\s*",
        r"(?i)^p/\s*",
        r"(?i)^(?:ao|aos|à|às|no|na|nos|nas|em|até|ate)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
    ]

    for _ in range(12):
        prev = text
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        for pat in prefix_patterns:
            text = re.sub(pat, '', text).strip()
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        if text == prev:
            break

    for _ in range(6):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r'[?!.,;:\"`\'\s]+$', '', text).strip()
        if text == prev:
            break
    return text.strip()


def _geocode_destination(destination: str) -> Optional[Dict[str, Any]]:
    """
    Geocodifica destino via Nominatim OSM com bias geográfico (viewbox + bounded=0)
    baseado na última localização salva em data/last_location.json.
    """
    clean_q = str(destination or "").strip()
    if not clean_q:
        return None

    encoded = urllib.parse.quote(clean_q)
    url = (
        f"https://nominatim.openstreetmap.org/search"
        f"?q={encoded}&format=json&limit=1&addressdetails=1&countrycodes=br"
    )

    try:
        loc_cache = load_last_location()
        if loc_cache and "latitude" in loc_cache and "longitude" in loc_cache:
            lat = float(loc_cache["latitude"])
            lon = float(loc_cache["longitude"])
            viewbox = f"{lon - 0.35:.6f},{lat + 0.35:.6f},{lon + 0.35:.6f},{lat - 0.35:.6f}"
            url += f"&viewbox={urllib.parse.quote(viewbox)}&bounded=0"
    except Exception:
        pass

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "SilvaAgent/1.0 (https://github.com/TGTiler/Silva)"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if isinstance(payload, list) and payload:
            top = payload[0]
            return {
                "latitude": float(top["lat"]),
                "longitude": float(top["lon"]),
                "display_name": top.get("display_name", clean_q),
                "query_url": url,
            }
    except Exception:
        pass
    return None


def _intent_succeeded(res: Any) -> bool:
    """Verifica se uma chamada _exec_android_intent foi bem-sucedida."""
    if not res or getattr(res, "returncode", 1) != 0:
        return False
    combined = (getattr(res, "stdout", "") or "") + (getattr(res, "stderr", "") or "")
    return not any(err in combined for err in ("Error:", "ActivityNotFound", "does not exist", "No activities found"))


# ---------------------------------------------------------------------------
# Super-app 99 (com.taxis99 / com.taxis99.food): helpers de UI Automator
# ---------------------------------------------------------------------------
_99_PROMO_HINTS = ("cupons", "cupom", "peca ja", "aproveite agora")
_99_CLOSE_LABELS = {"fechar", "close", "cancelar", "agora nao", "x", "dispensar"}
_99_RIDE_FIELD_HINT = "para onde vamos"
_99_RIDE_TAB_LABELS = {"corrida", "taxi", "corridas"}
_99_FOOD_TAB_LABELS = {"food", "99food", "comida"}


def _node_label(n: Dict[str, Any]) -> str:
    """Texto + content-desc normalizados (sem acentos, minúsculas) de um nó da UI."""
    return _normalize_text(f"{n.get('text', '')} {n.get('content_desc', '')}")


def _is_99_promo_visible(nodes: list) -> bool:
    """Detecta o modal promocional do 99 ('R$99 em cupons só pra você!', 'Peça já!', 'Aproveite agora')."""
    return any(any(h in _node_label(n) for h in _99_PROMO_HINTS) for n in nodes or [])


def _dismiss_99_promo(nodes: list, screen_w: int, screen_h: int) -> Optional[list]:
    """
    Fecha o modal de cupons do 99 tocando no 'X' (rótulo Fechar/Close/Cancelar/Agora não ou
    resource-id close/dismiss), nunca em 'Peça já!'. Fallback: coordenada segura (50%, 81%).
    Retorna a nova árvore de UI se algo foi dispensado; None se não havia modal.
    """
    if not _is_99_promo_visible(nodes):
        return None

    close_node = None
    for n in nodes:
        label = _node_label(n)
        if "peca ja" in label or "aproveite" in label:
            continue
        t_norm = _normalize_text(str(n.get("text") or ""))
        d_norm = _normalize_text(str(n.get("content_desc") or ""))
        res_id = str(n.get("resource_id") or "").lower()
        if t_norm in _99_CLOSE_LABELS or d_norm in _99_CLOSE_LABELS or any(k in res_id for k in ("close", "dismiss")):
            close_node = n
            break

    if close_node:
        tap_coords(int(close_node["cx"]), int(close_node["cy"]))
    else:
        tap_coords(int(screen_w * 0.50), int(screen_h * 0.81))
    time.sleep(1.0)
    return dump_ui_nodes()


def _has_99_ride_field(nodes: list) -> bool:
    """Indica se o campo 'Para onde vamos?' (aba Corrida) está visível."""
    return any(_99_RIDE_FIELD_HINT in _node_label(n) for n in nodes or [])


def _find_99_bottom_tab(nodes: list, labels: set, screen_h: int) -> Optional[Dict[str, Any]]:
    """Localiza uma aba da barra inferior do super-app 99 (cy > 88% da altura) pelo rótulo."""
    bottom_limit = int(screen_h * 0.88)
    for n in nodes or []:
        if int(n.get("cy") or 0) <= bottom_limit:
            continue
        t_norm = _normalize_text(str(n.get("text") or ""))
        d_norm = _normalize_text(str(n.get("content_desc") or ""))
        if t_norm in labels or d_norm in labels:
            return n
    return None


def _launch_99_package(target_tab: str) -> Optional[str]:
    """Abre com.taxis99.food (se instalado, para 'food') ou o super-app com.taxis99."""
    candidates = ["com.taxis99"]
    if target_tab == "food":
        ok_pm, out_pm = run_adb_shell(["pm", "list", "packages", "com.taxis99.food"], timeout=4.0)
        if ok_pm and "package:com.taxis99.food" in (out_pm or ""):
            candidates.insert(0, "com.taxis99.food")

    for pkg in candidates:
        if pkg in RESOLVED_APP_ACTIVITIES:
            cmd = f"am start -n {RESOLVED_APP_ACTIVITIES[pkg]}"
        else:
            cmd = f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1"
        if _intent_succeeded(_exec_android_intent(cmd)):
            return pkg
    return None


def _dismiss_99_location_accuracy_dialog(nodes: list) -> Optional[list]:
    """
    Caso A: Diálogo do sistema / Google Play Services ('Precisão de Local' / 'Localização do dispositivo').
    Prioriza o botão positivo 'Ativar' (à direita, maior cx), evitando 'Agora não'.
    """
    has_dialog = any(
        any(h in _node_label(n) for h in ("precisao de local", "localizacao do dispositivo"))
        for n in nodes or []
    )
    if not has_dialog:
        return None

    ativar_nodes = []
    for n in nodes or []:
        t_norm = _normalize_text(str(n.get("text") or ""))
        d_norm = _normalize_text(str(n.get("content_desc") or ""))
        if t_norm == "ativar" or d_norm == "ativar":
            ativar_nodes.append(n)

    if not ativar_nodes:
        return None

    ativar_nodes.sort(key=lambda item: int(item.get("cx") or 0), reverse=True)
    target = ativar_nodes[0]
    tap_coords(int(target["cx"]), int(target["cy"]))
    time.sleep(1.0)
    return dump_ui_nodes()


def _handle_99_location_blocker(nodes: list) -> Tuple[Optional[list], bool]:
    """
    Caso C: Tela bloqueadora 'Habilitar Serviços de Localização' na aba Corrida.
    1. Tenta ativar o GPS silenciosamente via ADB (set_location_state(True)).
    2. Se 'Inserir localização manualmente' estiver visível, toca nele para avançar direto à tela de endereço.
    3. Caso contrário, se 'Ativar nas Configurações' estiver visível, toca, aguarda e envia KEYCODE_BACK.
    Retorna (novos_nodes_ou_None, manual_location_mode).
    """
    has_blocker = any("habilitar servicos de localizacao" in _node_label(n) for n in nodes or [])
    if not has_blocker:
        return None, False

    try:
        set_location_state(True)
    except Exception:
        pass

    manual_btn = None
    settings_btn = None
    for n in nodes or []:
        label = _node_label(n)
        if "inserir localizacao manualmente" in label:
            manual_btn = n
            break
        if "ativar nas configuracoes" in label and settings_btn is None:
            settings_btn = n

    if manual_btn:
        tap_coords(int(manual_btn["cx"]), int(manual_btn["cy"]))
        time.sleep(1.0)
        return dump_ui_nodes(), True

    if settings_btn:
        tap_coords(int(settings_btn["cx"]), int(settings_btn["cy"]))
        time.sleep(1.0)
        try:
            set_location_state(True)
        except Exception:
            pass
        press_key(4)  # KEYCODE_BACK
        time.sleep(1.0)
        return dump_ui_nodes(), False

    return None, False


def _stabilize_99_ui(
    nodes: list,
    screen_w: int,
    screen_h: int,
    target_tab: str,
) -> Tuple[list, bool]:
    """
    Executa até 3 iterações de estabilização de UI (pausa de 1.0s após cada ação):
    - Caso A: Diálogo 'Precisão de Local' -> botão 'Ativar'
    - Caso B: Modal de cupons do 99 -> botão 'X' (ou 50%, 81%)
    - Caso C: Tela 'Habilitar Serviços de Localização' (aba Corrida) -> GPS + 'Inserir localização manualmente'
    """
    manual_location_mode = False
    for _ in range(3):
        next_nodes = _dismiss_99_location_accuracy_dialog(nodes)
        if next_nodes is not None:
            nodes = next_nodes
            continue

        next_nodes = _dismiss_99_promo(nodes, screen_w, screen_h)
        if next_nodes is not None:
            nodes = next_nodes
            continue

        if target_tab == "ride":
            blocker_nodes, is_manual = _handle_99_location_blocker(nodes)
            if blocker_nodes is not None:
                nodes = blocker_nodes
                if is_manual:
                    manual_location_mode = True
                    break
                continue

        break
    return nodes, manual_location_mode


def _prepare_99_app(target_tab: str) -> Dict[str, Any]:
    """
    Prepara o super-app 99 para automação (target_tab in ('ride', 'food')):
    1. Para corrida ('ride'), pré-ativa a localização silenciosamente via ADB.
    2. Abre o pacote correto e aguarda 3.5s (splash promocional inicial de ~3s); exige ADB e tela desbloqueada.
    3. Executa loop de estabilização de UI (até 3 tentativas): Precisão de Local, cupons e Serviços de Localização.
    4. Alterna para a aba inferior correta (Corrida x≈20% / Food x≈40%, y≈92%) e reestabiliza se necessário.
    Retorna {"ok", "package", "nodes", "screen_w", "screen_h", "manual_location_mode", "reason"}.
    """
    result: Dict[str, Any] = {
        "ok": False,
        "package": None,
        "nodes": [],
        "screen_w": 1080,
        "screen_h": 2400,
        "manual_location_mode": False,
        "reason": "",
    }
    if target_tab not in ("ride", "food"):
        result["reason"] = "invalid_tab"
        return result

    adb_ser = ensure_adb_connected()
    if not adb_ser:
        result["reason"] = "adb_disconnected"
        return result

    with _UI_LOCK:
        if target_tab == "ride":
            try:
                set_location_state(True)
            except Exception:
                pass

        pkg = _launch_99_package(target_tab)
        if not pkg:
            result["reason"] = "package_not_found"
            return result
        result["package"] = pkg

        time.sleep(3.5)
        unlocked, _ = is_screen_unlocked(serial=adb_ser)
        if not unlocked:
            result["reason"] = "screen_locked"
            return result

        nodes = dump_ui_nodes()
        screen_w, screen_h = get_screen_dimensions(nodes)
        nodes, manual_location_mode = _stabilize_99_ui(nodes, screen_w, screen_h, target_tab)

        # Alternância de abas só existe no super-app (com.taxis99).
        if pkg == "com.taxis99" and not manual_location_mode:
            ride_visible = _has_99_ride_field(nodes)
            tab_node = None
            fallback_xy = None
            if target_tab == "food" and ride_visible:
                tab_node = _find_99_bottom_tab(nodes, _99_FOOD_TAB_LABELS, screen_h)
                fallback_xy = (int(screen_w * 0.40), int(screen_h * 0.92))
            elif target_tab == "ride" and not ride_visible:
                tab_node = _find_99_bottom_tab(nodes, _99_RIDE_TAB_LABELS, screen_h)
                fallback_xy = (int(screen_w * 0.20), int(screen_h * 0.92))

            if fallback_xy:
                if tab_node:
                    tap_coords(int(tab_node["cx"]), int(tab_node["cy"]))
                else:
                    tap_coords(*fallback_xy)
                time.sleep(1.2)
                nodes = dump_ui_nodes()
                nodes, manual_location_mode = _stabilize_99_ui(nodes, screen_w, screen_h, target_tab)

        result.update({
            "ok": True,
            "nodes": nodes,
            "screen_w": screen_w,
            "screen_h": screen_h,
            "manual_location_mode": manual_location_mode,
        })
        return result


def _find_99_food_search_node(nodes: list, screen_w: int, screen_h: int) -> Optional[Dict[str, Any]]:
    """Barra de busca da aba Food do 99: faixa 11%–20% da altura, ignorando o rodapé (y > 85%)."""
    y_min, y_max = int(screen_h * 0.11), int(screen_h * 0.20)
    candidates = []
    for n in nodes or []:
        cy = int(n.get("cy") or 0)
        if not (y_min <= cy <= y_max):
            continue
        cls_name = str(n.get("class_name") or "").lower()
        res_id = str(n.get("resource_id") or "").lower()
        label = _node_label(n)
        is_wide = (int(n.get("x2") or 0) - int(n.get("x1") or 0)) >= int(screen_w * 0.35)
        has_res = any(k in res_id for k in ("search", "input", "query", "busca"))
        has_hint = any(h in label for h in ("buscar", "pesquisar", "o que voce", "restaurante", "busque"))
        clickable = bool(n.get("clickable"))
        if "edittext" in cls_name:
            candidates.append((100, n))
        elif clickable and has_res:
            candidates.append((90, n))
        elif clickable and has_hint:
            candidates.append((85, n))
        elif clickable and is_wide:
            candidates.append((70, n))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _automate_99_food_search_via_ui(clean_query: str) -> Optional[str]:
    """Busca `clean_query` na aba Food do 99. Retorna o pacote usado em caso de sucesso, ou None."""
    with _UI_LOCK:
        prep = _prepare_99_app("food")
        if not prep["ok"]:
            return None
        nodes, screen_w, screen_h = prep["nodes"], prep["screen_w"], prep["screen_h"]

        search_node = _find_99_food_search_node(nodes, screen_w, screen_h)
        if search_node:
            tap_coords(int(search_node["cx"]), int(search_node["cy"]))
        else:
            tap_coords(int(screen_w * 0.50), int(screen_h * 0.145))
        time.sleep(0.8)

        ok_type, _ = type_text_unicode(clean_query)
        if not ok_type:
            return None
        time.sleep(0.3)
        press_key(66)
        return prep["package"]


def _pick_99_destination_suggestion(nodes: list, destination: str, screen_h: int) -> Optional[Dict[str, Any]]:
    """Primeira sugestão de endereço que contém todos os termos significativos do destino."""
    tokens = [t for t in _normalize_text(destination).split() if len(t) > 2]
    if not tokens:
        return None
    bottom_limit = int(screen_h * 0.85)
    for n in sorted(nodes or [], key=lambda item: int(item.get("cy") or 0)):
        if "edittext" in str(n.get("class_name") or "").lower():
            continue
        if int(n.get("cy") or 0) > bottom_limit or not str(n.get("text") or "").strip():
            continue
        label = _node_label(n)
        if all(t in label for t in tokens):
            return n
    return None


def _automate_99_ride_via_ui(destination: str) -> Optional[Dict[str, Any]]:
    """
    Preenche o destino em 'Para onde vamos?' (ou após 'Inserir localização manualmente') no 99 (aba Corrida).
    Retorna {"package", "suggestion_selected"} em caso de sucesso, ou None.
    """
    with _UI_LOCK:
        prep = _prepare_99_app("ride")
        if not prep["ok"]:
            return None
        nodes, screen_w, screen_h = prep["nodes"], prep["screen_w"], prep["screen_h"]

        if prep.get("manual_location_mode"):
            edit_node = next(
                (n for n in nodes if "edittext" in str(n.get("class_name") or "").lower()),
                None,
            )
            if edit_node:
                tap_coords(int(edit_node["cx"]), int(edit_node["cy"]))
                time.sleep(0.3)
        else:
            y_min, y_max = int(screen_h * 0.30), int(screen_h * 0.45)
            field = None
            for n in nodes:
                if _99_RIDE_FIELD_HINT in _node_label(n) and y_min <= int(n.get("cy") or 0) <= y_max:
                    field = n
                    break
            if field:
                tap_coords(int(field["cx"]), int(field["cy"]))
            else:
                tap_coords(int(screen_w * 0.50), int(screen_h * 0.36))
            time.sleep(1.0)

        ok_type, _ = type_text_unicode(destination)
        if not ok_type:
            return None
        time.sleep(1.2)

        suggestion = _pick_99_destination_suggestion(dump_ui_nodes(), destination, screen_h)
        if suggestion:
            tap_coords(int(suggestion["cx"]), int(suggestion["cy"]))
        return {"package": prep["package"], "suggestion_selected": bool(suggestion)}


def request_ride(destination: str, app: str = "uber", service: str = "") -> Dict[str, Any]:
    """Abre o aplicativo de transporte (Uber ou 99) com resolução de apelidos, geocodificação e fallback em 3 camadas."""
    clean_dest = _clean_ride_destination(destination)
    if not clean_dest:
        return {"status": "error", "message": "Destino da corrida não informado."}

    # 1. Integração com Memória Local (memory.db / FTS5): apelidos comuns ou destinos curtos (< 3 palavras)
    resolved_destination = clean_dest
    found_in_mem = False
    common_aliases = {"casa", "trabalho", "escola", "faculdade", "academia", "igreja", "mercado"}
    norm_dest = _normalize_text(clean_dest)
    should_check_memory = norm_dest in common_aliases or len(norm_dest.split()) < 3

    mem = _load_memory()
    if mem:
        query_tokens = set(norm_dest.split())
        best_match = None
        best_score = 0
        for k, v_data in mem.items():
            val = v_data.get("value", "") if isinstance(v_data, dict) else str(v_data)
            norm_k = _normalize_text(k)
            score = 0
            if norm_dest == norm_k or f"endereco {norm_dest}" == norm_k:
                score += 10
            elif norm_dest in norm_k:
                score += 6
            elif norm_k in norm_dest:
                score += 5

            common = query_tokens.intersection(set(norm_k.split()))
            if common:
                score += len(common) * 2

            if score > best_score and score >= 4:
                best_score = score
                best_match = val

        if best_match:
            resolved_destination = best_match
            found_in_mem = True

    if not found_in_mem and should_check_memory:
        for mem_query in (f"endereco {clean_dest}", clean_dest):
            try:
                rec = recall_note(mem_query)
                if rec.get("status") == "ok":
                    notes = rec.get("data", {}).get("notes") or []
                    if notes and isinstance(notes[0], dict) and notes[0].get("value"):
                        resolved_destination = str(notes[0]["value"]).strip()
                        found_in_mem = True
                        break
            except Exception:
                pass

    alias_prefix = f"Usando endereço salvo para '{clean_dest}': {resolved_destination}. " if found_in_mem else ""
    app_target = str(service or app or "uber").strip().lower()
    encoded_dest = urllib.parse.quote(resolved_destination)

    if app_target == "uber":
        geo = None if SIMULATE_HARDWARE else _geocode_destination(resolved_destination)
        geo_qs = f"&dropoff[latitude]={geo['latitude']}&dropoff[longitude]={geo['longitude']}" if geo else ""
        uber_uri = f"uber://?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_dest}{geo_qs}"
        web_url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_dest}{geo_qs}"

        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"{alias_prefix}Abrindo UBER com destino para '{resolved_destination}'. Basta confirmar a corrida na tela. [Simulado]",
                "data": {"destination": resolved_destination, "app": "uber", "url": uber_uri, "web_url": web_url}
            }

        # Camada 1: Deep Link nativo Uber
        res1 = _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{uber_uri}"')
        if _intent_succeeded(res1):
            return {
                "status": "ok",
                "message": f"{alias_prefix}Abrindo UBER com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
                "data": {"destination": resolved_destination, "app": "uber", "url": uber_uri, "geocoded": geo, "method": "deep_link"}
            }

        # Camada 2: Package Launch (com.ubercab)
        res2 = _exec_android_intent("monkey -p com.ubercab -c android.intent.category.LAUNCHER 1")
        if _intent_succeeded(res2):
            set_clipboard(resolved_destination)
            return {
                "status": "ok",
                "message": f"{alias_prefix}Abrindo UBER com destino para '{resolved_destination}' (endereço copiado para a área de transferência).",
                "data": {"destination": resolved_destination, "app": "uber", "package": "com.ubercab", "geocoded": geo, "method": "package_fallback"}
            }

        # Camada 3: Fallback Web Mobile
        _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{web_url}"')
        return {
            "status": "ok",
            "message": f"{alias_prefix}Abrindo UBER Web com destino para '{resolved_destination}'.",
            "data": {"destination": resolved_destination, "app": "uber", "url": web_url, "geocoded": geo, "method": "web_fallback"}
        }

    elif app_target in ("99", "99pop"):
        geo = None if SIMULATE_HARDWARE else _geocode_destination(resolved_destination)
        geo_qs_99 = f"&dropoff_lat={geo['latitude']}&dropoff_lng={geo['longitude']}" if geo else ""
        uri_99 = f"taxis99://call?dropoff_title={encoded_dest}{geo_qs_99}"
        set_clipboard(resolved_destination)

        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"{alias_prefix}Abrindo 99 com destino para '{resolved_destination}'. Basta confirmar a corrida na tela. [Simulado]",
                "data": {"destination": resolved_destination, "app": "99", "url": uri_99}
            }

        # Camada 0: Automação real via ADB + UI Automator ('Para onde vamos?')
        ui_ride = _automate_99_ride_via_ui(resolved_destination)
        if ui_ride:
            tail = (
                "Sugestão de endereço selecionada; basta confirmar a corrida na tela."
                if ui_ride["suggestion_selected"]
                else "Escolha o endereço na lista de sugestões e confirme a corrida."
            )
            return {
                "status": "ok",
                "message": f"{alias_prefix}Destino '{resolved_destination}' preenchido no 99. {tail}",
                "data": {
                    "destination": resolved_destination,
                    "app": "99",
                    "package": ui_ride["package"],
                    "suggestion_selected": ui_ride["suggestion_selected"],
                    "method": "ui_automator_destination",
                }
            }

        # Camada 1: Deep Link nativo 99
        res1 = _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{uri_99}"')
        if _intent_succeeded(res1):
            return {
                "status": "ok",
                "message": f"{alias_prefix}Abrindo 99 com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
                "data": {"destination": resolved_destination, "app": "99", "url": uri_99, "geocoded": geo, "method": "deep_link"}
            }

        # Camada 2: Package Launch (com.taxis99 / com.xiaojukeji.didi.brazil.passenger)
        for pkg in ("com.taxis99", "com.xiaojukeji.didi.brazil.passenger"):
            cmd = f"am start -n {RESOLVED_APP_ACTIVITIES[pkg]}" if pkg in RESOLVED_APP_ACTIVITIES else f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1"
            res_pkg = _exec_android_intent(cmd)
            if _intent_succeeded(res_pkg):
                return {
                    "status": "ok",
                    "message": f"{alias_prefix}Abrindo 99 com destino para '{resolved_destination}' (endereço copiado para a área de transferência).",
                    "data": {"destination": resolved_destination, "app": "99", "package": pkg, "geocoded": geo, "method": "package_fallback"}
                }

        # Camada 3: Play Store / Web fallback
        _exec_android_intent('am start -a android.intent.action.VIEW -d "market://details?id=com.taxis99"')
        return {
            "status": "ok",
            "message": f"{alias_prefix}Abrindo página da 99 na Play Store para corrida até '{resolved_destination}'.",
            "data": {"destination": resolved_destination, "app": "99", "method": "store_fallback"}
        }
    else:
        url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_dest}"
        if not SIMULATE_HARDWARE:
            _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"{alias_prefix}Abrindo {app_target.upper()} com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
            "data": {"destination": resolved_destination, "app": app_target, "url": url}
        }


def _clean_food_query(raw_query: str) -> str:
    """
    Remove prefixos de comando e sufixos de aplicativo/cortesia de uma busca de comida.
    Exemplos:
      "peça um hamburguer no ifood" -> "hamburguer"
      "silva quero pedir uma pizza de calabresa no ifood pfv" -> "pizza de calabresa"
      "busca acai na 99" -> "acai"
    """
    if not raw_query:
        return ""
    text = str(raw_query).strip()

    # 1. Sufixos de app e cortesia no final (repetidos até limpar)
    suffix_pat = r"(?i)\s+(?:no\s+ifood|pelo\s+ifood|na\s+99\s*food|no\s+99\s*food|pela\s+99\s*food|pelo\s+99\s*food|na\s+99|no\s+99|pela\s+99|pelo\s+99|pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    # 2. Prefixos de comando no início da frase (repetidos até limpar)
    prefix_patterns = [
        r"(?i)^(?:silva|ei|oi)\b[,\s]*",
        r"(?i)^(?:t[oô]\s+com\s+fome|estou\s+com\s+fome|com\s+fome)\b[,\s]*",
        r"(?i)^(?:abre\s+o\s+ifood\s+e\s+pede|abre\s+o\s+ifood\s+e\s+peça|abre\s+o\s+ifood\s+e\s+peca|abre\s+o\s+ifood\s+e\s+pedir)\b\s*",
        r"(?i)^(?:abre\s+o\s+99\s+e\s+pede|abre\s+a\s+99\s+e\s+pede)\b\s*",
        r"(?i)^(?:quero\s+pedir|quero|gostaria\s+de\s+pedir|gostaria\s+de|me\s+vê|me\s+ve)\b\s*",
        r"(?i)^(?:peça|peca|pede|pedir|compra|comprar|compre|busca|busque|buscar|procura|procure|procurar|acha|achar|pesquisa|pesquisar)\b\s*",
        r"(?i)^(?:no\s+ifood|pelo\s+ifood|na\s+99\s*food|no\s+99\s*food|pela\s+99\s*food|pelo\s+99\s*food|na\s+99|no\s+99|pela\s+99|pelo\s+99)\b\s*",
        r"(?i)^(?:delivery\s+de|delivery)\b\s*",
        r"(?i)^(?:um|uma|uns|umas)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
        r"(?i)^(?:de)\b\s*",
    ]

    for _ in range(10):
        prev = text
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        for pat in prefix_patterns:
            text = re.sub(pat, '', text).strip()
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        if text == prev:
            break

    text = re.sub(suffix_pat, "", text).strip()
    text = re.sub(r'[?!.,;:\"`\'\s]+$', '', text).strip()
    return text.strip()


def _dismiss_promo_modal(nodes: list) -> Optional[list]:
    """Dispensa modais promocionais/splash no iFood ('Fechar', 'Agora não', 'Pular', 'Continuar', 'Entendi')."""
    modal_labels = {"fechar", "agora nao", "pular", "continuar", "entendi", "close", "dismiss"}
    for n in nodes:
        t_norm = _normalize_text(str(n.get("text") or ""))
        d_norm = _normalize_text(str(n.get("content_desc") or ""))
        if t_norm in modal_labels or d_norm in modal_labels:
            tap_coords(int(n["cx"]), int(n["cy"]))
            time.sleep(1.0)
            return dump_ui_nodes()
    return None


def _find_food_search_node(
    nodes: list,
    screen_w: int = 1080,
    screen_h: int = 2400,
    prefer_edit_text: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Localiza a barra superior de pesquisa no app de delivery via UI Automator:
    - Ignora a barra de navegação inferior (cy > 85% da altura).
    - Prioriza EditText ou nós clicáveis na faixa superior (cy < 22% da altura)
      com resource-id de busca ou largura de barra de pesquisa (mesmo com placeholders rotativos).
    """
    search_hints = ("o que vai pedir", "item ou loja", "buscar", "pesquisar", "procurar", "mercado perto de mim", "todo o ifood")
    top_limit = int(screen_h * 0.22)
    bottom_limit = int(screen_h * 0.85)
    candidates = []

    for n in nodes:
        cy = int(n.get("cy") or 0)
        if cy > bottom_limit:
            continue

        cls_name = str(n.get("class_name") or n.get("class") or "").lower()
        res_id = str(n.get("resource_id") or "").lower()
        combined = _normalize_text(f"{n.get('text', '')} {n.get('content_desc', '')}")
        is_edit = "edittext" in cls_name
        is_clickable = bool(n.get("clickable", False))
        in_top = cy <= top_limit
        has_res_search = any(k in res_id for k in ("search", "input", "query", "busca"))
        has_hint = any(h in combined for h in search_hints)
        x1 = int(n.get("x1") or 0)
        x2 = int(n.get("x2") or 0)
        is_wide_bar = (x2 - x1) >= int(screen_w * 0.35)

        if prefer_edit_text and is_edit:
            candidates.append((110 if in_top else 90, n))
            continue

        if is_edit and in_top:
            candidates.append((100, n))
        elif is_clickable and in_top and has_res_search:
            candidates.append((90, n))
        elif is_clickable and in_top and has_hint:
            candidates.append((85, n))
        elif is_clickable and in_top and is_wide_bar:
            candidates.append((70, n))
        elif in_top and (has_res_search or has_hint):
            candidates.append((60, n))

    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _automate_food_search_via_ui(clean_query: str) -> bool:
    """
    Camada 2 ativa (ADB + UI Automator):
    1. Aguarda estabilização (3.0s) e dispensa modais promocionais.
    2. Localiza a barra superior (y < 22%, ignorando rodapé y > 85%) ou usa coordenada segura (52%, 7.5%).
    3. Toca na barra, aguarda foco no EditText (0.8s), digita com acentos PT-BR e envia Enter (66).
    """
    adb_ser = ensure_adb_connected()
    if not adb_ser:
        return False

    unlocked, _ = is_screen_unlocked(serial=adb_ser)
    if not unlocked:
        return False

    with _UI_LOCK:
        time.sleep(3.0)
        nodes = dump_ui_nodes()
        if nodes:
            dismissed_nodes = _dismiss_promo_modal(nodes)
            if dismissed_nodes is not None:
                nodes = dismissed_nodes

        screen_w, screen_h = get_screen_dimensions(nodes)
        search_node = _find_food_search_node(nodes, screen_w=screen_w, screen_h=screen_h, prefer_edit_text=False)

        if search_node:
            tap_coords(int(search_node["cx"]), int(search_node["cy"]))
            tapped_cls = str(search_node.get("class_name") or search_node.get("class") or "").lower()
        else:
            # Prioridade 2: Fallback por coordenada segura da barra superior (52% x, 7.5% y)
            tap_coords(int(screen_w * 0.52), int(screen_h * 0.075))
            tapped_cls = ""

        time.sleep(0.8)

        if "edittext" not in tapped_cls:
            nodes_after = dump_ui_nodes()
            edit_node = _find_food_search_node(nodes_after, screen_w=screen_w, screen_h=screen_h, prefer_edit_text=True)
            if edit_node:
                tap_coords(int(edit_node["cx"]), int(edit_node["cy"]))
                time.sleep(0.3)

        ok_type, _ = type_text_unicode(clean_query)
        if not ok_type:
            return False
        time.sleep(0.3)
        press_key(66)
        return True


def order_food(query: str, app: str = "ifood") -> Dict[str, Any]:
    """Abre o aplicativo de delivery (iFood ou 99Food) buscando o prato via Intent + UI Automator."""
    clean_query = _clean_food_query(query)
    if not clean_query or clean_query.lower() in ("algo", "alguma coisa", "qualquer coisa"):
        clean_query = "comida"

    app_target = str(app).strip().lower() if app else "ifood"
    encoded_query = urllib.parse.quote_plus(clean_query)
    encoded_path_query = urllib.parse.quote(clean_query)

    if app_target == "ifood":
        set_clipboard(clean_query)
        url_deep = f"ifood://search?q={encoded_query}"
        url_app_view = f"https://www.ifood.com.br/busca?q={encoded_path_query}"
        url_web = f"https://www.ifood.com.br/busca?q={encoded_query}&tab=0"

        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Buscando '{clean_query}' no iFood (termo também copiado para a área de transferência caso precise colar na lupa).\n{url_web}",
                "data": {"query": clean_query, "app": "ifood", "url": url_deep, "web_url": url_web}
            }

        # Camada 1: Deep Link de busca interno / Intent direto no pacote do iFood
        res1 = _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url_deep}"')
        if _intent_succeeded(res1):
            ui_ok = _automate_food_search_via_ui(clean_query)
            return {
                "status": "ok",
                "message": f"Buscando '{clean_query}' no iFood (termo também copiado para a área de transferência).",
                "data": {
                    "query": clean_query,
                    "app": "ifood",
                    "url": url_deep,
                    "method": "ui_automator_search" if ui_ok else "deep_link",
                }
            }

        res_pkg_view = _exec_android_intent(
            f'am start -a android.intent.action.VIEW -d "{url_app_view}" -p br.com.brainweb.ifood'
        )
        if _intent_succeeded(res_pkg_view):
            ui_ok = _automate_food_search_via_ui(clean_query)
            return {
                "status": "ok",
                "message": f"Buscando '{clean_query}' no iFood.",
                "data": {
                    "query": clean_query,
                    "app": "ifood",
                    "url": url_app_view,
                    "method": "ui_automator_search" if ui_ok else "intent_package",
                }
            }

        # Camada 2: Abrir App Principal (br.com.brainweb.ifood) + busca ativa via UI Automator
        res2 = _exec_android_intent("monkey -p br.com.brainweb.ifood -c android.intent.category.LAUNCHER 1")
        if _intent_succeeded(res2):
            ui_ok = _automate_food_search_via_ui(clean_query)
            return {
                "status": "ok",
                "message": (
                    f"Buscando '{clean_query}' no iFood."
                    if ui_ok
                    else f"Abrindo iFood para buscar '{clean_query}' (termo copiado para a área de transferência)."
                ),
                "data": {
                    "query": clean_query,
                    "app": "ifood",
                    "package": "br.com.brainweb.ifood",
                    "method": "ui_automator_search" if ui_ok else "package_fallback",
                }
            }

        # Camada 3: Fallback Web Search
        _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url_web}"')
        return {
            "status": "ok",
            "message": f"Buscando '{clean_query}' no iFood Web.\n{url_web}",
            "data": {"query": clean_query, "app": "ifood", "url": url_web, "method": "web_fallback"}
        }

    elif app_target in ("99", "99food", "99 food"):
        app_norm = "99food"
        set_clipboard(clean_query)
        url_deep = f"taxis99://food/search?q={encoded_query}"

        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Abrindo 99 (aba Delivery) para buscar '{clean_query}' (termo copiado para a área de transferência). [Simulado]",
                "data": {"query": clean_query, "app": app_norm, "url": url_deep}
            }

        # 0. Automação real via ADB + UI Automator (pop-up de cupons, aba Food e barra de busca)
        ui_pkg = _automate_99_food_search_via_ui(clean_query)
        if ui_pkg:
            return {
                "status": "ok",
                "message": f"Buscando '{clean_query}' no 99Food.",
                "data": {"query": clean_query, "app": app_norm, "package": ui_pkg, "method": "ui_automator_search"}
            }

        # 1. Tentativa via Deep Link nativo do super-app da 99
        cmd_deep = f'am start -a android.intent.action.VIEW -d "{url_deep}"'
        res1 = _exec_android_intent(cmd_deep)
        if _intent_succeeded(res1):
            return {
                "status": "ok",
                "message": f"Abrindo 99 (aba Delivery) para buscar '{clean_query}' (termo copiado para a área de transferência).",
                "data": {"query": clean_query, "app": app_norm, "url": url_deep, "method": "deep_link"}
            }

        # 2. Fallback: abrir pacote principal do super-app da 99 / 99Food
        for pkg in ("com.taxis99", "com.taxis99.food", "com.xiaojukeji.didi.brazil.passenger", "com.didi.brazil.food"):
            if pkg in RESOLVED_APP_ACTIVITIES:
                res_pkg = _exec_android_intent(f"am start -n {RESOLVED_APP_ACTIVITIES[pkg]}")
            else:
                res_pkg = _exec_android_intent(f"monkey -p {pkg} -c android.intent.category.LAUNCHER 1")
            if _intent_succeeded(res_pkg):
                return {
                    "status": "ok",
                    "message": f"Abrindo 99 (aba Delivery) para buscar '{clean_query}' (termo copiado para a área de transferência).",
                    "data": {"query": clean_query, "app": app_norm, "package": pkg, "method": "package_fallback"}
                }

        open_app("99")
        return {
            "status": "ok",
            "message": f"Abrindo 99 (aba Delivery) para buscar '{clean_query}' (termo copiado para a área de transferência).",
            "data": {"query": clean_query, "app": app_norm, "method": "open_app_fallback"}
        }
    else:
        set_clipboard(clean_query)
        url_web = f"https://www.ifood.com.br/busca?q={encoded_query}&tab=0"
        if not SIMULATE_HARDWARE:
            _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url_web}"')
        return {
            "status": "ok",
            "message": f"Buscando '{clean_query}' no {app_target.capitalize()}.",
            "data": {"query": clean_query, "app": app_target, "url": url_web}
        }


def _clean_install_app_name(raw_name: str) -> str:
    """Limpa o nome do aplicativo removendo artigos, pronomes e termos de loja/cortesia."""
    if not raw_name:
        return ""
    text = str(raw_name).strip()

    suffix_pat = r"(?i)\s+(?:no\s+google\s+play|na\s+google\s+play|no\s+play\s*store|na\s+play\s*store|no\s+playstore|na\s+playstore|pelo\s+google\s+play|pela\s+play\s*store|pelo\s+play\s*store|google\s+play|play\s*store|playstore|pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    prefix_patterns = [
        r"(?i)^(?:silva|ei|oi)\b\s*",
        r"(?i)^(?:abre\s+a\s+play\s*store\s+e\s+(?:baixa|instala|procura|pesquisa|busca))\b\s*",
        r"(?i)^(?:abre\s+o\s+google\s+play\s+e\s+(?:baixa|instala|procura|pesquisa|busca))\b\s*",
        r"(?i)^(?:instalar|instala|instale|baixar|baixa|baixe|download\s+do|download\s+de|download)\b\s*",
        r"(?i)^(?:pesquisar|pesquisa|pesquise|buscar|busca|busque|procurar|procura|procure)\b\s*",
        r"(?i)^(?:o\s+aplicativo|aplicativo|o\s+app|app|o\s+jogo|jogo)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
        r"(?i)^(?:do|da|dos|das|de)\b\s*",
    ]

    for _ in range(10):
        prev = text
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        for pat in prefix_patterns:
            text = re.sub(pat, '', text).strip()
        text = re.sub(r'^[?!.,;:\"`\'\s]+', '', text).strip()
        if text == prev:
            break

    text = re.sub(suffix_pat, "", text).strip()
    text = re.sub(r'[?!.,;:\"`\'\s]+$', '', text).strip()
    return text.strip()


def install_app(app_name: str) -> Dict[str, Any]:
    """Abre a Google Play Store diretamente na página de instalação ou na pesquisa do aplicativo."""
    clean_name = _clean_install_app_name(app_name)
    if not clean_name:
        return {"status": "error", "message": "Nome do aplicativo não informado para instalação."}

    lookup_key = clean_name.lower().strip()
    pkg = APP_PACKAGES.get(lookup_key)

    if pkg:
        url = f"market://details?id={pkg}"
        cmd = f'am start -a android.intent.action.VIEW -d "{url}" -p com.android.vending'
        if not SIMULATE_HARDWARE:
            res = _exec_android_intent(cmd)
            if res.returncode != 0 or "ActivityNotFound" in res.stderr:
                _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"Abrindo a página de instalação de '{clean_name}' na Play Store.",
            "data": {"app_name": clean_name, "package": pkg, "url": url}
        }
    else:
        encoded_name = urllib.parse.quote_plus(clean_name)
        url = f"market://search?q={encoded_name}"
        cmd = f'am start -a android.intent.action.VIEW -d "{url}" -p com.android.vending'
        if not SIMULATE_HARDWARE:
            res = _exec_android_intent(cmd)
            if res.returncode != 0 or "ActivityNotFound" in res.stderr:
                _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"Pesquisando '{clean_name}' na Play Store.",
            "data": {"app_name": clean_name, "query": clean_name, "url": url}
        }



def list_capabilities() -> Dict[str, Any]:
    """Retorna um guia completo e organizado de todas as funções e comandos do Silva."""
    text = (
        "🤖 **Comandos e Funções do Silva**\n\n"
        "📱 **Sistema & Tela:**\n"
        "• Bateria: \"quanto tenho de bateria?\"\n"
        "• Lanterna: \"liga a lanterna\" ou \"desliga o flash\"\n"
        "• Não Perturbe: \"ativa o modo silencioso\"\n"
        "• Volume: \"coloca o volume em 70%\"\n"
        "• Brilho: \"ajusta o brilho para 50%\"\n"
        "• Vibração: \"vibra por 2 segundos\"\n"
        "• Print da Tela: \"tira um print da tela\"\n"
        "• Área de Transferência: \"copia o código 1234\" ou \"o que copiei?\"\n\n"
        "📸 **Câmera & Mídia:**\n"
        "• Foto: \"tira uma foto\" ou \"tira uma selfie\"\n"
        "• Vídeo: \"grava um vídeo de 15 segundos\"\n"
        "• Mídia: \"pausa a música\", \"continua\", \"próxima música\" ou \"música anterior\"\n\n"
        "📞 **Chamadas & Mensagens:**\n"
        "• Chamadas: \"liga para Mãe\" ou \"disca 11987654321\"\n"
        "• SMS: \"manda um sms para João dizendo que estou chegando\" ou \"ler últimos sms\"\n"
        "• Notificações: \"ler notificações do WhatsApp\" ou \"quais as notificações?\"\n\n"
        "🚀 **Apps & Busca:**\n"
        "• Abrir Apps: \"abre o YouTube\" ou \"inicia o WhatsApp\"\n"
        "• Instalar Apps: \"baixa o Spotify na Play Store\" ou \"instala o Nubank\"\n"
        "• Google: \"pesquisa no Google receita de bolo de cenoura\"\n\n"
        "⏰ **Agenda, Alarmes & Tempo:**\n"
        "• Alarmes: \"coloca um alarme para 07:00\" ou \"cancela o alarme das 07:00\"\n"
        "• Compromissos: \"agenda reunião amanhã às 14:00\"\n"
        "• Timer: \"inicia um timer de 10 minutos\"\n\n"
        "📍 **Localização & Clima:**\n"
        "• Localização: \"onde eu estou?\" ou \"última localização registrada\"\n"
        "• GPS: \"ativa o GPS\" ou \"desliga a localização\"\n"
        "• Clima: \"previsão do tempo hoje em Recife\" ou \"vai chover no sábado?\"\n\n"
        "🚗 **Mobilidade & Delivery:**\n"
        "• Transporte: \"pede um Uber para o Shopping Recife\" ou \"chama um 99\"\n"
        "• Comida: \"peça uma pizza no iFood\" ou \"busca açaí no 99 food\"\n\n"
        "🧠 **Memória & Utilidades:**\n"
        "• Memória Offline: \"lembra que guardei a chave na gaveta\" ou \"onde guardei a chave?\"\n"
        "• Wi-Fi: \"quais wifis tem por perto?\" ou \"escanear redes wifi\"\n"
        "• Calculadora: \"quanto é 350 * 12?\" ou \"raiz quadrada de 144\"\n"
        "• Humor: \"conta uma piada\"\n"
        "• Multi-Ações: \"liga a lanterna e ajusta o volume em 80%\""
    )
    return {
        "status": "ok",
        "message": text,
        "data": {
            "categories": [
                "system", "media", "telephony", "apps", "time", "location", "transport", "utilities", "network"
            ]
        }
    }


_WEEKDAYS_PTBR = [
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
]
_MONTHS_PTBR = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


def get_datetime() -> Dict[str, Any]:
    """Retorna data completa, dia da semana, hora exata e período do dia em PT-BR."""
    now = datetime.now()
    weekday = _WEEKDAYS_PTBR[now.weekday()]
    month_name = _MONTHS_PTBR[now.month]
    date_str = f"{now.day:02d} de {month_name} de {now.year}"
    time_str = now.strftime("%H:%M:%S")
    hour = now.hour

    if hour < 6:
        period = "madrugada"
    elif hour < 12:
        period = "manhã"
    elif hour < 18:
        period = "tarde"
    else:
        period = "noite"

    return {
        "status": "ok",
        "message": f"Silva: Hoje é {weekday}, {date_str}. Agora são {time_str} ({period}).",
        "data": {
            "date": now.strftime("%Y-%m-%d"),
            "date_br": now.strftime("%d/%m/%Y"),
            "weekday": weekday,
            "time": time_str,
            "period": period,
            "iso": now.isoformat(timespec="seconds"),
        },
    }


def read_screen() -> Dict[str, Any]:
    """Extrai e resume o conteúdo legível da tela atual via uiautomator + ADB."""
    adb_ser = ensure_adb_connected()
    if not adb_ser:
        return {
            "status": "error",
            "message": "Não foi possível ler a tela porque o ADB local está offline. Conecte a depuração por Wi-Fi para habilitar a leitura de tela.",
            "data": {"texts": [], "count": 0},
        }

    unlocked, lock_msg = is_screen_unlocked(serial=adb_ser)
    if not unlocked:
        return {"status": "error", "message": lock_msg, "data": {"texts": [], "count": 0, "locked": True}}

    nodes = dump_ui_nodes()
    filtered = []
    last_added = None
    for n in nodes:
        raw_txt = (n.get("text") or "").strip()
        raw_desc = (n.get("content_desc") or "").strip()
        for candidate in (raw_txt, raw_desc):
            if not candidate or len(candidate) <= 1:
                continue
            # Filtra ruídos puramente técnicos (resource-ids ou separadores)
            if re.match(r"^[a-z0-9_]+\.[a-z0-9_.]+:[a-z0-9_/]+$", candidate, re.IGNORECASE):
                continue
            if candidate == last_added:
                continue
            filtered.append(candidate)
            last_added = candidate

    if not filtered:
        return {
            "status": "ok",
            "message": "A tela atual parece estar vazia ou bloqueada (nenhum texto legível encontrado).",
            "data": {"texts": [], "count": 0},
        }

    joined = " | ".join(filtered[:30])
    if len(joined) > 520:
        joined = joined[:517].rstrip() + "..."
    return {
        "status": "ok",
        "message": f"Conteúdo visível na tela: {joined}",
        "data": {"texts": filtered[:30], "count": len(filtered)},
    }


def _dispatch_intent(args: list, adb_serial: Optional[str]) -> bool:
    if adb_serial:
        ok, out = run_adb_shell(args, timeout=6.0)
        if ok and "Error:" not in (out or ""):
            return True
    res = _exec_android_intent(shlex.join(args))
    return res.returncode == 0 and "Error:" not in (res.stderr or "")


def navigate_to(destination: str, app: str = "maps") -> Dict[str, Any]:
    """Inicia navegação GPS curva a curva diretamente no Google Maps ou Waze."""
    clean_dest = str(destination or "").strip()
    if not clean_dest:
        return {"status": "error", "message": "Informe o destino para iniciar a navegação GPS."}

    raw_app = str(app or "maps").strip().lower()
    norm_app = "waze" if "waze" in raw_app else "maps"
    app_label = "Waze" if norm_app == "waze" else "Google Maps"
    if SIMULATE_HARDWARE:
        return {
            "status": "ok",
            "message": f"Silva: Navegação iniciada no {app_label} para '{clean_dest}'. [Simulado]",
            "data": {"destination": clean_dest, "app": norm_app, "simulated": True},
        }
    adb_serial = ensure_adb_connected()

    enc_dest = urllib.parse.quote(clean_dest)
    launched = False
    if norm_app == "waze":
        waze_url = f"https://waze.com/ul?q={enc_dest}&navigate=yes"
        launched = _dispatch_intent(
            ["am", "start", "-a", "android.intent.action.VIEW", "-d", waze_url, "-p", "com.waze"],
            adb_serial,
        ) or _dispatch_intent(
            ["am", "start", "-a", "android.intent.action.VIEW", "-d", waze_url],
            adb_serial,
        )
    else:
        nav_uri = f"google.navigation:q={enc_dest}&mode=d"
        geo_uri = f"geo:0,0?q={enc_dest}"
        launched = _dispatch_intent(
            ["am", "start", "-a", "android.intent.action.VIEW", "-d", nav_uri, "-p", "com.google.android.apps.maps"],
            adb_serial,
        ) or _dispatch_intent(
            ["am", "start", "-a", "android.intent.action.VIEW", "-d", geo_uri],
            adb_serial,
        )

    if not launched:
        return {
            "status": "error",
            "message": f"Não foi possível iniciar a navegação no {app_label} para '{clean_dest}'.",
            "data": {"destination": clean_dest, "app": norm_app},
        }

    return {
        "status": "ok",
        "message": f"Silva: Navegação iniciada no {app_label} para '{clean_dest}'.",
        "data": {"destination": clean_dest, "app": norm_app},
    }


# Dicionário de registro de funções disponíveis para o parser
