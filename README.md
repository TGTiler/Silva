# 🤖 Silva — Micro-Agente Autônomo Offline para Android

O **Silva** é um micro-agente de Inteligência Artificial **100% offline, privado e ultraleve**, projetado para rodar nativamente em smartphones Android utilizando o **Termux** e a **Termux:API**.

Diferente de assistentes convencionais dependentes de nuvem ou bots de mensagens externas, o Silva opera diretamente na borda (*edge computing*) utilizando um micro-modelo de linguagem quantizado em formato **GGUF** de **~105 MB** (`Q5_K_M`), atuando estritamente como um **roteador semântico de *Function Calling***: ele interpreta comandos de voz/texto em linguagem natural (Português do Brasil) e emite chamadas de função tipadas `<call>funcao(args)</call>` para orquestrar o hardware, aplicativos e sensores do dispositivo com latência de milissegundos.

O sistema conta com um **servidor web nativo** com interface moderna inspirada em assistentes como Claude, ChatGPT e DeepSeek (design minimalista, tema escuro refinado, sidebar retrátil com histórico de conversas em `localStorage` e badges de telemetria), **100% offline (sem CDNs externos)**, acessível tanto no navegador do próprio celular (`http://localhost:5000`) quanto em computadores na mesma rede Wi-Fi (`http://<IP-DO-CELULAR>:5000`).

---

## 📊 Estatísticas e Parâmetros do Projeto

| Dimensão | Especificação | Detalhes |
| :--- | :--- | :--- |
| **Parâmetros do Modelo (LLM)** | **134.515.008 parâmetros** (~134.5M) | Arquitetura baseada em `HuggingFaceTB/SmolLM2-135M-Instruct` |
| **Quantização Móvel** | **Q5_K_M (Medium)** | ~105 MB de tamanho em disco, ideal para dispositivos ARM64 |
| **Janela de Contexto** | **2.048 tokens** | Espaço amplo para System Prompt completo + histórico de ações |
| **Vocabulário** | **49.152 tokens** | Tokenizador ChatML nativo |
| **Ferramentas Nativas (Tools)** | **39 ferramentas** | Controle de hardware, utilitários, sensores, mobilidade, delivery, mídia, redes Wi-Fi, apps e ajuda |
| **Parâmetros de Ferramentas** | **44 parâmetros formais** | Catalogados e tipados estritamente no `dataset/schema.json` |
| **Base de Dados de Treino** | **6.381 amostras limpas** | 100% validadas por analisador sintático AST em PT-BR (0 erros) |

---

## 🏛️ Arquitetura do Sistema

