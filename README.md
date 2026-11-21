# 🤖 Silva — Micro-Agente Autônomo Offline para Android

O **Silva** é um micro-agente de Inteligência Artificial **100% offline, privado e ultraleve**, projetado para rodar nativamente em smartphones Android utilizando o **Termux** e a **Termux:API**.

Diferente de assistentes convencionais dependentes de nuvem ou bots de mensagens externas, o Silva opera diretamente na borda (*edge computing*) utilizando um micro-modelo de linguagem quantizado em formato **GGUF** de **~105 MB** (`Q5_K_M`), atuando estritamente como um **roteador semântico de *Function Calling***: ele interpreta comandos de voz/texto em linguagem natural (Português do Brasil) e emite chamadas de função tipadas `<call>funcao(args)</call>` para orquestrar o hardware, aplicativos e sensores do dispositivo com latência de milissegundos.

O sistema conta com um **servidor web nativo** com interface moderna *dark mode* (tons de roxo e estética *glassmorphism*), **100% offline (sem CDNs externos)**, acessível tanto no navegador do próprio celular (`http://localhost:5000`) quanto em computadores na mesma rede Wi-Fi (`http://<IP-DO-CELULAR>:5000`).

---

## 📊 Estatísticas e Parâmetros do Projeto

| Dimensão | Especificação | Detalhes |
| :--- | :--- | :--- |
| **Parâmetros do Modelo (LLM)** | **134.515.008 parâmetros** (~134.5M) | Arquitetura baseada em `HuggingFaceTB/SmolLM2-135M-Instruct` |
| **Quantização Móvel** | **Q5_K_M (Medium)** | ~105 MB de tamanho em disco, ideal para dispositivos ARM64 |
| **Janela de Contexto** | **2.048 tokens** | Espaço amplo para System Prompt completo + histórico de ações |
| **Vocabulário** | **49.152 tokens** | Tokenizador ChatML nativo |
| **Ferramentas Nativas (Tools)** | **32 ferramentas** | Controle de hardware, utilitários, sensores, mobilidade e delivery |
| **Parâmetros de Ferramentas** | **40 parâmetros formais** | Catalogados e tipados estritamente no `dataset/schema.json` |
| **Base de Dados de Treino** | **5.424 amostras limpas** | 100% validadas por analisador sintático AST em PT-BR |

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

## 🛠️ Catálogo Completo das 32 Ferramentas

O Silva possui 32 ferramentas implementadas em `android_agent/tools.py` e catalogadas formalmente em `dataset/schema.json`:

