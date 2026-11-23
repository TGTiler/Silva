"""
Módulo Apps, Mobilidade e Utilidades do Silva: Abertura de Apps, Uber/99, iFood, Play Store, Piadas e Capacidades.
"""

import difflib
import os
import random
import re
import unicodedata
import urllib.parse
from typing import Any, Dict, Optional

from .core import (
    APP_PACKAGES,
    RESOLVED_APP_ACTIVITIES,
    SIMULATE_HARDWARE,
    _run_termux_cmd,
    _exec_android_intent,
)
from .comms import set_clipboard
from .memory_schedule import _load_memory, _normalize_text

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

def open_app(app_name: str) -> Dict[str, Any]:
    """Abre um aplicativo pelo nome ou pacote Android com tolerância a ruído e fuzzy matching."""
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
      "ir na casa da minha tia" -> "casa da minha tia"
    """
    if not raw_dest:
        return ""
    text = str(raw_dest).strip()

    # 1. Sufixos de cortesia e ruídos no final
    suffix_pat = r"(?i)\s+(?:por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|de\s+uber|de\s+99|no\s+uber|na\s+99|pelo\s+uber|pela\s+99|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    # 2. Prefixos conversacionais no início (repetidos até limpar completamente)
    prefix_patterns = [
        r"(?i)^(?:me\s+levar|me\s+leva|me\s+leve|levar|leva|leve|chegar|voltar|ir)\b\s*",
        r"(?i)^(?:para|pra|pro|pras|pros)\b\s*",
        r"(?i)^p/\s*",
        r"(?i)^(?:mim|eu|gente|nós|nos)\b\s*",
        r"(?i)^(?:ao|aos|à|às|no|na|nos|nas|em|até|ate)\b\s*",
        r"(?i)^(?:o|a|os|as)\b\s*",
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


def request_ride(destination: str, app: str = "uber") -> Dict[str, Any]:
    """Abre o aplicativo de transporte (Uber ou 99) com o destino configurado a partir da localização atual."""
    clean_dest = _clean_ride_destination(destination)
    if not clean_dest:
        return {"status": "error", "message": "Destino da corrida não informado."}

    # 1. Integração com Memória Local: consulta se o destino corresponde a um local salvo
    resolved_destination = clean_dest
    mem = _load_memory()
    if mem:
        norm_dest = _normalize_text(clean_dest)
        query_tokens = set(norm_dest.split())
        best_match = None
        best_score = 0
        for k, v_data in mem.items():
            val = v_data.get("value", "") if isinstance(v_data, dict) else str(v_data)
            norm_k = _normalize_text(k)
            score = 0
            if norm_dest == norm_k:
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

    app_target = str(app).strip().lower() if app else "uber"

    if app_target == "uber":
        encoded_dest = urllib.parse.quote(resolved_destination)
        url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_dest}"
        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Abrindo UBER com destino para '{resolved_destination}'. Basta confirmar a corrida na tela. [Simulado]",
                "data": {"destination": resolved_destination, "app": "uber", "url": url}
            }
        _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"Abrindo UBER com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
            "data": {"destination": resolved_destination, "app": "uber", "url": url}
        }

    elif app_target in ("99", "99pop"):
        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Abrindo 99 com destino para '{resolved_destination}'. Basta confirmar a corrida na tela. [Simulado]",
                "data": {"destination": resolved_destination, "app": "99"}
            }
        set_clipboard(resolved_destination)
        open_app("99")
        return {
            "status": "ok",
            "message": f"Abrindo 99 com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
            "data": {"destination": resolved_destination, "app": "99"}
        }
    else:
        encoded_dest = urllib.parse.quote(resolved_destination)
        url = f"https://m.uber.com/ul/?action=setPickup&pickup=my_location&dropoff[formatted_address]={encoded_dest}"
        if not SIMULATE_HARDWARE:
            _exec_android_intent(f'am start -a android.intent.action.VIEW -d "{url}"')
        return {
            "status": "ok",
            "message": f"Abrindo {app_target.upper()} com destino para '{resolved_destination}'. Basta confirmar a corrida na tela.",
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
    suffix_pat = r"(?i)\s+(?:no\s+ifood|pelo\s+ifood|na\s+99|no\s+99|no\s+99\s*food|pelo\s+99|pelo\s+99\s*food|pra\s+mim|para\s+mim|por\s+favor|pfv|pfvr|agora|agr|aí|ai|silva|obrigad[oa]|vlw|valeu)$"
    for _ in range(5):
        prev = text
        text = re.sub(suffix_pat, "", text).strip()
        text = re.sub(r"[?!.,;:]+$", "", text).strip()
        if text == prev:
            break

    # 2. Prefixos de comando no início da frase (repetidos até limpar)
    prefix_patterns = [
        r"(?i)^(?:silva|ei|oi)\b\s*",
        r"(?i)^(?:abre\s+o\s+ifood\s+e\s+pede|abre\s+o\s+ifood\s+e\s+peça|abre\s+o\s+ifood\s+e\s+peca|abre\s+o\s+ifood\s+e\s+pedir)\b\s*",
        r"(?i)^(?:abre\s+o\s+99\s+e\s+pede|abre\s+a\s+99\s+e\s+pede)\b\s*",
        r"(?i)^(?:quero\s+pedir|quero|gostaria\s+de\s+pedir|gostaria\s+de|me\s+vê|me\s+ve)\b\s*",
        r"(?i)^(?:peça|peca|pede|pedir|compra|comprar|compre|busca|busque|buscar|procura|procure|procurar|acha|achar|pesquisa|pesquisar)\b\s*",
        r"(?i)^(?:delivery\s+de|delivery)\b\s*",
        r"(?i)^(?:um|uma|uns|umas)\b\s*",
        r"(?i)^(?:comida|lanche)\b\s*",
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


def order_food(query: str, app: str = "ifood") -> Dict[str, Any]:
    """Abre o aplicativo de delivery (iFood ou 99) buscando o prato, restaurante ou item pedido."""
    clean_query = _clean_food_query(query)
    if not clean_query:
        return {"status": "error", "message": "Item ou prato para busca de comida não informado."}

    app_target = str(app).strip().lower() if app else "ifood"
    encoded_query = urllib.parse.quote(clean_query)

    if app_target == "ifood":
        # 1. Copia para a área de transferência (garante colar em 1 toque na lupa)
        set_clipboard(clean_query)
        url_web = f"https://www.ifood.com.br/busca?q={encoded_query}&tab=0"
        url_deep = f"ifood://search?term={encoded_query}"

        if SIMULATE_HARDWARE:
            return {
                "status": "ok",
                "message": f"Buscando '{clean_query}' no iFood (termo também copiado para a área de transferência caso precise colar na lupa).\nhttps://www.ifood.com.br/busca?q={encoded_query}",
                "data": {"query": clean_query, "app": "ifood", "url": url_web}
            }

        # 2. Ordem de disparo no Android:
        # Tentativa 1 (Deep Link interno do app)
        cmd_app = f'am start -a android.intent.action.VIEW -d "{url_deep}" -p br.com.brainweb.ifood'
        res1 = _exec_android_intent(cmd_app)

        # Tentativa 2 (Fallback se Tentativa 1 falhou / pacote não encontrado / ActivityNotFound)
        if res1.returncode != 0 or "Error:" in res1.stderr or "ActivityNotFound" in res1.stderr or "does not exist" in res1.stderr:
            cmd_web = f'am start -a android.intent.action.VIEW -d "{url_web}"'
            _exec_android_intent(cmd_web)

        return {
            "status": "ok",
            "message": f"Buscando '{clean_query}' no iFood (termo também copiado para a área de transferência caso precise colar na lupa).\nhttps://www.ifood.com.br/busca?q={encoded_query}",
            "data": {"query": clean_query, "app": "ifood", "url": url_web}
        }

    elif app_target in ("99", "99food", "99 food"):
        set_clipboard(clean_query)
        if not SIMULATE_HARDWARE:
            open_app("99")
        return {
            "status": "ok",
            "message": f"Buscando '{clean_query}' no 99 (termo copiado para a área de transferência).",
            "data": {"query": clean_query, "app": "99"}
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


# Dicionário de registro de funções disponíveis para o parser
