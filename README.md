# 🤖 Silva — Micro-Agente Autônomo Offline para Android

O **Silva** é um micro-agente de inteligência artificial pessoal **100% offline, privado e ultraleve**, projetado para rodar nativamente em smartphones Android utilizando o **Termux** e a **Termux:API**. 

Diferente de assistentes convencionais ou bots de chat externos (Telegram/WhatsApp), o Silva utiliza um micro-modelo quantizado em formato **GGUF** (entre 90 MB e 105 MB, baseado na arquitetura **`HuggingFaceTB/SmolLM2-135M-Instruct`** quantizado em `Q5_K_M` ou `Q4_K_M`) operando estritamente como um **roteador semântico de *Function Calling***: ele recebe instruções em linguagem natural em Português do Brasil e gera chamadas de função tipadas `<call>funcao(args)</call>` que interagem diretamente com o hardware e os recursos do celular.

O sistema inclui um **servidor web local responsivo** com tema moderno roxo/escuro e **zero dependências externas (sem CDNs)**, permitindo acesso tanto pelo navegador do próprio celular (`http://localhost:5000`) quanto pelo computador conectado à mesma rede Wi-Fi (`http://<IP-DO-CELULAR>:5000`).

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
│                │                             │  Micro-GGUF (SmolLM2-135M)    │   │
│                │                             └──────────────┬────────────────┘   │
│                │                                            │ <call>func()</call>│
│                ▼                                            ▼                    │
│   ┌─────────────────────────┐               ┌────────────────────────────────┐   │
│   │   Tools.py (Termux:API) │◀──────────────│   Parser AST & Whitelist       │   │
│   └────────────┬────────────┘               └────────────────────────────────┘   │
│                │                                                                 │
│                ▼ Subprocessos seguros (sem shell injection)                      │
│   [Bateria] [Câmera] [SMS] [Lanterna] [GPS] [Vibração] [Chamadas] [Apps]         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📁 Estrutura do Repositório

```text
silva-agent/
├── README.md                      # Documentação completa do Silva
├── .env.example                   # Template de variáveis de ambiente
├── dataset/
│   ├── schema.json                # Especificação formal das 12 ferramentas e tipos
│   ├── seed_examples.jsonl        # Amostras iniciais em PT-BR cobrindo todas as ferramentas
│   └── validate_dataset.py        # Validador de sintaxe JSONL, tags <call> e classes
├── android_agent/
│   ├── setup_termux.sh            # Script de instalação de pacotes e build do llama-server
│   ├── start_silva.sh             # Script de inicialização (llama-server + web_server)
│   ├── config.py                  # Configurações de ambiente, timeouts e System Prompt
│   ├── tools.py                   # Wrappers seguros para hardware e Termux:API
│   ├── llm_client.py              # Cliente HTTP ultraleve para o llama-server local
│   ├── parser.py                  # Extrator seguro via AST com validação em whitelist
│   ├── web_server.py              # Servidor HTTP multithread nativo com endpoints REST
│   ├── main.py                    # Entrypoint (--web para LAN ou --cli para terminal)
│   ├── captures/                  # Diretório local para fotos capturadas
│   ├── models/                    # Diretório local para os modelos GGUF
│   └── static/
│       └── index.html             # Interface web single-file (dark mode roxo, 100% offline)
└── pc_training/
    ├── requirements_pc.txt        # Dependências compatíveis com CPU Ivy Bridge e DirectML
    ├── train_sft.py               # Fine-Tuning SFT (LoRA/Full) otimizado para CPU/DirectML
    └── export_gguf.py             # Fusão de pesos LoRA, conversão para GGUF e quantização
```

---

## 📱 Guia de Instalação no Android (Termux)

