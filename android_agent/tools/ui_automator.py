"""
Motor de Visão e Interação de Interface Android via ADB (uiautomator + input events).
100% stdlib Python, apoiado em adb_bridge.py para leitura da árvore de UI,
busca semântica de elementos e digitação com preservação de acentuação PT-BR.
"""

import re
import subprocess
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional, Tuple

from .adb_bridge import ensure_adb_connected, is_screen_unlocked, run_adb_shell

_UI_LOCK = threading.RLock()

_BOUNDS_RE = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")


def _normalize_ui_text(text: str) -> str:
    """Remove acentos, converte para minúsculas e normaliza espaços."""
    deaccent = unicodedata.normalize("NFKD", str(text or "")).encode("ASCII", "ignore").decode("ASCII")
    return re.sub(r"\s+", " ", deaccent).strip().lower()


def _parse_bounds(bounds_str: str) -> Optional[Tuple[int, int, int, int, int, int]]:
    """Converte '[x1,y1][x2,y2]' em (x1, y1, x2, y2, cx, cy) se a área for positiva."""
    m = _BOUNDS_RE.search(str(bounds_str or ""))
    if not m:
        return None
    x1, y1, x2, y2 = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
    if x2 <= x1 or y2 <= y1:
        return None
    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2
    return x1, y1, x2, y2, cx, cy


def _extract_xml_payload(raw_output: str) -> str:
    """Remove prefixos de log do uiautomator antes de '<?xml' ou '<hierarchy'."""
    text = (raw_output or "").strip()
    if not text:
        return ""
    idx_xml = text.find("<?xml")
    if idx_xml != -1:
        return text[idx_xml:].strip()
    idx_hier = text.find("<hierarchy")
    if idx_hier != -1:
        return text[idx_hier:].strip()
    return text


def dump_ui_nodes() -> List[Dict[str, Any]]:
    """
    Captura a árvore de UI atual via 'uiautomator dump' sob _UI_LOCK e retorna
    a lista ordenada de nós visíveis com área positiva.
    """
    with _UI_LOCK:
        xml_raw = ""
        ok_dump, out_dump = run_adb_shell(["uiautomator", "dump", "/sdcard/silva_ui.xml"], timeout=5.0)
        if ok_dump:
            ok_cat, out_cat = run_adb_shell(["cat", "/sdcard/silva_ui.xml"], timeout=5.0)
            if ok_cat and ("<hierarchy" in out_cat or "<?xml" in out_cat):
                xml_raw = out_cat

        if not xml_raw:
            ok_tty, out_tty = run_adb_shell(["uiautomator", "dump", "/dev/tty"], timeout=5.0)
            if ok_tty and ("<hierarchy" in out_tty or "<?xml" in out_tty):
                xml_raw = out_tty
            elif out_dump and ("<hierarchy" in out_dump or "<?xml" in out_dump):
                xml_raw = out_dump

    xml_clean = _extract_xml_payload(xml_raw)
    if not xml_clean:
        return []

    try:
        root = ET.fromstring(xml_clean)
    except ET.ParseError:
        return []

    nodes: List[Dict[str, Any]] = []
    for elem in root.iter("node"):
        parsed_bounds = _parse_bounds(elem.attrib.get("bounds", ""))
        if not parsed_bounds:
            continue
        x1, y1, x2, y2, cx, cy = parsed_bounds
        nodes.append({
            "text": elem.attrib.get("text", ""),
            "content_desc": elem.attrib.get("content-desc", ""),
            "resource_id": elem.attrib.get("resource-id", ""),
            "class_name": elem.attrib.get("class", ""),
            "clickable": elem.attrib.get("clickable", "false").lower() == "true",
            "enabled": elem.attrib.get("enabled", "false").lower() == "true",
            "bounds": (x1, y1, x2, y2),
            "center": (cx, cy),
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2,
            "cx": cx,
            "cy": cy,
        })
    return nodes


def _score_node(norm_query: str, node: Dict[str, Any]) -> int:
    """Pontua a aderência de um nó da UI à consulta normalizada."""
    if not norm_query:
        return 0
    text_n = _normalize_ui_text(node.get("text", ""))
    desc_n = _normalize_ui_text(node.get("content_desc", ""))
    res_n = _normalize_ui_text(node.get("resource_id", ""))

    # 1. Match exato em text ou content_desc
    if norm_query == text_n or norm_query == desc_n:
        return 100

    # 2. Match por palavra inteira ou início de frase
    word_re = re.compile(rf"(?:^|\b){re.escape(norm_query)}(?:\b|$)")
    if (text_n and (text_n.startswith(norm_query) or word_re.search(text_n))) or (
        desc_n and (desc_n.startswith(norm_query) or word_re.search(desc_n))
    ):
        return 80

    # 3. Substring em text, content_desc ou resource_id
    if norm_query in text_n or norm_query in desc_n or norm_query in res_n:
        return 60

    return 0