```text
                                  ┌──────────────────────────────┐
                                  │      Usuário (Mobile/PC)     │
                                  │   Interface Web / Terminal   │
                                  └──────────────┬───────────────┘
                                                 │ HTTP /api/chat (X-Access-Pin)
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             Ambiente Android (Termux)                            │
│                                                                                  │
│   ┌─────────────────────────┐               ┌────────────────────────────────┐   │
│   │   Web Server (Python)   │──────────────▶│   Silva LLM Client (urllib)    │   │
│   │   ThreadingHTTPServer   │               └───────────────┬────────────────┘   │
│   └────────────┬────────────┘                               │ POST /completion   │
│                │                                            ▼                    │
│                │                             ┌───────────────────────────────┐   │
│                │                             │  llama-server (porta 8080)    │   │
│                │                             │  silva-135m.gguf (Q5_K_M)     │   │
│                │                             └──────────────┬────────────────┘   │
│                │                                            │ <call>func()</call>│
│                ▼                                            ▼                    │
│   ┌─────────────────────────┐               ┌────────────────────────────────┐   │
│   │   Tools.py (Termux:API) │◀──────────────│   Parser AST & Whitelist       │   │
│   └────────────┬────────────┘               └────────────────────────────────┘   │
│                │                                                                 │
│                ▼ Subprocessos seguros e Intent Viewers                            │
│   [GPS/Mapa] [Câmera/Vídeo] [Clima] [Bateria] [Lanterna] [SMS] [Chamadas]       │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 🛠️ Catálogo Completo das 39 Ferramentas

O Silva possui 39 ferramentas implementadas no pacote modular `android_agent/tools/` e catalogadas formalmente em `dataset/schema.json`:

| # | Ferramenta | Parâmetros (44 no total) | Descrição do Hardware / Função |
| :-: | :--- | :--- | :--- |
| **1** | `get_battery()` | *Nenhum* | Consulta status, porcentagem, temperatura e saúde da bateria. |
| **2** | `get_last_sms(limit)` | `limit` (int, padrão: 5) | Lê as últimas mensagens SMS recebidas na caixa de entrada. |
| **3** | `send_sms(number, message)` | `number` (str, obrigatório), `message` (str, obrigatório) | Envia SMS para número com DDD ou contato da agenda. |
| **4** | `take_photo(camera_id)` | `camera_id` (int: 0=traseira, 1=frontal) | Tira foto com câmera traseira ou frontal (selfie). |
| **5** | `record_video(duration, camera_id)` | `duration` (int: 3 a 120s), `camera_id` (int: 0 ou 1) | Grava vídeo nativo e disponibiliza player no chat. |
| **6** | `take_screenshot()` | *Nenhum* | Tira print da tela do celular via ADB local, Shizuku ou keyevent nativo. |
| **7** | `open_app(app_name)` | `app_name` (str, obrigatório) | Abre aplicativos pelo nome popular (WhatsApp, TikTok, etc.). |
| **8** | `make_call(number)` | `number` (str, obrigatório) | Realiza chamada telefônica direta via discador nativo. |
| **9** | `get_location()` | *Nenhum* | Obtém coordenadas GPS atuais e renderiza card visual de mapa. |
| **10** | `get_last_location()` | *Nenhum* | Consulta a última localização salva offline mesmo com GPS desligado. |
| **11** | `set_location_state(state)` | `state` (bool, obrigatório) | Liga ou desliga o serviço de GPS/localização do aparelho. |
| **12** | `get_weather(day, time, location)` | `day` (str), `time` (str), `location` (str) | Previsão do tempo detalhada via Open-Meteo (PT-BR). |
| **13** | `search_google(query, open_browser)` | `query` (str, obrigatório), `open_browser` (bool, padrão: False) | Pesquisa multi-fonte em cascata real na web (Wikipédia PT-BR semântica + Google News RSS nativo + DuckDuckGo Lite) com card visual estruturado no chat e abertura opcional no navegador. |
| **14** | `set_torch(state)` | `state` (bool, obrigatório) | Liga (`True`) ou desliga (`False`) a lanterna traseira. |
| **15** | `set_dnd(state)` | `state` (bool, obrigatório) | Ativa ou desativa modo Não Perturbe / Silencioso. |
| **16** | `vibrate(duration_ms)` | `duration_ms` (int, padrão: 500) | Aciona vibração háptica no aparelho pelo tempo informado. |
| **17** | `get_clipboard()` | *Nenhum* | Lê o conteúdo textual copiado na área de transferência. |
| **18** | `set_clipboard(text)` | `text` (str, obrigatório) | Copia texto especificado para a área de transferência. |
| **19** | `tell_joke()` | *Nenhum* | Retorna piada divertida do banco offline em PT-BR. |
| **20** | `set_alarm(time, label, days)` | `time` (str, obrigatório), `label` (str), `days` (str) | Agenda alarme no relógio nativo do Android. |
| **21** | `cancel_alarm(time, day, label)` | `time` (str), `day` (str), `label` (str) | Cancela ou descarta alarme configurado. |
| **22** | `schedule_event(title, date, time)`| `title` (str, obrigatório), `date` (str), `time` (str) | Cria compromisso na agenda local + Intent direta no Calendário Samsung. |
| **23** | `remember_note(key, value)` | `key` (str, obrigatório), `value` (str, obrigatório) | Salva/atualiza notas na memória relacional SQLite FTS5 (ou remove se valor for vazio). |
| **24** | `recall_note(query)` | `query` (str, obrigatório) | Busca híbrida (FTS5 BM25 + LIKE) de anotações e compromissos passados. |
| **25** | `get_notifications(app)` | `app` (str, opcional) | Lê notificações recentes da barra de status do Android. |
| **26** | `set_volume(stream, level)` | `stream` (str: media/ring/alarm), `level` (int: 0-100) | Ajusta volume por canal de áudio em porcentagem. |
| **27** | `set_brightness(level)` | `level` (int: 0 a 100, obrigatório) | Ajusta o brilho da tela do smartphone de 0% a 100%. |
| **28** | `set_timer(minutes, label)` | `minutes` (int, obrigatório), `label` (str) | Inicia timer ou cronômetro no relógio do Android. |
| **29** | `calculate(expression)` | `expression` (str, obrigatório) | Calculadora científica e financeira AST (raízes, trigonométricas, log, fatorial, porcentagem). |
| **30** | `request_ride(destination, app)` | `destination` (str, obrigatório), `app` (str, padrão: "uber") | Abre app de transporte (Uber ou 99) com o destino configurado a partir da localização atual. |
| **31** | `order_food(query, app)` | `query` (str, obrigatório), `app` (str, padrão: "ifood") | Abre app de delivery (iFood ou 99) buscando o prato, restaurante ou item pedido. |
| **32** | `install_app(app_name)` | `app_name` (str, obrigatório) | Abre a Google Play Store diretamente na página de instalação ou pesquisa do app. |
| **33** | `media_control(action)` | `action` (str, obrigatório: play/pause/next/previous) | Controla a reprodução de mídia nativamente (`cmd media_session` e KeyEvents). |
| **34** | `scan_wifi()` | *Nenhum* | Escaneia redes Wi-Fi próximas, identificando sinal (dBm e %), frequência, segurança e rede conectada. |
| **35** | `connect_wifi(ssid, password)` | `ssid` (str, obrigatório), `password` (str, opcional) | Conecta a uma rede Wi-Fi direta ou via fallback seguro com cópia de credencial e salvamento em SQLite. |
| **36** | `get_wifi_info()` | *Nenhum* | Obtém informações detalhadas da conexão Wi-Fi atual (SSID, IP local, sinal %, dBm e link web). |
| **37** | `set_wifi_state(state)` | `state` (bool, obrigatório) | Ativa ou desativa a interface Wi-Fi do smartphone via Termux:API e fallback svc. |
| **38** | `list_capabilities()` | *Nenhum* | Retorna guia organizado de todas as funções e comandos do Silva com exemplos práticos. |
| **39** | `none()` | *Nenhum* | Emissão neutra para saudações e conversas gerais. |

---

## 📁 Estrutura Detalhada dos Arquivos do Projeto

Abaixo está a documentação explicativa de cada componente do repositório:

```text
silva-agent/
├── README.md                      # Documentação completa, arquitetura e guias
├── .gitignore                     # Protege o Git contra uploads pesados (>100MB)
├── .env.example                   # Template de variáveis de ambiente e portas
│
├── android_agent/                 # RUNTIME DE PRODUÇÃO NO SMARTPHONE (TERMUX)
│   ├── main.py                    # Ponto de entrada (CLI para terminal ou Web Server)
│   ├── web_server.py              # Servidor HTTP multithread nativo com endpoints REST
│   ├── scheduler.py               # Agendador daemon em background para lembretes de agenda
│   ├── llm_client.py              # Cliente HTTP para o llama-server local com fallback
│   ├── intent_fallback.py         # Roteador determinístico de ultra-baixa latência (<2ms)
│   ├── nlp/                       # Pacote de Processamento de Linguagem Natural (PT-BR)
│   │   ├── numbers.py             # Pilar A: Parser numérico composto (centenas, multiplicadores, horários)
│   │   ├── colloquial.py          # Pilar B: Normalizador de gírias, níveis ("no talo", "total") e typos com difflib
│   │   └── router.py              # Pilar C: Roteador por pontuação (ScoredIntentRouter) com tolerância a typos matemáticos e recall restrito
│   ├── parser.py                  # Analisador sintático AST seguro, validador de whitelist e propagação de status
│   ├── voice_assistant.py         # Módulo opcional de voz offline (Vosk vosk-model-small-pt-0.3 + notificação 24/7)
│   ├── tools/                     # Pacote modular das 39 ferramentas auditado via AST (core, hardware, media, comms, etc)
│   ├── config.py                  # Configurações globais, portas, PIN e System Prompt das 39 tools
│   ├── setup_termux.sh            # Instalação automática de dependências e build do llama.cpp
│   ├── start_silva.sh             # Script de inicialização (llama-server + web_server + voz opcional)
│   ├── captures/                  # Armazena fotos, vídeos, prints e mapas gerados
│   ├── data/                      # Persistência: banco relacional SQLite FTS5 (memory.db), events.json e localização
│   ├── models/                    # Pasta onde reside o micro-modelo silva-135m.gguf
│   └── static/
│       └── index.html             # Interface web responsiva (Desktop/Mobile, dark mode, zero CDNs)
│
├── dataset/                       # ENGENHARIA DE DADOS E VALIDAÇÃO
│   ├── schema.json                # Especificação JSON Schema formal das 39 ferramentas
│   ├── seed_examples.jsonl        # 133 exemplos canônicos de referência em PT-BR
│   ├── train.jsonl                # Dataset de treino consolidado
│   ├── train_clean.jsonl          # 95% do dataset limpo para fine-tuning supervisionado (5.790)
│   ├── eval_clean.jsonl           # 5% do dataset para avaliação e validação de perda (304)
│   ├── silva_colab_dataset.jsonl  # 6.381 amostras consolidadas para treino no Google Colab
│   ├── validate_dataset.py        # Validador sintático AST e verificador de schema estrito
│   ├── prepare_final_dataset.py   # Gerador de contatos sintéticos, balanceador e divisor
│   └── repair_train_dataset.py    # Corretor automático de inconsistências e desbalanceamento
│
├── tests/                         # SUÍTE DE TESTES AUTOMATIZADOS (32 TESTES 100% PASSANDO)
│   ├── test_contracts.py          # Sincronização de schema (39 tools), prompt e conformidade do dataset
│   ├── test_parser_and_fallback.py# Testes de AST, whitelist, fallback e tolerância a typos/sinônimos
│   ├── test_tools_and_memory.py   # Testes de SQLite FTS5, calculadora e smoke test de todas as 39 ferramentas
│   ├── test_voice_assistant.py    # Testes do assistente de voz offline, estados e notificações
│   └── test_web_server.py         # Testes HTTP, autenticação por PIN e proteção Path Traversal
│
└── pc_training/                   # PIPELINE DE FINE-TUNING E QUANTIZAÇÃO GGUF
    ├── colab_train_silva.py       # Script autônomo completo para Google Colab (GPU T4)
    ├── train_sft.py               # Fine-tuning supervisionado local (CPU FP32 / DirectML)
    ├── export_gguf.py             # Fusão de pesos LoRA e conversão para GGUF quantizado
    └── requirements_pc.txt        # Dependências Python para máquinas de treino