### 1. Pré-requisitos no Celular
1. Instale o **Termux** e o **Termux:API** a partir do [F-Droid](https://f-droid.org/) (não use a versão desatualizada da Play Store).
2. Abra as configurações do Android > Aplicativos > **Termux:API** e conceda as permissões necessárias: Câmera, Localização, SMS, Telefone e Armazenamento.

### 2. Configuração Automatizada
No terminal do Termux, clone ou copie a pasta `silva-agent` e execute:

```bash
cd silva-agent/android_agent
chmod +x setup_termux.sh start_silva.sh
./setup_termux.sh
```

O script atualizará os pacotes, instalará as ferramentas de compilação, clonará o `llama.cpp` e compilará o `llama-server` nativo para a arquitetura ARM64 do seu celular.

### 3. Inicialização do Agente
Com o modelo GGUF colocado dentro da pasta `android_agent/models/`:

```bash
./start_silva.sh
```

O script detectará o IP da sua rede Wi-Fi e exibirá:
- **Acesso direto no smartphone:** `http://localhost:5000`
- **Acesso pelo PC na mesma rede Wi-Fi:** `http://192.168.x.x:5000`

---

## 🛠️ Ferramentas Nativas Disponíveis

| Ferramenta | Comando Nativo | Descrição |
| :--- | :--- | :--- |
| `get_battery()` | `termux-battery-status` | Nível de carga, status de carregamento e temperatura. |
| `get_last_sms(limit=5)` | `termux-sms-list` | Lê os últimos SMS recebidos no aparelho. |
| `send_sms(number, message)` | `termux-sms-send` | Envia mensagem SMS para um número com DDD. |
| `take_photo(camera_id=0)` | `termux-camera-photo` | Tira foto (0 traseira, 1 frontal) e renderiza inline no chat. |
| `open_app(app_name)` | `monkey / am start` | Abre aplicativos populares (WhatsApp, YouTube, Spotify, etc). |
| `make_call(number)` | `termux-telephony-call` | Inicia ligação telefônica para o número informado. |
| `get_location()` | `termux-location` | Obtém coordenadas GPS/rede e link direto do Google Maps. |
| `set_torch(state=True)` | `termux-torch` | Liga ou desliga a lanterna traseira. |
| `set_dnd(state=True)` | `cmd notification / termux-volume` | Ativa ou desativa o modo Não Perturbe / Silencioso. |
| `vibrate(duration_ms=500)`| `termux-vibrate` | Aciona o motor de vibração do smartphone. |
| `get_clipboard()` | `termux-clipboard-get` | Retorna o texto copiado na área de transferência. |
| `set_clipboard(text)` | `termux-clipboard-set` | Copia texto para a área de transferência. |
| `tell_joke()` | Banco offline | Conta piadas curtas e bem-humoradas em Português do Brasil. |
| `set_alarm(time, label, days)` | `am start (SET_ALARM)` | Define alarme no relógio nativo do Android. |
| `cancel_alarm(time, day, label)` | `am start (DISMISS_ALARM)` | Cancela alarme por horário, dia ou rótulo. |
| `schedule_event(title, date, time)` | `am start (INSERT calendar)` | Agenda compromisso no calendário nativo com resolução PT-BR. |
| `remember_note(key, value)` | Persistência JSON | Salva uma anotação pessoal na memória local do Silva. |
| `recall_note(query)` | Busca semântica local | Consulta anotações guardadas na memória persistente. |
| `get_notifications(app)` | `termux-notification-list`| Lê as notificações recentes com filtro opcional por app. |
| `set_volume(stream, level)` | `termux-volume` | Ajusta volume de áudio em porcentagem (0 a 100%). |
| `set_brightness(level)` | `termux-brightness` | Ajusta brilho da tela em porcentagem (0 a 100%). |
| `set_timer(minutes, label)` | `am start (SET_TIMER)` | Inicia timer / cronômetro nativo do Android. |
| `calculate(expression)` | Avaliador AST seguro | Resolve expressões matemáticas offline sem eval. |
| `none()` | — | Acionado para perguntas gerais, saudações ou sem ferramenta. |

---

## 💻 Ambiente de Treinamento no PC Desktop (Windows 10 / Linux)

### Especificações Alvo
- **Processador:** Intel Xeon E3-1270 v2 (Ivy Bridge — suporta AVX, não suporta AVX2).
- **RAM:** 16 GB DDR3.
- **GPU:** AMD Radeon RX 580 2048SP 8GB (suporte a `torch-directml` ou execução estável em CPU FP32).

### Passos de Treinamento e Quantização

1. **Instalação das dependências:**
   ```bash
   cd pc_training
   pip install -r requirements_pc.txt
   ```

2. **Validação do Dataset:**
   ```bash
   python ../dataset/validate_dataset.py
   ```

3. **Treinamento SFT:**
   O script `train_sft.py` utiliza a biblioteca `trl` e `peft` (LoRA) para treinar o micro-modelo `SmolLM2-135M-Instruct` sem sobrecarregar a memória do computador.

4. **Conversão e Quantização GGUF:**
   O script `export_gguf.py` realiza a fusão dos adaptadores LoRA e quantiza para `Q5_K_M` (~105 MB, padrão de máxima precisão) ou `Q4_K_M` (~90 MB), gerando o arquivo final `silva-135m.gguf`.

---

## 🔒 Segurança e Privacidade

- **100% Offline:** Nenhuma requisição ou dado sai da sua rede local.
- **Sem Shell Injection:** Chamadas de sistema utilizam `subprocess.run` com listas de argumentos sanitizados.
- **AST Parsing:** Argumentos são avaliados estritamente via `ast.literal_eval`, sem uso de `eval()` arbitrário.
- **PIN de Rede:** Header opcional `X-Access-Pin` para prevenir comandos acidentais de outros aparelhos no mesmo Wi-Fi.
