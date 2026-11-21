"""
Mapeador inteligente de intenções em linguagem natural (PT-BR) para chamadas de função do Silva.
Atua como camada de fallback ultra-rápida e robusta para garantir que todos os comandos
sejam traduzidos com precisão imediata mesmo em micro-modelos quantizados.
Suporta comandos únicos e multi-ações encadeadas ("e", "depois", "também").
"""

import re
import unicodedata
from typing import List, Optional


def normalize_text(text: str) -> str:
    """Remove acentos, converte para minúsculas e remove pontuação excessiva."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    text_clean = "".join([c for c in nfkd if not unicodedata.combining(c)])
    return text_clean.strip()


def parse_single_intent(raw_cmd: str) -> Optional[str]:
    """Tenta identificar uma intenção específica e retornar uma tag <call>...</call>."""
    cmd = normalize_text(raw_cmd)
    if not cmd:
        return None

    # 1. Lanterna (set_torch)
    if "lanterna" in cmd or "torch" in cmd or "flash" in cmd:
        if any(neg in cmd for neg in ["deslig", "desativ", "apag", "off", "fecha", "cort", "tir"]):
            return "<call>set_torch(state=False)</call>"
        return "<call>set_torch(state=True)</call>"

    # 2. Bateria (get_battery)
    if any(w in cmd for w in ["bateria", "carga", "porcentagem", "nivel de bateria", "quanta bateria", "status da bateria"]):
        return "<call>get_battery()</call>"

    # 3. Vibração (vibrate)
    if any(w in cmd for w in ["vibra", "vibrar", "vibracao", "treme", "tremer"]):
        m = re.search(r"(\d+)\s*(?:ms|milissegundos|segundos|s)?", cmd)
        duration = 500
        if m:
            val = int(m.group(1))
            if "segundo" in cmd or " s" in cmd:
                duration = val * 1000
            else:
                duration = val
        return f"<call>vibrate(duration_ms={duration})</call>"

    # 4. Não Perturbe / Silencioso (set_dnd)
    if any(w in cmd for w in ["perturbe", "pertube", "dnd", "silencioso", "silenciar", "mutar", "mudo"]):
        if any(neg in cmd for neg in ["desativ", "deslig", "tir", "sair", "off", "cancel", "voltar"]):
            return "<call>set_dnd(state=False)</call>"
        return "<call>set_dnd(state=True)</call>"

    # 5. Captura de Tela / Print (take_screenshot)
    if any(w in cmd for w in ["print", "screenshot", "captura de tela", "capturar tela", "foto da tela"]):
        return "<call>take_screenshot()</call>"

    # 6. Câmera / Foto (take_photo)
    if any(w in cmd for w in ["foto", "selfie", "retrato", "fotografa"]) and not any(s in cmd for s in ["tela", "screen", "print", "video", "gravar", "filmar"]):
        if any(w in cmd for w in ["frontal", "selfie", "frente", "minha foto", "foto minha"]):
            return "<call>take_photo(camera_id=1)</call>"
        return "<call>take_photo(camera_id=0)</call>"

    # 6.1 Gravação de Vídeo (record_video)
    if any(w in cmd for w in ["video", "gravar", "grave", "grava", "filmar", "filma", "filme"]) and not any(w in cmd for w in ["youtube", "tiktok"]):
        m_dur = re.search(r"(\d+)\s*(?:segundos?|s|minutos?|min)?", cmd)
        duration = 10
        if m_dur:
            val = int(m_dur.group(1))
            if "minuto" in cmd or "min" in cmd:
                duration = val * 60
            else:
                duration = val
        duration = max(3, min(duration, 120))
        camera_id = 1 if any(w in cmd for w in ["frontal", "selfie", "frente", "me film", "me grav", "minha cara"]) else 0
        return f"<call>record_video(duration={duration}, camera_id={camera_id})</call>"

    # 7. Abrir Aplicativo (open_app)
    m_open = re.search(r"(?:abre|abra|abrir|inicia|inicie|iniciar|roda|rode|rodar|executa|execute|executar)\s+(?:o|a)?\s*([a-zA-Z0-9_\-\s]+)", cmd)
    if m_open and not any(w in cmd for w in ["lanterna", "camera", "foto", "timer", "alarme", "print", "screenshot", "tela"]):
        app_name = m_open.group(1).strip()
        # Remove palavras parasitas no final
        app_name = re.sub(r"\s+(?:pra mim|por favor|agora|rapido)$", "", app_name).strip()
        if app_name:
            return f'<call>open_app(app_name="{app_name}")</call>'

    # 7. Ligação telefônica (make_call)
    m_call = re.search(r"(?:liga|ligar|disca|discar|chama|chamar|telefone|telefonar)\s+(?:para\s+o|para\s+a|para|pro|pra|a)?\s*([^\n\r,\.;]+)", raw_cmd, re.IGNORECASE)
    if m_call and not any(w in cmd for w in ["lanterna", "alarme", "som", "brilho"]):
        target = m_call.group(1).strip()
        target = re.sub(r"(?i)\s+(?:pra mim|por favor|agora|rapido)$", "", target).strip()
        if target:
            return f'<call>make_call(number="{target}")</call>'

    # 8. Envio de SMS (send_sms)
    m_sms = re.search(r"(?:envia|enviar|manda|mandar)\s+(?:um\s+)?sms\s+(?:para|pro|pra)?\s*([a-zA-Z0-9_\+\s]+?)\s+(?:falando|dizendo|com a mensagem|que|de)\s+(.+)", raw_cmd, re.IGNORECASE)
    if m_sms:
        to_target = m_sms.group(1).strip()
        msg_body = m_sms.group(2).strip()
        return f'<call>send_sms(number="{to_target}", message="{msg_body}")</call>'

    # 9. Leitura de SMS (get_last_sms)
    if any(w in cmd for w in ["ler sms", "leia sms", "ultimos sms", "ultimo sms", "mensagens recentes", "ver sms"]):
        m_lim = re.search(r"(\d+)\s*(?:ultimos|sms|mensagens)?", cmd)
        limit = int(m_lim.group(1)) if m_lim else 5
        return f"<call>get_last_sms(limit={limit})</call>"

    # 10. Localização / GPS
    if any(w in cmd for w in ["ultima localizacao", "última localização", "ultimo gps", "onde estive", "onde eu estava", "posicao anterior", "localizacao anterior"]):
        return "<call>get_last_location()</call>"

    if any(w in cmd for w in ["gps", "localizacao"]):
        if any(neg in cmd for neg in ["desativ", "deslig", "desliga", "tirar", "sair", "off", "cancel"]):
            return "<call>set_location_state(state=False)</call>"
        if any(pos in cmd for pos in ["ativ", "ligar", "liga ", "habilita", "habilitar", "on"]):
            return "<call>set_location_state(state=True)</call>"

    if any(w in cmd for w in ["localizacao", "onde estou", "onde eu estou", "gps", "coordenadas", "minha posicao", "minha localizacao"]):
        return "<call>get_location()</call>"

    # 11. Contar Piada (tell_joke)
    if any(w in cmd for w in ["piada", "engracado", "conta uma piada", "me faz rir"]):
        return "<call>tell_joke()</call>"

    # 12. Área de transferência (get_clipboard / set_clipboard)
    if "clipboard" in cmd or "area de transferencia" in cmd or "o que copiei" in cmd or "copiado" in cmd:
        # Prioriza consulta se contiver palavras interrogativas/de leitura
        if any(q in cmd for q in ["o que", "qual", "ler", "le ", "ver", "mostra", "tem", "copiado", "conteudo", "consulte", "consultar"]):
            return "<call>get_clipboard()</call>"
        # Verifica se há verbo de escrita explícito
        if any(w in cmd for w in ["copia ", "copie ", "salva ", "salve ", "coloca ", "coloque ", "define ", "definir "]) or cmd.startswith(("copia", "copie", "salva", "salve", "coloca", "coloque", "define", "definir")):
            m_clip = re.search(r"(?:copia|copie|salva|salve|coloca|coloque|define|definir)\s+(?:no\s+clipboard|na\s+area\s+de\s+transferencia|o\s+texto)?\s*(.+)", raw_cmd, re.IGNORECASE)
            text_val = m_clip.group(1).strip() if m_clip else ""
            text_val = re.sub(r"(?i)^(?:no\s+clipboard|na\s+area\s+de\s+transferencia|o\s+texto)\s*", "", text_val).strip()
            text_val = re.sub(r"(?i)\s+(?:no\s+clipboard|na\s+area\s+de\s+transferencia|para\s+o\s+clipboard)$", "", text_val).strip()
            if text_val:
                return f'<call>set_clipboard(text="{text_val}")</call>'
        return "<call>get_clipboard()</call>"

    # 13. Alarme (set_alarm / cancel_alarm)
    if "alarme" in cmd or "despertador" in cmd:
        if any(w in cmd for w in ["cancela", "cancelar", "desativa", "desativar", "apaga", "remover"]):
            m_time = re.search(r"(\d{1,2}(?::\d{2})?)", cmd)
            t_str = m_time.group(1) if m_time else ""
            if t_str and ":" not in t_str:
                t_str = f"{int(t_str):02d}:00"
            return f'<call>cancel_alarm(time="{t_str}", day="", label="")</call>'
        else:
            m_time = re.search(r"(\d{1,2}(?::\d{2})?)", cmd)
            t_str = m_time.group(1) if m_time else "07:00"
            if ":" not in t_str:
                t_str = f"{int(t_str):02d}:00"
            return f'<call>set_alarm(time="{t_str}", label="Alarme", days=[])</call>'

    # 14. Timer (set_timer)
    if "timer" in cmd or "temporizador" in cmd:
        m_min = re.search(r"(\d+)\s*(?:minutos?|min)?", cmd)
        minutes = int(m_min.group(1)) if m_min else 5
        return f'<call>set_timer(minutes={minutes}, label="Timer")</call>'

    # 15. Memória (remember_note / recall_note)
    if any(w in cmd for w in ["lembra que", "lembrar que", "anota que", "salva que", "guarda que"]):
        content = re.sub(r"(?i)^(?:silva,?\s*)?(?:lembra|lembrar|anota|anotar|salva|salvar|guarda|guardar)\s+que\s+", "", raw_cmd).strip()
        if "=" in content:
            k, v = content.split("=", 1)
        elif " e " in content:
            parts = content.split(" e ", 1)
            k, v = parts[0], parts[1]
        elif " e: " in content or ":" in content:
            parts = content.split(":", 1)
            k, v = parts[0], parts[1]
        else:
            k, v = "nota", content
        return f'<call>remember_note(key="{k.strip()}", value="{v.strip()}")</call>'

    if any(w in cmd for w in ["o que voce lembra", "qual a senha", "onde guardei", "lembra de", "lembra do", "lembra da"]) or (
        any(w in cmd for w in ["qual o", "qual a"]) and not any(w in cmd for w in ["bateria", "clima", "tempo", "previsao", "temperatura", "localizacao", "hora", "clipboard", "foto", "print"])
    ):
        q = re.sub(r"(?i)^(?:silva,?\s*)?(?:qual|onde|o que|lembra)\s+(?:voce\s+lembra\s+)?(?:de|do|da|o|a)?\s*", "", raw_cmd).strip().rstrip("?")
        return f'<call>recall_note(query="{q}")</call>'

    # 16. Notificações (get_notifications)
    if any(w in cmd for w in ["notificacoes", "notificacao", "notificacoes do"]):
        m_app = re.search(r"(?:do|da|de)\s+([a-zA-Z0-9_\-]+)", cmd)
        app_filter = m_app.group(1).strip() if m_app else ""
        if app_filter in ["celular", "meu", "sistema"]:
            app_filter = ""
        return f'<call>get_notifications(app="{app_filter}")</call>'

    # 17. Volume (set_volume)
    if "volume" in cmd:
        m_vol = re.search(r"(\d+)\s*(?:%|porcento)?", cmd)
        level = int(m_vol.group(1)) if m_vol else 50
        return f'<call>set_volume(stream="music", level={level})</call>'

    # 18. Brilho (set_brightness)
    if "brilho" in cmd:
        m_bri = re.search(r"(\d+)\s*(?:%|porcento)?", cmd)
        level = int(m_bri.group(1)) if m_bri else 50
        return f"<call>set_brightness(level={level})</call>"

    # 19. Calculadora (calculate)
    m_calc = re.search(r"(?:quanto e|calcula|calcule|conta de)\s+([0-9\+\-\*\/\(\)\^\.\s]+)", cmd)
    if m_calc:
        expr = m_calc.group(1).strip()
        expr = expr.replace("^", "**").rstrip("?")
        return f'<call>calculate(expression="{expr}")</call>'

    # 20. Previsão do tempo / Clima (get_weather)
    if any(w in cmd for w in ["clima", "previsao", "tempo", "chover", "chuva", "temperatura"]) and not any(w in cmd for w in ["no google", "pesquisa no google"]):
        day = "hoje"
        if "depois de amanha" in cmd or "depois de amanhã" in cmd:
            day = "depois de amanhã"
        elif "amanha" in cmd or "amanhã" in cmd:
            day = "amanhã"
        else:
            for wd in ["segunda", "terca", "terça", "quarta", "quinta", "sexta", "sabado", "sábado", "domingo"]:
                if wd in cmd:
                    day = wd
                    break

        time_val = ""
        if "noite" in cmd:
            time_val = "noite"
        elif "tarde" in cmd:
            time_val = "tarde"
        elif "madrugada" in cmd:
            time_val = "madrugada"
        elif re.search(r"\bde manh[aã]\b|\bpela manh[aã]\b|\bmanh[aã]\b", cmd) and not re.search(r"\bamanh[aã]\b", cmd):
            time_val = "manhã"
        else:
            m_t = re.search(r"(\d{1,2}(?::\d{2}|h\d{0,2})?)", cmd)
            if m_t and not any(c in m_t.group(1) for c in ["graus", "º", "°"]):
                time_val = m_t.group(1)

        loc = ""
        m_city = re.search(r"(?:em|para|pra|no|na)\s+([a-zA-ZÀ-ÿ\s]+)", raw_cmd, re.IGNORECASE)
        if m_city:
            cand = m_city.group(1).strip()
            cand = re.sub(r"(?i)\s+(?:no|na|em|de|para|pra)?\s*(?:hoje|amanha|amanhã|depois de amanha|depois de amanhã|segunda|terca|terça|quarta|quinta|sexta|sabado|sábado|domingo|noite|tarde|manha|manhã|as|às|\d{1,2}h|\d{1,2}:\d{2}).*$", "", cand).strip()
            cand = re.sub(r"[?!.,;]+$", "", cand).strip()
            if cand and cand.lower() not in ["hoje", "amanha", "amanhã", "depois", "aqui", "minha cidade", "mim", "graus"]:
                loc = cand

        return f'<call>get_weather(day="{day}", time="{time_val}", location="{loc}")</call>'

    # 21. Pesquisa no Google (search_google)
    if any(w in cmd for w in ["pesquisa", "pesquise", "busca", "busque", "procura", "procure", "google", "no google"]):
        q = raw_cmd
        q = re.sub(r"(?i)^(?:silva,?\s*)?", "", q).strip()
        q = re.sub(
            r"(?i)^(?:pesquise\s+no\s+google|pesquisa\s+no\s+google|busca\s+no\s+google|busque\s+no\s+google|procura\s+no\s+google|procure\s+no\s+google|"
            r"pesquisa(?:r|ndo)?|pesquise|busca(?:r|ndo)?|busque|procura(?:r|ndo)?|procure|google|fazer\s+uma\s+busca\s+no\s+google\s+por|"
            r"fazer\s+uma\s+busca\s+por|faz\s+uma\s+busca\s+no\s+google\s+por|faz\s+uma\s+busca\s+por)\s+",
            "",
            q
        ).strip()
        q = re.sub(r"(?i)^(?:no\s+google\s+|pelo\s+google\s+|sobre\s+|por\s+|para\s+)?", "", q).strip()
        q = re.sub(r"(?i)\s+(?:no\s+google|pelo\s+google)?\s*(?:por\s+favor|pra\s+mim|agora)?$", "", q).strip().rstrip("?")
        q = re.sub(r"(?i)\s+(?:no\s+google|pelo\s+google)$", "", q).strip().rstrip("?")
        if q:
            return f'<call>search_google(query="{q}")</call>'

    return None


def match_intent_fallback(user_prompt: str) -> Optional[str]:
    """
    Roteador de intenções composto.
    Detecta multi-comandos combinados com 'e', 'depois', 'alem disso', etc.
    Exemplo: "liga a lanterna e vibra o celular" -> <call>set_torch(state=True)</call><call>vibrate(duration_ms=500)</call>
    """
    clean_prompt = user_prompt.strip()
    if not clean_prompt:
        return None

    # Tenta quebrar em cláusulas sequenciais para multi-call
    # Divide por " e ", " e também ", " depois ", ou ";"
    delimiters = r"\s+(?:e\s+tambem|depois|em\s+seguida|e)\s+|;"
    sub_clauses = [c.strip() for c in re.split(delimiters, clean_prompt, flags=re.IGNORECASE) if c.strip()]

    matched_calls = []
    if len(sub_clauses) > 1:
        for clause in sub_clauses:
            call = parse_single_intent(clause)
            if call:
                matched_calls.append(call)

    # Se conseguiu multi-chamadas
    if len(matched_calls) >= 2:
        return "".join(matched_calls)

    # Tenta frase inteira como comando único
    return parse_single_intent(clean_prompt)
