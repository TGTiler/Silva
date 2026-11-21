#!/usr/bin/env python3
"""
Script de correção, higienização e balanceamento completo de train.jsonl
- Corrige make_call(target=...) -> make_call(number=...)
- Corrige send_sms(target=..., message=...) -> send_sms(number=..., message=...)
- Corrige vibrate(state=True/False) -> vibrate(duration_ms=...)
- Adiciona amostras ricas para classes com baixa contagem (get_last_sms, get_battery, get_last_location, set_clipboard, etc.)
- Valida 100% das linhas contra o schema.json
"""

import ast
import json
import re
import shutil
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = BASE_DIR / "schema.json"
TRAIN_PATH = BASE_DIR / "train.jsonl"
BACKUP_PATH = BASE_DIR / "train.jsonl.bak"

CALL_TAG_REGEX = re.compile(r"<call>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\((.*?)\)\s*</call>", re.DOTALL)


def load_schema(schema_file: Path) -> dict:
    with open(schema_file, "r", encoding="utf-8") as f:
        return json.load(f)["tools"]


def fix_line(item: dict) -> dict:
    prompt = item["prompt"]
    comp = item["completion"]

    # 1. make_call: target= -> number=
    if "make_call(target=" in comp:
        comp = comp.replace("make_call(target=", "make_call(number=")

    # 2. send_sms: target= -> number=
    if "send_sms(target=" in comp:
        comp = comp.replace("send_sms(target=", "send_sms(number=")

    # 3. vibrate(state=True) -> vibrate(duration_ms=500)
    if "vibrate(state=True)" in comp:
        comp = comp.replace("vibrate(state=True)", "vibrate(duration_ms=500)")

    # 4. vibrate(state=False) -> ajustar prompt e duração
    if "vibrate(state=False)" in comp:
        durations = [1000, 2000, 300, 800, 1500, 400]
        chosen_ms = durations[hash(prompt) % len(durations)]
        # Se for multi-call, mantém o resto
        comp = comp.replace("vibrate(state=False)", f"vibrate(duration_ms={chosen_ms})")
        # Ajusta prompt para não parecer 'desativa'
        p_lower = prompt.lower()
        if "desativa" in p_lower or "desliga" in p_lower or "tira" in p_lower or "sem" in p_lower:
            prompt = f"Silva, faça o celular vibrar por {chosen_ms} milissegundos"

    return {"prompt": prompt, "completion": comp}