| # | Ferramenta | Parâmetros (40 no total) | Descrição do Hardware / Função |
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
| **13** | `search_google(query)` | `query` (str, obrigatório) | Pesquisa no Google abrindo navegador e gerando link rápido. |
| **14** | `set_torch(state)` | `state` (bool, obrigatório) | Liga (`True`) ou desliga (`False`) a lanterna traseira. |
| **15** | `set_dnd(state)` | `state` (bool, obrigatório) | Ativa ou desativa modo Não Perturbe / Silencioso. |
| **16** | `vibrate(duration_ms)` | `duration_ms` (int, padrão: 500) | Aciona vibração háptica no aparelho pelo tempo informado. |
| **17** | `get_clipboard()` | *Nenhum* | Lê o conteúdo textual copiado na área de transferência. |
| **18** | `set_clipboard(text)` | `text` (str, obrigatório) | Copia texto especificado para a área de transferência. |
| **19** | `tell_joke()` | *Nenhum* | Retorna piada divertida do banco offline em PT-BR. |
| **20** | `set_alarm(time, label, days)` | `time` (str, obrigatório), `label` (str), `days` (str) | Agenda alarme no relógio nativo do Android. |
| **21** | `cancel_alarm(time, day, label)` | `time` (str), `day` (str), `label` (str) | Cancela ou descarta alarme configurado. |
| **22** | `schedule_event(title, date, time)`| `title` (str, obrigatório), `date` (str), `time` (str) | Cria compromisso na agenda local + Intent direta no Calendário Samsung. |
| **23** | `remember_note(key, value)` | `key` (str, obrigatório), `value` (str, obrigatório) | Salva nota ou informação na memória persistente offline. |
| **24** | `recall_note(query)` | `query` (str, obrigatório) | Busca notas, lembretes e compromissos armazenados anteriormente. |
| **25** | `get_notifications(app)` | `app` (str, opcional) | Lê notificações recentes da barra de status do Android. |
| **26** | `set_volume(stream, level)` | `stream` (str: media/ring/alarm), `level` (int: 0-100) | Ajusta volume por canal de áudio em porcentagem. |
| **27** | `set_brightness(level)` | `level` (int: 0 a 100, obrigatório) | Ajusta o brilho da tela do smartphone de 0% a 100%. |
| **28** | `set_timer(minutes, label)` | `minutes` (int, obrigatório), `label` (str) | Inicia timer ou cronômetro no relógio do Android. |
| **29** | `calculate(expression)` | `expression` (str, obrigatório) | Resolve cálculos matemáticos e expressões aritméticas offline. |
| **30** | `request_ride(destination, app)` | `destination` (str, obrigatório), `app` (str, padrão: "uber") | Abre app de transporte (Uber ou 99) com o destino configurado a partir da localização atual. |
| **31** | `order_food(query, app)` | `query` (str, obrigatório), `app` (str, padrão: "ifood") | Abre app de delivery (iFood ou 99) buscando o prato, restaurante ou item pedido. |
| **32** | `none()` | *Nenhum* | Emissão neutra para saudações e conversas gerais. |

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
│   ├── parser.py                  # Analisador sintático AST seguro e validador de whitelist
│   ├── tools.py                   # Implementação real das 32 ferramentas de hardware/apps
│   ├── config.py                  # Configurações globais, portas, PIN e System Prompt
│   ├── setup_termux.sh            # Instalação automática de dependências e build do llama.cpp
│   ├── start_silva.sh             # Script de inicialização (llama-server + web_server)
│   ├── captures/                  # Armazena fotos, vídeos, prints e mapas gerados
│   ├── data/                      # Persistência de notas, eventos de agenda e localização
│   ├── models/                    # Pasta onde reside o micro-modelo silva-135m.gguf
│   └── static/
│       └── index.html             # Interface web responsiva (Desktop/Mobile, dark mode, zero CDNs)
│
├── dataset/                       # ENGENHARIA DE DADOS E VALIDAÇÃO
│   ├── schema.json                # Especificação JSON Schema formal das 32 ferramentas
│   ├── seed_examples.jsonl        # 104 exemplos canônicos de referência em PT-BR
│   ├── train.jsonl                # Dataset completo com 5.092 amostras validadas
│   ├── train_clean.jsonl          # 95% do dataset limpo para fine-tuning supervisionado (5.153)
│   ├── eval_clean.jsonl           # 5% do dataset para avaliação e validação de perda (271)
│   ├── silva_colab_dataset.jsonl  # 5.424 amostras consolidadas para treino no Google Colab
│   ├── validate_dataset.py        # Validador sintático AST e verificador de schema
│   ├── prepare_final_dataset.py   # Gerador de contatos sintéticos, balanceador e divisor
│   └── repair_train_dataset.py    # Corretor automático de inconsistências e desbalanceamento
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
- **`web_server.py`**: Construído sobre o `ThreadingHTTPServer` nativo do Python (sem frameworks pesados como Flask/FastAPI para economizar RAM). Trata requisições para a API `/api/chat`, valida o cabeçalho de segurança `X-Access-Pin`, serve arquivos estáticos e mapeia arquivos multimídia da pasta `captures/`.
- **`scheduler.py`**: Thread daemon em background que monitora compromissos salvos localmente (`events.json`) a cada 30 segundos, disparando notificações nativas (`termux-notification`) e vibração no horário exato do lembrete.
- **`llm_client.py`**: Interage com o `llama-server` rodando em `127.0.0.1:8080`. Se o modelo demorar ou antes mesmo da chamada, o `match_intent_fallback` processa intenções imediatas em menos de 2 milissegundos.
- **`intent_fallback.py`**: Motor de regras determinísticas de alta velocidade para controle de hardware crítico (ligar lanterna, silenciar, pedir localização, previsão do tempo, corridas Uber/99 e delivery iFood) garantindo resposta instantânea mesmo se o processador estiver sob carga.
- **`parser.py`**: Utiliza o módulo `ast` (Abstract Syntax Tree) para validar e inspecionar os argumentos emitidos na tag `<call>`. Evita injeção de código e checa se a função chamada pertence à lista de permissões (`AVAILABLE_TOOLS`).
- **`tools.py`**: Conector entre a inteligência e o Android. Executa comandos como `termux-battery-status`, `termux-camera-photo`, `termux-location`, deep links de transporte (`request_ride`) e delivery (`order_food`), chamadas de telefone (`am start -a android.intent.action.CALL`), controle de volume e consultas à API do Open-Meteo.
- **`config.py`**: Centraliza os parâmetros de configuração: porta do servidor (padrão `5000`), PIN de autenticação (`1234`), e o `SILVA_SYSTEM_PROMPT` sincronizado.
- **`static/index.html`**: Chat moderno com estética Dark Purple & Liquid Glass, sidebar desktop de 2 colunas com telemetria em tempo real, ribbon mobile horizontal, zero `innerHTML` (100% seguro contra XSS) e zero dependências externas.

#### 2. Módulo `dataset/` (Dados de Treinamento)
- **`schema.json`**: Contrato estrito que rege a estrutura do micro-agente. Define formalmente parâmetros obrigatórios, opcionais e tipos (string, integer, boolean) para as 32 ferramentas.
- **`validate_dataset.py`**: Analisa arquivos `.jsonl` linha por linha, extrai chamadas via regex, compila os argumentos via AST e emite relatórios de conformidade e proporção percentual de classes.
- **`prepare_final_dataset.py`**: Enriquece a base com variações naturais de contatos humanos (ex: *"Mãe"*, *"Amor"*, *"Doutor Carlos"*), remove duplicatas e gera a divisão treino (95%) e validação (5%).
- **`silva_colab_dataset.jsonl`**: Arquivo final consolidado com 5.424 exemplos prontos para upload e treino no Colab.

#### 3. Módulo `pc_training/` (Treino e Conversão)
- **`colab_train_silva.py`**: Pipeline tudo-em-um para o Google Colab: desinstala pacotes conflitantes, atualiza Hugging Face, clona e compila ferramentas do `llama.cpp`, realiza o fine-tuning LoRA com `TRL/SFTTrainer`, funde os pesos no modelo base SmolLM2-135M, quantiza em `Q5_K_M` e dispara o download automático de `silva-135m.gguf`.

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
Coloque o arquivo `silva-135m.gguf` dentro de `android_agent/models/` e execute:
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