```

### Detalhamento por Módulo:

#### 1. Módulo `android_agent/` (Execução no Celular)
- **`main.py`**: Gerencia os argumentos de linha de comando. Permite iniciar o agente no modo `--web` (padrão) para abrir o servidor de rede local ou `--cli` para interagir diretamente pelo terminal do Termux.
- **`web_server.py`**: Construído sobre `ReusableThreadingHTTPServer` com `SO_REUSEADDR` e threads daemon, garantindo reutilização imediata de portas e encerramento limpo via `SIGINT`/`SIGTERM`. Possui fallback automático de porta (`port` a `port+5`) caso a porta configurada esteja ocupada. Trata requisições para a API `/api/chat`, valida o cabeçalho de segurança `X-Access-Pin`, serve arquivos estáticos e mapeia arquivos multimídia da pasta `captures/`.
- **`start_silva.sh`**: Script de boot resiliente e idempotente. Executa limpeza cirúrgica de instâncias órfãs antigas do `llama-server` e `main.py`, gerencia PIDs via `data/llama.pid` e `data/web.pid`, respeita a variável `WEB_PORT` do `.env` e implementa `trap cleanup EXIT INT TERM` unificado.
- **`scheduler.py`**: Thread daemon em background que monitora compromissos salvos localmente (`events.json`) a cada 30 segundos, disparando notificações nativas (`termux-notification`) e vibração no horário exato do lembrete.
- **`llm_client.py`**: Interage com o `llama-server` rodando em `127.0.0.1:8080`. Se o modelo demorar ou antes mesmo da chamada, o `match_intent_fallback` processa intenções imediatas em menos de 2 milissegundos.
- **`intent_fallback.py` e `nlp/`**: Motor determinístico de alta velocidade (<2ms) reestruturado em 4 pilares: Parser Numérico Composto (`parse_ptbr_numbers`), Normalizador de Gírias e Typos (`normalize_colloquial_ptbr`), Roteador por Pontuação (`ScoredIntentRouter`) cobrindo as 39 ferramentas e Splitter Inteligente de cláusulas compostas. Trata números por extenso de zero a milhões, gírias de celular ("no talo", "zap", "insta"), erros de digitação ("baterria", "lanterana"), previsão do tempo inteligente, cálculo científico e ecossistema Wi-Fi completo.
- **`parser.py`**: Utiliza o módulo `ast` (Abstract Syntax Tree) para validar e inspecionar os argumentos emitidos na tag `<call>`. Evita injeção de código, checa a whitelist de permissões (`AVAILABLE_TOOLS`) e propaga o status real das chamadas (`ok`, `partial_error`, `error`).
- **`tools/`**: Conector entre a inteligência e o Android. Pacote modular que executa 39 ferramentas nativas divididas em 8 domínios (`core`, `hardware`, `media`, `comms`, `weather_web`, `apps_mobility`, `memory_schedule`, `__init__`), auditado contra símbolos não definidos via AST. Inclui: varredura de Wi-Fi (`scan_wifi`), conexão com salvamento seguro (`connect_wifi`), telemetria de rede (`get_wifi_info`), toggle Wi-Fi (`set_wifi_state`), memória persistente SQLite FTS5 (`remember_note`/`recall_note`), calculadora científica segura via AST (`calculate`), busca web multi-fonte (`search_google`), consultas à bateria, câmera, GPS com mapa Pillow, previsão do tempo Open-Meteo, deep links de transporte (`request_ride`) e delivery (`order_food`), discador nativo, controle de volume/mídia e lanterna.
- **`config.py`**: Centraliza os parâmetros de configuração: porta do servidor (padrão `5000`), PIN de autenticação (`1234`), parâmetros opcionais de voz (`ENABLE_VOICE_MODE`, `WHISPER_BIN_PATH`, etc.) e o `SILVA_SYSTEM_PROMPT` sincronizado para as 39 ferramentas.
- **`voice_assistant.py`**: Módulo opcional de comando por voz offline. Opera em segundo plano através de notificação persistente 24/7 do Termux (`--id silva_voice`) com botões 'Falar' (`--action start`) e 'Parar' (`--action stop`), gravação local via `termux-microphone-record`, conversão via `ffmpeg`, reconhecimento local de alta precisão via **Vosk (`vosk-model-small-pt-0.3`)** otimizado com vocabulário/gramática prioritária das **39 ferramentas**, aplicativos e numerais PT-BR, despacho direto para `/api/chat` com `X-Access-Pin`, atualização dinâmica da notificação e leitura opcional em voz alta via `termux-tts-speak`.
- **`static/index.html`**: Interface web inspirada no Claude/ChatGPT/DeepSeek com design minimalista dark mode, sidebar retrátil com histórico de chats persistido em `localStorage`, telemetria de latência e status do modelo/hardware, cards de ações rápidas, visualizador de mídia integrado e 100% offline (zero CDNs).

#### 2. Módulo `dataset/` (Dados de Treinamento)
- **`schema.json`**: Contrato estrito que rege a estrutura do micro-agente. Define formalmente parâmetros obrigatórios, opcionais e tipos (string, integer, boolean) para as 39 ferramentas (44 parâmetros).
- **`validate_dataset.py`**: Analisa arquivos `.jsonl` linha por linha, extrai chamadas via regex, compila os argumentos via AST e emite relatórios de conformidade estrita e proporção percentual de classes (com validação estrita de tipos inteiros).
- **`prepare_final_dataset.py`**: Enriquece a base com variações naturais de contatos humanos (ex: *"Mãe"*, *"Amor"*, *"Doutor Carlos"*), remove duplicatas e gera a divisão treino (95%) e validação (5%).
- **`silva_colab_dataset.jsonl`**: Arquivo final consolidado com 6.381 exemplos prontos para upload e treino no Colab (100% válidos contra o schema das 39 ferramentas).
- **`PASSO_A_PASSO.md`**: Guia prático passo a passo para o usuário adicionar novos exemplos, recriar os datasets e validar a integridade sintática de forma 100% autônoma.

#### 3. Módulo `pc_training/` (Treino e Conversão)
- **`colab_train_silva.py`**: Pipeline tudo-em-um para o Google Colab: desinstala pacotes conflitantes, atualiza Hugging Face, clona e compila `llama-quantize` no `llama.cpp`, realiza fine-tuning LoRA calibrado (4 épocas, janela 1024 tokens, batch micro 4 com 8 acumulações = 32 efetivo, `gradient_checkpointing=True`, `learning_rate=3e-4`, split determinístico 95/5, mascaramento manual de prompt `labels=-100`, separação estrita `pad_token != eos_token`, `DataCollatorForSeq2Seq` e `load_best_model_at_end=True`), valida 10 cenários de inferência via ChatML, funde pesos no modelo SmolLM2-135M, quantiza em `Q5_K_M` e dispara o download automático de `silva-135m.gguf`.

---

## 🚀 Como Executar o Silva no Android (Termux)

### 1. Preparação no Celular
1. Instale o **Termux** e o **Termux:API** pelo [F-Droid](https://f-droid.org/).
2. Abra as configurações do Android > Aplicativos > **Termux:API** > Permissões e conceda acesso para: **Câmera**, **Localização**, **SMS**, **Telefone** e **Armazenamento**.

### 2. Instalação
No terminal do Termux, clone o repositório:
```bash
git clone https://github.com/TGTiler/Silva.git
cd Silva/silva-agent/android_agent
chmod +x setup_termux.sh start_silva.sh
./setup_termux.sh
```

### 3. Inserção do Modelo e Inicialização
Coloque o arquivo `silva-135m.gguf` dentro de `android_agent/models/` (diretamente no celular ou via ADB do PC com `adb push silva-135m.gguf /sdcard/Download/`) e execute:
```bash
./start_silva.sh
```

O terminal exibirá o endereço para acesso no navegador:
- **No celular:** `http://localhost:5000`
- **No computador (mesmo Wi-Fi):** `http://<IP-DO-CELULAR>:5000`
- **PIN de Acesso Padrão:** `1234`

---

## ⚡ Como Treinar Novamente no Google Colab

1. Acesse o [Google Colab](https://colab.research.google.com/) e ative um ambiente com **GPU T4** (*Ambiente de execução > Alterar tipo de ambiente de execução > GPU T4*).
2. Cole e execute o código de [colab_train_silva.py](pc_training/colab_train_silva.py).
3. Na etapa de upload, envie o arquivo [silva_colab_dataset.jsonl](dataset/silva_colab_dataset.jsonl).
4. O notebook treinará o modelo, converterá e baixará automaticamente o novo arquivo `silva-135m.gguf`.

---

## 🔒 Privacidade e Segurança

- **100% Offline:** Nenhuma gravação de áudio, imagem capturada, SMS ou coordenada sai do dispositivo para servidores externos.
- **PIN de Acesso Local:** Proteção no cabeçalho HTTP contra acessos não autorizados por outros aparelhos na mesma rede local.
- **Execução Sandboxed:** Todas as chamadas de função são validadas por parser AST estrito antes da execução em subprocesso seguro.