def generate_enrichment_samples() -> list[dict]:
    samples = []

    # 1. get_last_sms (55 amostras)
    sms_limits = [1, 2, 3, 5, 10, 15]
    sms_prompts = [
        ("Silva, leia meus últimos SMS", 5),
        ("Mostre as últimas mensagens de texto que recebi", 5),
        ("Tem algum SMS novo no aparelho?", 3),
        ("Lê os últimos 10 SMS pra mim", 10),
        ("Chegou alguma mensagem no chip?", 5),
        ("Vê quem me mandou SMS recentemente", 5),
        ("Quais foram as últimas 3 mensagens recebidas?", 3),
        ("Mostra a caixa de entrada de SMS", 5),
        ("Lê os SMS recentes", 5),
        ("Alguém mandou SMS hoje?", 5),
        ("Consulta os últimos torpedos recebidos", 5),
        ("Verifica as últimas mensagens de texto", 5),
        ("Mostre os últimos 7 SMS recebidos", 7),
        ("Quem mandou o último SMS?", 1),
        ("Mostra o último SMS que chegou", 1),
        ("Silva, dá uma olhada nos meus SMS", 5),
        ("Lê as duas últimas mensagens de texto", 2),
        ("Verifica se o banco mandou SMS", 5),
        ("Tem código de verificação no SMS?", 3),
        ("Quais mensagens de texto chegaram?", 5),
        ("Checar últimas mensagens SMS", 5),
        ("Abre as últimas mensagens de texto", 5),
        ("Vê os 15 últimos SMS pra mim", 15),
        ("Mostra o SMS que acabei de receber", 1),
        ("Silva, verifica meu correio de SMS", 5),
        ("Quais foram as mensagens que recebi no chip?", 5),
        ("Lê as mensagens SMS recebidas", 5),
        ("Confere os últimos torpedos", 3),
        ("Silva, lista as últimas mensagens recebidas", 5),
        ("Tem alguma mensagem importante no SMS?", 5),
        ("Lê pra mim os últimos 4 SMS", 4),
        ("Vê os últimos SMS recebidos agora", 5),
        ("Verifica as notificações de SMS", 3),
        ("Me mostra os SMS recebidos hoje", 5),
        ("Recebi algum SMS recentemente?", 3),
        ("Silva, consulta as mensagens de texto", 5),
        ("Lê o primeiro SMS da lista", 1),
        ("Quais os últimos 5 SMS no celular?", 5),
        ("Quem me mandou SMS?", 3),
        ("Abre a lista dos últimos SMS", 5),
        ("Checa meus SMS por favor", 5),
        ("Dá uma lida nos últimos torpedos", 5),
        ("Mensagens de texto recentes", 5),
        ("Silva, histórico dos últimos SMS", 10),
        ("Mostra mensagens SMS da operadora", 5),
        ("Confere os SMS recebidos", 5),
        ("Quero ver os últimos SMS", 5),
        ("Lê os três últimos torpedos", 3),
        ("Verifica se recebi algum SMS", 3),
        ("Silva, mostre meus torpedos", 5),
        ("Consulta os SMS mais recentes", 5),
        ("Dá uma olhada no último SMS recebido", 1),
        ("Checa se tem SMS novo", 3),
        ("Lê as mensagens de texto novas", 5),
        ("Vê os últimos 8 SMS recebidos", 8)
    ]
    for p, lim in sms_prompts:
        samples.append({"prompt": p, "completion": f"<call>get_last_sms(limit={lim})</call>"})

    # 2. get_battery (55 amostras)
    battery_prompts = [
        "Silva, quanta bateria ainda tenho?",
        "Qual a porcentagem de carga do celular?",
        "O smartphone está carregando?",
        "Como está a saúde da bateria?",
        "Qual a temperatura da bateria agora?",
        "Quanto por cento de bateria resta?",
        "O telefone tá na tomada?",
        "Verifica o nível da bateria",
        "Status da bateria por favor",
        "A bateria tá esquentando?",
        "Me dá um relatório da bateria",
        "Vê quanta carga ainda tem",
        "O carregamento tá rápido?",
        "Silva, consulta a bateria",
        "Como tá o consumo de bateria?",
        "Quanto resta de carga?",
        "A bateria vai durar até a noite?",
        "O carregador tá conectado?",
        "Verifica se o celular tá na tomada",
        "Dá uma olhada na porcentagem de bateria",
        "Qual é o nível de carga atual?",
        "Silva, checa a bateria do aparelho",
        "O telefone está plugado no carregador?",
        "Qual a saúde da minha bateria?",
        "Bateria tá em quanto?",
        "Quantos porcento ainda temos de bateria?",
        "Vê se a bateria tá acabando",
        "Verifica a temperatura do telefone",
        "Silva, como tá a nossa bateria?",
        "O carregamento tá ativo?",
        "Vê o status da carga do aparelho",
        "A bateria tá com carga cheia?",
        "Quanto tempo falta pra descarregar?",
        "Checa o status da bateria",
        "Como está a energia do celular?",
        "Consulta o nível de energia do aparelho",
        "Silva, me fala a porcentagem da bateria",
        "Verifica se está na tomada carregando",
        "Status de energia do telefone",
        "Bateria está ok?",
        "Quanto por cento tem agora?",
        "O celular tá quente? Vê a temperatura da bateria",
        "Me mostra o status de carregamento",
        "Silva, bateria atual",
        "Vê quanta bateria resta",
        "Qual o status do carregador?",
        "Verifica a carga do celular agora",
        "A bateria já tá em 100%?",
        "O celular está descarregando?",
        "Silva, relatório de bateria",
        "Como tá a porcentagem agora?",
        "Vê se o celular tá carregando",
        "Nível de bateria do smartphone",
        "Checa a energia da bateria",
        "Silva, quanta carga tenho no aparelho?"
    ]
    for p in battery_prompts:
        samples.append({"prompt": p, "completion": "<call>get_battery()</call>"})

    # 3. get_last_location (55 amostras)
    last_loc_prompts = [
        "Onde eu estava pela última vez?",
        "Qual foi a minha última localização registrada?",
        "Mostra a última posição que o GPS salvou",
        "Onde foi a última vez que estive?",
        "Mostra a última localização no mapa",
        "Qual o último local registrado offline?",
        "Onde eu parei o carro pela última vez?",
        "Onde foi meu último registro de GPS?",
        "Consulta o histórico de última localização",
        "Vê onde o celular esteve por último",
        "Qual o último endereço registrado?",
        "Silva, qual foi meu último ponto no mapa?",
        "Onde eu estive antes de desligar o GPS?",
        "Última localização conhecida do aparelho",
        "Mostra no mapa onde estive por último",
        "Silva, onde eu parei?",
        "Qual a última coordenada salva no sistema?",
        "Consulta a última localização salva offline",
        "Onde foi registrada minha última posição?",
        "Vê o último card de localização gravado",
        "Qual foi a última coordenada registrada pelo GPS?",
        "Silva, me mostra o último mapa registrado",
        "Onde o telefone esteve pela última vez?",
        "Localização anterior salva",
        "Mostra a última rota ou ponto registrado",
        "Consulta onde eu estava",
        "Silva, qual a última posição salva?",
        "Me mostra o último lugar que você registrou",
        "Onde eu passei antes?",
        "Qual o último registro geográfico salvo?",
        "Silva, resgata a última localização",
        "Onde estive hoje mais cedo?",
        "Mostra a última posição registrada no dispositivo",
        "Qual foi o último local que você marcou?",
        "Vê a última localização offline salva",
        "Consulta último ponto de GPS registrado",
        "Onde foi a última vez que pegou sinal?",
        "Silva, mostra a localização anterior",
        "Qual a última posição que você lembra?",
        "Onde o celular registrou localização por último?",
        "Resgata a última coordenada do mapa",
        "Silva, qual o último ponto conhecido?",
        "Onde estive pela última vez no mapa?",
        "Consulta última coordenada offline",
        "Vê onde foi que eu parei",
        "Qual a última localização guardada?",
        "Mostra onde estive na última consulta",
        "Silva, busca a última localização gravada",
        "Onde foi meu último check-in offline?",
        "Último local que o Silva registrou",
        "Pega a última localização salva",
        "Consulta o último registro de localização",
        "Silva, qual a posição registrada anteriormente?",
        "Onde eu estava quando o GPS funcionou?",
        "Mostra o mapa da última localização salva"
    ]
    for p in last_loc_prompts:
        samples.append({"prompt": p, "completion": "<call>get_last_location()</call>"})

    # 4. set_clipboard (55 amostras)
    clipboard_texts = [
        ("Copia o texto 'secreto123' pra área de transferência", "secreto123"),
        ("Coloca 'senha@2026' no clipboard", "senha@2026"),
        ("Copia este link https://google.com para o clipboard", "https://google.com"),
        ("Copia o endereço 'Rua das Flores, 123'", "Rua das Flores, 123"),
        ("Salva no clipboard o código 998877", "998877"),
        ("Copia o e-mail contato@empresa.com", "contato@empresa.com"),
        ("Coloca na área de transferência o cupom DESCONTO10", "DESCONTO10"),
        ("Silva, copie o código PIX: 00020126580014br.gov.bcb.pix", "00020126580014br.gov.bcb.pix"),
        ("Copia o número da conta 12345-6 para colar depois", "12345-6"),
        ("Coloca a frase 'Bom dia a todos' no clipboard", "Bom dia a todos"),
        ("Copia o telefone 11988887777 pra área de transferência", "11988887777"),
        ("Guarda no clipboard o código de barras 34191790010104351004791020150008", "34191790010104351004791020150008"),
        ("Copia a mensagem 'Já estou saindo de casa' pro clipboard", "Já estou saindo de casa"),
        ("Silva, coloca o texto 'Reunião confirmada às 15h' na área de transferência", "Reunião confirmada às 15h"),
        ("Copia o CPF 123.456.789-00", "123.456.789-00"),
        ("Coloca a chave de acesso 849201 no clipboard", "849201"),
        ("Copia o link do vídeo https://youtube.com/watch?v=123", "https://youtube.com/watch?v=123"),
        ("Salva 'Avenida Paulista, 1000' na área de transferência", "Avenida Paulista, 1000"),
        ("Silva, copie 'token_auth_xyz999' para colar", "token_auth_xyz999"),
        ("Coloca o CNPJ 00.123.456/0001-99 no clipboard", "00.123.456/0001-99"),
        ("Copia o texto 'Comprar pão e leite' pra área de transferência", "Comprar pão e leite"),
        ("Copia a hashtag #inteligenciaartificial no clipboard", "#inteligenciaartificial"),
        ("Salva a palavra 'abracadabra' no clipboard", "abracadabra"),
        ("Coloca na área de transferência 'Entrega agendada para sexta'", "Entrega agendada para sexta"),
        ("Silva, copie a url https://github.com/silva", "https://github.com/silva"),
        ("Copia o código de rastreio AA123456789BR", "AA123456789BR"),
        ("Coloca 'confirmado' na área de transferência", "confirmado"),
        ("Copia este endereço de IP: 192.168.0.106", "192.168.0.106"),
        ("Salva o e-mail silva@agente.local no clipboard", "silva@agente.local"),
        ("Copia a senha wifi 'InternetFibra2026'", "InternetFibra2026"),
        ("Coloca 'Revisão do código aprovada' no clipboard", "Revisão do código aprovada"),
        ("Silva, copia o nome 'Fernanda Silva' pra área de transferência", "Fernanda Silva"),
        ("Guarda no clipboard o código de desconto 'SILVA50'", "SILVA50"),
        ("Copia a coordenada '-7.9196, -34.8466' pro clipboard", "-7.9196, -34.8466"),
        ("Coloca o texto 'Terminei o relatório' na área de transferência", "Terminei o relatório"),
        ("Copia o número do pedido #987654", "#987654"),
        ("Silva, copie 'https://maps.google.com/?q=recife'", "https://maps.google.com/?q=recife"),
        ("Coloca a placa do carro 'ABC1D23' no clipboard", "ABC1D23"),
        ("Copia a mensagem de aniversário 'Parabéns e muitas felicidades!'", "Parabéns e muitas felicidades!"),
        ("Salva o link da reunião https://meet.google.com/abc-defg-hij no clipboard", "https://meet.google.com/abc-defg-hij"),
        ("Copia o código SMS '548291' pra área de transferência", "548291"),
        ("Coloca a nota 'Lembrar de pagar o condomínio' no clipboard", "Lembrar de pagar o condomínio"),
        ("Silva, copie a palavra chave 'SmolLM2-135M'", "SmolLM2-135M"),
        ("Copia 'Obrigado pelo suporte!' no clipboard", "Obrigado pelo suporte!"),
        ("Coloca 'Protocolo de atendimento 2026112101' na área de transferência", "Protocolo de atendimento 2026112101"),
        ("Copia o texto 'Desenvolvedor Full Stack' pra colar", "Desenvolvedor Full Stack"),
        ("Salva no clipboard a cotação 'Dólar R$ 5,65'", "Dólar R$ 5,65"),
        ("Copia o nome da rua 'Rua do Sol, 45' no clipboard", "Rua do Sol, 45"),
        ("Silva, copia a mensagem 'Te vejo às 19h no restaurante'", "Te vejo às 19h no restaurante"),
        ("Coloca 'Aprovado por unanimidade' na área de transferência", "Aprovado por unanimidade"),
        ("Copia a chave Pix 'fernanda@pix.com.br'", "fernanda@pix.com.br"),
        ("Salva o código OTP 443210 no clipboard", "443210"),
        ("Copia o texto 'Finalizado com sucesso' pra área de transferência", "Finalizado com sucesso"),
        ("Coloca 'Consulta marcada para segunda 09h' no clipboard", "Consulta marcada para segunda 09h"),
        ("Silva, copie a frase 'A IA offline mais rápida do Android'", "A IA offline mais rápida do Android")
    ]
    for p, txt in clipboard_texts:
        samples.append({"prompt": p, "completion": f'<call>set_clipboard(text="{txt}")</call>'})

    # 5. take_screenshot (35 amostras)
    screenshot_prompts = [
        "Silva, tira um print da tela",
        "Faz uma captura de tela agora",
        "Manda um print da tela do celular",
        "Tira screenshot da tela atual",
        "Captura a tela do smartphone",
        "Silva, bate um print pra mim",
        "Salva uma captura da tela",
        "Tira print dessa conversa",
        "Registra a tela atual em imagem",
        "Faz um print rápido da tela",
        "Silva, captura a tela",
        "Tira um screenshot agora",
        "Manda print aí por favor",
        "Pode tirar print da tela?",
        "Captura a tela inteira do celular",
        "Tira foto da tela atual",
        "Faz uma captura de tela do telefone",
        "Salva screenshot na galeria",
        "Silva, tira um print dessa tela",
        "Print da tela por favor",
        "Faz screenshot do smartphone",
        "Captura de tela imediata",
        "Silva, tira uma foto da tela do aparelho",
        "Grava a tela em imagem print",
        "Bate print do que tá na tela",
        "Tira um print screen agora",
        "Screenshot da tela do Android",
        "Silva, captura o que tá aparecendo na tela",
        "Faz uma foto da tela",
        "Tira screenshot do visor",
        "Manda uma captura dessa tela",
        "Bate uma captura da tela",
        "Print screen do telefone",
        "Silva, captura imagem da tela",
        "Tira print rapidinho"
    ]
    for p in screenshot_prompts:
        samples.append({"prompt": p, "completion": "<call>take_screenshot()</call>"})

    # 6. record_video (35 amostras)
    video_configs = [
        ("Silva, grava um vídeo de 10 segundos", 10, 0),
        ("Filma com a câmera frontal por 15 segundos", 15, 1),
        ("Grava um vídeo de 30 segundos com a câmera traseira", 30, 0),
        ("Faz um vídeo rápido de 5 segundos selfie", 5, 1),
        ("Grava um vídeo de 20 segundos", 20, 0),
        ("Filma por 1 minuto na câmera de trás", 60, 0),
        ("Grava 15 segundos de vídeo na câmera de selfie", 15, 1),
        ("Faz uma gravação de vídeo de 10 segundos", 10, 0),
        ("Filma a frente por 10 segundos", 10, 1),
        ("Silva, grave um vídeo de 45 segundos", 45, 0),
        ("Grava um vídeo selfie de 20 segundos", 20, 1),
        ("Inicia gravação de vídeo de 30s", 30, 0),
        ("Faz um vídeo de 15 segundos com a câmera principal", 15, 0),
        ("Grava um vídeo da câmera frontal por 30 segundos", 30, 1),
        ("Filma com a traseira durante 10 segundos", 10, 0),
        ("Silva, grava um vídeo de 5 segundos", 5, 0),
        ("Grava um vídeo de 25 segundos", 25, 0),
        ("Filma a gente com a frontal por 15s", 15, 1),
        ("Grava um vídeo de 40 segundos", 40, 0),
        ("Faz um vídeo de 8 segundos na frontal", 8, 1),
        ("Grava um vídeo com a câmera traseira por 50 segundos", 50, 0),
        ("Filma com a câmera de selfie por 12 segundos", 12, 1),
        ("Silva, grava um vídeo curto de 6 segundos", 6, 0),
        ("Faz uma filmagem de 20 segundos", 20, 0),
        ("Grava um vídeo frontal de 10 segundos", 10, 1),
        ("Filma por 35 segundos", 35, 0),
        ("Grava um vídeo de 15 segundos pra mim", 15, 0),
        ("Faz um vídeo rápido com a câmera da frente de 5s", 5, 1),
        ("Silva, grava vídeo de 10 segundos na traseira", 10, 0),
        ("Filma 30 segundos na câmera frontal", 30, 1),
        ("Grava um clipe de 15 segundos", 15, 0),
        ("Faz uma gravação frontal de 20 segundos", 20, 1),
        ("Filma por 10 segundos com a câmera principal", 10, 0),
        ("Silva, grava 5 segundos de vídeo selfie", 5, 1),
        ("Gravação de vídeo por 15 segundos", 15, 0)
    ]
    for p, dur, cam in video_configs:
        samples.append({"prompt": p, "completion": f"<call>record_video(duration={dur}, camera_id={cam})</call>"})

    # 7. set_location_state (35 amostras)
    loc_state_configs = [
        ("Silva, liga a localização do celular", True),
        ("Desativa o GPS do aparelho", False),
        ("Ativa o serviço de localização agora", True),
        ("Desliga a localização por favor", False),
        ("Pode ligar o GPS?", True),
        ("Desativa o GPS para economizar bateria", False),
        ("Silva, ative a localização", True),
        ("Desliga o rastreamento por GPS", False),
        ("Liga o GPS do smartphone", True),
        ("Desativa a localização do telefone", False),
        ("Ativa o GPS do celular", True),
        ("Desliga a localização agora", False),
        ("Habilita o serviço de GPS", True),
        ("Desabilita a localização", False),
        ("Silva, liga o sensor de localização", True),
        ("Desliga o sensor de GPS", False),
        ("Pode ativar a localização do celular?", True),
        ("Desativa a localização por gentileza", False),
        ("Liga a localização pra eu usar o mapa", True),
        ("Desliga o GPS agora por favor", False),
        ("Silva, coloca a localização como ativa", True),
        ("Desativa o sinal de GPS", False),
        ("Ativa o GPS pra mim", True),
        ("Desativa a localização do Android", False),
        ("Ligue a localização do aparelho", True),
        ("Desligue o GPS do smartphone", False),
        ("Aciona o GPS do celular", True),
        ("Corta a localização do telefone", False),
        ("Silva, quero a localização ligada", True),
        ("Quero a localização desligada", False),
        ("Liga o posicionamento por GPS", True),
        ("Desliga o posicionamento por satélite", False),
        ("Habilita o GPS", True),
        ("Desabilita o GPS", False),
        ("Ativa a localização do aparelho", True)
    ]
    for p, st in loc_state_configs:
        samples.append({"prompt": p, "completion": f"<call>set_location_state(state={st})</call>"})

    # 8. get_weather (35 amostras)
    weather_configs = [
        ("Silva, como tá o clima hoje?", "hoje", "", ""),
        ("Qual é a previsão do tempo para amanhã em Olinda?", "amanhã", "", "Olinda"),
        ("Vai chover às 18:00 em Recife?", "hoje", "18:00", "Recife"),
        ("Como vai estar o tempo no sábado à tarde?", "sábado", "tarde", ""),
        ("Previsão do tempo para amanhã em Paulista", "amanhã", "", "Paulista"),
        ("Qual a temperatura em São Paulo hoje?", "hoje", "", "São Paulo"),
        ("Vai fazer calor no domingo de manhã?", "domingo", "manhã", ""),
        ("Como tá o clima em Fortaleza agora?", "hoje", "", "Fortaleza"),
        ("Vai chover amanhã à noite?", "amanhã", "noite", ""),
        ("Qual a previsão do tempo para domingo?", "domingo", "", ""),
        ("Como vai estar o tempo na segunda-feira?", "segunda-feira", "", ""),
        ("Tem previsão de chuva para hoje às 15h?", "hoje", "15:00", ""),
        ("Temperatura atual na minha cidade", "hoje", "", ""),
        ("Como tá o clima em Belo Horizonte?", "hoje", "", "Belo Horizonte"),
        ("Previsão meteorológica para sexta-feira", "sexta-feira", "", ""),
        ("Vai chover hoje à tarde em Salvador?", "hoje", "tarde", "Salvador"),
        ("Qual a temperatura máxima prevista para amanhã?", "amanhã", "", ""),
        ("Como vai ser o tempo no fim de semana?", "sábado", "", ""),
        ("Previsão do tempo para Brasília hoje", "hoje", "", "Brasília"),
        ("Vai ter tempestade hoje às 20h?", "hoje", "20:00", ""),
        ("Qual a previsão do tempo em Curitiba para amanhã?", "amanhã", "", "Curitiba"),
        ("Como tá o tempo lá fora?", "hoje", "", ""),
        ("Vai chover no sábado à noite em Florianópolis?", "sábado", "noite", "Florianópolis"),
        ("Qual a probabilidade de chuva amanhã?", "amanhã", "", ""),
        ("Previsão do tempo para quarta-feira de manhã", "quarta-feira", "manhã", ""),
        ("Como estará o clima na quinta em Manaus?", "quinta-feira", "", "Manaus"),
        ("Vai esfriar hoje à noite?", "hoje", "noite", ""),
        ("Previsão do tempo hoje para o Rio de Janeiro", "hoje", "", "Rio de Janeiro"),
        ("Como tá o clima na praia amanhã às 10h?", "amanhã", "10:00", ""),
        ("Qual a previsão de tempo para Porto Alegre hoje?", "hoje", "", "Porto Alegre"),
        ("Vai fazer sol no domingo à tarde em Natal?", "domingo", "tarde", "Natal"),
        ("Previsão do tempo para hoje à noite", "hoje", "noite", ""),
        ("Como tá o clima em João Pessoa agora?", "hoje", "", "João Pessoa"),
        ("Qual a temperatura prevista para as 12:00?", "hoje", "12:00", ""),
        ("Silva, vai chover amanhã de tarde?", "amanhã", "tarde", "")
    ]
    for p, d, t, loc in weather_configs:
        samples.append({"prompt": p, "completion": f'<call>get_weather(day="{d}", time="{t}", location="{loc}")</call>'})

    return samples