def _find_clickable_container(target: Dict[str, Any], nodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Localiza o menor nó clicável que envolve o centro (cx, cy) do rótulo encontrado."""
    cx, cy = target["cx"], target["cy"]
    containers = []
    for n in nodes:
        if not n.get("clickable"):
            continue
        if n["x1"] <= cx <= n["x2"] and n["y1"] <= cy <= n["y2"]:
            area = (n["x2"] - n["x1"]) * (n["y2"] - n["y1"])
            containers.append((area, n))
    if not containers:
        return None
    containers.sort(key=lambda item: item[0])
    return containers[0][1]


def find_ui_node(
    query: str,
    nodes: Optional[List[Dict[str, Any]]] = None,
    clickable_only: bool = False,
) -> Optional[Dict[str, Any]]:
    """
    Busca semanticamente um elemento na árvore de UI.
    Se clickable_only=True e o nó encontrado não for clicável, sobe para o
    ancestral/container clicável que contém suas coordenadas.
    """
    norm_query = _normalize_ui_text(query)
    if not norm_query:
        return None

    ui_nodes = nodes if nodes is not None else dump_ui_nodes()
    if not ui_nodes:
        return None

    best_score = 0
    best_area = float("inf")
    best_node: Optional[Dict[str, Any]] = None

    for node in ui_nodes:
        score = _score_node(norm_query, node)
        if score <= 0:
            continue
        area = (node["x2"] - node["x1"]) * (node["y2"] - node["y1"])
        if score > best_score or (score == best_score and area < best_area):
            best_score = score
            best_area = area
            best_node = node

    if not best_node:
        return None

    if clickable_only and not best_node.get("clickable"):
        container = _find_clickable_container(best_node, ui_nodes)
        if container:
            return container

    return best_node


def tap_coords(x: int, y: int) -> Tuple[bool, str]:
    """Executa toque real nas coordenadas (x, y) via ADB input tap sob _UI_LOCK."""
    with _UI_LOCK:
        return run_adb_shell(["input", "tap", str(int(x)), str(int(y))], timeout=4.0)


def press_key(keycode: Any) -> Tuple[bool, str]:
    """Envia um evento de tecla Android (ex: 66=ENTER, 279=PASTE) via ADB sob _UI_LOCK."""
    with _UI_LOCK:
        return run_adb_shell(["input", "keyevent", str(keycode)], timeout=4.0)


def tap_element(label: str, timeout: float = 4.0) -> Tuple[bool, str]:
    """
    Faz polling da árvore de UI a cada 0.5s até 'timeout' procurando 'label'
    e toca no centro do elemento (ou de seu container clicável) sob _UI_LOCK.
    """
    if not ensure_adb_connected():
        return False, "ADB local não conectado para tocar na tela."

    with _UI_LOCK:
        deadline = time.monotonic() + max(0.5, float(timeout))
        while True:
            nodes = dump_ui_nodes()
            node = find_ui_node(label, nodes=nodes, clickable_only=True)
            if node:
                ok, out = tap_coords(node["cx"], node["cy"])
                if ok:
                    return True, f"Tocado em '{label}' nas coordenadas ({node['cx']}, {node['cy']})."
                return False, f"Falha ao tocar em '{label}': {out}"

            if time.monotonic() >= deadline:
                break
            time.sleep(0.5)

        return False, f"Elemento '{label}' não encontrado na tela."


def _set_device_clipboard(text: str) -> bool:
    """Grava texto na área de transferência do Android preservando acentos PT-BR."""
    try:
        res = subprocess.run(
            ["termux-clipboard-set"],
            input=text,
            text=True,
            capture_output=True,
            timeout=3.0,
            check=False,
        )
        if res.returncode == 0:
            return True
    except Exception:
        pass

    ok, out = run_adb_shell(["cmd", "clipboard", "set-text", text], timeout=4.0)
    low = (out or "").lower()
    if ok and "no shell command" not in low and "error" not in low and "exception" not in low:
        return True
    return False


def get_screen_dimensions(nodes: Optional[List[Dict[str, Any]]] = None) -> Tuple[int, int]:
    """Obtém (largura, altura) da tela via 'wm size' ou a partir dos bounds dos nós."""
    try:
        ok, out = run_adb_shell(["wm", "size"], timeout=3.0)
        if ok and out:
            m = re.search(r"(\d{3,4})x(\d{3,4})", out)
            if m:
                return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    if nodes:
        max_x = max((int(n.get("x2") or n.get("cx") or 0) for n in nodes), default=0)
        max_y = max((int(n.get("y2") or n.get("cy") or 0) for n in nodes), default=0)
        if max_x >= 480 and max_y >= 800:
            return max_x, max_y
    return 1080, 2400


def type_text_unicode(text: str) -> Tuple[bool, str]:
    """
    Digita texto no campo focado preservando acentuação PT-BR via clipboard + KEYCODE_PASTE (279),
    com fallback ASCII para 'adb shell input text'.
    """
    clean_text = str(text or "")
    if not clean_text:
        return False, "Texto vazio para digitação."

    if _set_device_clipboard(clean_text):
        ok_paste, _ = press_key(279)  # KEYCODE_PASTE
        if ok_paste:
            return True, "Texto inserido com acentuação via clipboard."
        # fallback se paste falhar

    ascii_text = unicodedata.normalize("NFKD", clean_text).encode("ASCII", "ignore").decode("ASCII")
    escaped = ascii_text.replace(" ", "%s")
    ok_type, out_type = run_adb_shell(["input", "text", escaped], timeout=6.0)
    if ok_type:
        return True, "Texto inserido via input text."
    return False, f"Falha ao digitar texto: {out_type}"