def main():
    print("=" * 65)
    print(" SILVA AGENT — REPARO E BALANCEAMENTO DO TRAIN.JSONL ")
    print("=" * 65)

    tools_schema = load_schema(SCHEMA_PATH)
    print(f"[*] Schema carregado com {len(tools_schema)} ferramentas.")

    if not TRAIN_PATH.is_file():
        print(f"[ERRO] {TRAIN_PATH} não encontrado!")
        return

    # 1. Backup
    shutil.copyfile(TRAIN_PATH, BACKUP_PATH)
    print(f"[*] Backup salvo em {BACKUP_PATH.name}")

    # 2. Leitura e correção
    fixed_samples = []
    lines_read = 0
    with open(TRAIN_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            lines_read += 1
            item = json.loads(line)
            fixed_item = fix_line(item)
            fixed_samples.append(fixed_item)

    print(f"[*] Linhas lidas e corrigidas de train.jsonl: {len(fixed_samples)} de {lines_read}")

    # 3. Adiciona enriquecimento
    enrichment = generate_enrichment_samples()
    print(f"[*] Geradas {len(enrichment)} novas amostras de enriquecimento para classes com baixa contagem.")
    fixed_samples.extend(enrichment)

    # 4. Deduplicação e validação estrita
    print("[*] Validando e deduplicando amostras...")
    seen = set()
    final_samples = []
    invalid_count = 0

    for item in fixed_samples:
        p = item["prompt"].strip()
        comp = item["completion"].strip()
        p_clean = " ".join(p.lower().split())

        if p_clean in seen:
            continue

        # Validação regex e AST
        matches = CALL_TAG_REGEX.findall(comp)
        if not matches:
            invalid_count += 1
            continue

        is_valid = True
        for fn, args_raw in matches:
            if fn not in tools_schema:
                is_valid = False
                break
            try:
                expr = ast.parse(f"call({args_raw})", mode="eval")
                kwargs = {kw.arg: ast.literal_eval(kw.value) for kw in expr.body.keywords}
            except Exception:
                is_valid = False
                break
            pdef = tools_schema[fn].get("parameters", {})
            for a in kwargs:
                if a not in pdef:
                    is_valid = False
                    break
            for p_req, meta in pdef.items():
                if meta.get("required") and p_req not in kwargs:
                    is_valid = False
                    break
            if not is_valid:
                break

        if not is_valid:
            invalid_count += 1
            continue

        seen.add(p_clean)
        final_samples.append(item)

    print(f"[*] Total de amostras finais válidas e únicas: {len(final_samples)} (Inválidas descartadas: {invalid_count})")

    # 5. Salva novo train.jsonl
    with open(TRAIN_PATH, "w", encoding="utf-8") as f:
        for item in final_samples:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"[OK] {TRAIN_PATH.name} regravado com sucesso ({len(final_samples)} linhas)!")


if __name__ == "__main__":
    main()
