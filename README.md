# 🤖 Silva — Micro-Agente Autônomo Offline para Android

O **Silva** é um micro-agente de Inteligência Artificial **100% offline, privado e ultraleve**, desenvolvido para operar nativamente na borda (*edge computing*) em smartphones Android através do ambiente **Termux** e da **Termux:API**.

Sem depender de nuvem, APIs pagas ou conexões de internet para raciocinar, o Silva une o que há de melhor em **IA determinística ultra-rápida** e **modelos de linguagem generativos locais (SLM - Small Language Models)**, orquestrando hardware, conectividade, aplicativos e automações do dispositivo em milissegundos.

---

## 🏛️ 1. Apresentação e Arquitetura Híbrida

O grande diferencial do Silva é a sua **Arquitetura Híbrida em Dois Estágios**, projetada para aliar **latência instantânea** e **baixo consumo de bateria**:

```text
                                  ┌──────────────────────────────┐
                                  │      Usuário (Mobile/PC)     │
                                  │   Interface Web / Terminal   │
                                  └──────────────┬───────────────┘
                                                 │ Entrada (Texto / "Segure para falar")
                                                 ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                            AMBILENTE ANDROID (TERMUX)                            │
│                                                                                  │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │ ESTÁGIO 1: Roteador Determinístico & NLP PT-BR (intent_fallback / nlp/)  │   │
│   │ • Normalização fonética e coloquial ("bateria", "lanterna", "no talo")  │   │
│   │ • Parser numérico composto ("trinta e cinco", "meia hora")               │   │
│   │ • Sanitização de quebras de linha e argumentos semânticos                │   │
│   │ • Latência: ~1.5 milissegundos | RAM: < 35 MB | CPU: < 1%                │   │
│   └───────────────────────┬──────────────────────────┬───────────────────────┘   │
│                           │ Intenção Reconhecida     │ Entrada Complexa / Livre  │
│                           ▼                          ▼                           │
│   ┌─────────────────────────────────┐   ┌────────────────────────────────────┐   │
│   │   Execução Direta de Funções    │   │ ESTÁGIO 2: Motor Local GGUF        │   │
│   │   <call>ferramenta(args)</call> │   │ • llama-server (porta 8080)        │   │
│   │   Parser AST & Whitelist Segura │   │ • silva-135m.gguf (SmolLM2 Q5_K_M) │   │
│   └───────────────┬─────────────────┘   │ • Function Calling ChatML          │   │
│                   │                     └─────────────────┬──────────────────┘   │
│                   │                                       │                      │
│                   ▼                                       ▼                      │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │ Pacote Modular de Ferramentas Nativas (39 Tools em android_agent/tools/) │   │
│   │ Hardware • Câmera • GPS • Wi-Fi • Volume • SMS • Memória SQLite FTS5     │   │
│   └──────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

### Os 4 Pilares da Engenharia do Silva:

1. **Roteador Determinístico com Regex + NLP em Português (~1.5ms):**
   Antes de acionar qualquer rede neural pesada, o texto do usuário passa pelo pacote `android_agent/nlp/` (`numbers.py`, `colloquial.py`, `router.py`). Ele interpreta gírias brasileiras, números por extenso de zero a milhões, variações fonéticas e erros comuns de digitação ("baterria", "ligar lanterana"). Se a intenção for clara, a ferramenta é disparada imediatamente sem aquecer o processador.
2. **Motor Local LLM (GGUF ~135M via `llama.cpp`):**
   Para diálogos abertos, perguntas gerais e intenções complexas, entra em ação o micro-modelo local `silva-135m.gguf` (treinado sobre `SmolLM2-135M-Instruct` e quantizado em `Q5_K_M` com apenas ~105 MB). Ele roda sobre o `llama-server` nativo compilado para ARM64.
3. **57 Ferramentas Nativas com Whitelist e AST Estrito:**
   O agente possui acesso controlado a 57 ferramentas que cobrem o ecossistema do smartphone: sensores, câmera frontal/traseira, gravador de áudio, reprodução de mídia por busca (`play_media`), lanterna, Wi-Fi, Bluetooth, Dados Móveis, Modo Avião, Hotspot, volume granular, discagem, SMS, envio direto no WhatsApp (`send_whatsapp`), resumo inteligente de notificações (`summarize_notifications`), cadastro/consulta de contatos, navegação GPS curva a curva (`navigate_to`), deep links para Uber/iFood, data/hora, telemetria (disco, RAM, operadora), conversor de unidades/moedas, leitura de tela via `uiautomator`, listas dinâmicas persistentes (`add_list_item`, `get_list`, `remove_list_item`) e banco de notas/agenda SQLite FTS5. Todas as chamadas de função passam por um analisador de sintaxe abstrata (`ast`) contra qualquer injeção de código.
4. **Web UI Mobile Moderna com "Segure para falar":**
   Interface escura com visual futurista em roxo/neon (`#5A189A` / `#7B1FA2`), 100% responsiva, sem qualquer framework pesado ou CDN externo (totalmente offline-ready). Inclui botão de alternância para o modo **"Segure para falar"** com visualizador de ondas sonoras em tempo real via Web Audio API e gesto de deslizar para cancelar.

---

## ⚠️ 2. Pré-Requisitos no Android (Aviso Crítico)

> [!CAUTION]
> ### 🛑 NUNCA INSTALE O TERMUX OU O TERMUX:API PELA GOOGLE PLAY STORE!
> **As versões do Termux publicadas na Google Play Store estão DESCONTINUADAS E OBSOLETAS desde 2020** devido a restrições de permissões introduzidas pelo Google no Android 10+.
> Se você instalar pela Play Store, os repositórios oficiais falharão com erros críticos como `403 Forbidden` ou `Repository under maintenance` durante a execução de `pkg update`.

### Onde Baixar Corretamente:
Baixe os aplicativos oficiais através do **F-Droid** ou das **Releases do GitHub**. Ambos os aplicativos **DEVEM** ser instalados a partir da mesma fonte para compartilharem a mesma assinatura criptográfica de APK:

* **Termux App:** [Baixar no F-Droid](https://f-droid.org/packages/com.termux/) ou [GitHub Releases](https://github.com/termux/termux-app/releases)
* **Termux:API:** [Baixar no F-Droid](https://f-droid.org/packages/com.termux.api/) ou [GitHub Releases](https://github.com/termux/termux-api/releases)

### Permissões Necessárias no Android:
Após instalar o aplicativo **Termux:API**, abra as **Configurações do Android** > **Aplicativos** > **Termux:API** > **Permissões** e conceda:
* **Câmera:** para fotos (`take_photo`) e controle da lanterna (`set_torch`).
* **Localização (Precisa / Sempre):** obrigatória no Android para ler dados de Wi-Fi (`scan_wifi`, `get_wifi_info`) e clima local (`get_location`, `get_weather`).
* **Telefone e Contatos:** para efetuar chamadas (`make_call`).
* **SMS:** para envio e leitura de mensagens (`send_sms`, `get_last_sms`).
* **Microfone:** para o reconhecimento de voz nativo e Web Speech API.

> [!TIP]
> **Desative a Otimização de Bateria:** Vá em *Configurações > Aplicativos > Termux > Bateria* e selecione **"Irrestrito"** (ou "Não otimizar"). Isso impede que o Android encerre o servidor em segundo plano quando a tela for bloqueada.

---

## ⚡ 3. Tabela dos 4 Comandos Oficiais

Todo o gerenciamento do projeto foi consolidado em **4 scripts principais** localizados na raiz de `silva-agent/`:

| Script Oficial | Papel e Responsabilidade | Modo de Execução Recomendado |
| :--- | :--- | :--- |
| **`./install-silva.sh`** | Instalador automático, idempotente e resiliente. Instala pacotes essenciais do Termux (`python`, `termux-api`, `clang`, `cmake`, `git`), cria ambiente virtual (`venv`), compila o `llama-server` nativamente em ARM64 com `-j2` e baixa o modelo `silva-135m.gguf`. | Executar na 1ª instalação ou após atualizações de sistema. |
| **`./config-silva.sh`** | Assistente interativo de configuração. Permite alterar o PIN de segurança, portas de rede (Web e LLM), caminho do modelo GGUF, cidade padrão e opções de síntese de voz (TTS). | Opcional, sempre que desejar alterar configurações. |
| **`./start_silva.sh`** | Inicializador unificado do ecossistema. Executa pré-limpeza, aciona wake-lock para manter CPU ativa, sobe o `llama-server` (porta 8080), salva os PIDs em `runtime.pids`, exibe o painel de telemetria com URLs e inicia a Web UI (porta 5000). | Uso diário para colocar a IA em operação. |
| **`./stop-silva.sh`** | Encerramento seguro e completo. Finaliza com precisão os processos via `android_agent/data/runtime.pids` (SIGTERM e SIGKILL gracioso), faz varredura de instâncias presas, libera as portas 5000/8080 e desativa o wake-lock do Android. | Uso diário para desligar o agente e poupar bateria. |

---

## 🚀 4. Guia Passo a Passo de Instalação e Primeira Execução

Abra o aplicativo **Termux** no seu celular e execute os comandos abaixo sequencialmente:

### Passo 1: Atualizar pacotes base e clonar o repositório
```bash
pkg update -y && pkg install -y git
git clone https://github.com/TGTiler/Silva.git
cd Silva/silva-agent
```

### Passo 2: Executar o instalador automático
```bash
chmod +x install-silva.sh config-silva.sh start_silva.sh stop-silva.sh
./install-silva.sh
```
*O instalador detectará seu ambiente Android Termux, instalará as dependências necessárias, preparará o binário do `llama.cpp` e configurará o modelo `silva-135m.gguf`.*

### Passo 3: (Opcional) Ajustar preferências
```bash
./config-silva.sh
```
*Configure seu PIN de segurança pessoal (padrão: `1234`) e sua cidade padrão para previsão do tempo.*

### Passo 4: Iniciar o Silva Agent
```bash
./start_silva.sh
```
Ao iniciar, o terminal exibirá o banner informativo:
```text
========================================================
         SILVA AGENT - SISTEMA EM OPERAÇÃO              
========================================================
  Motor LLM:         [OK] Online (llama-server ativo na porta 8080)
  Acesso no Celular: http://127.0.0.1:5000
  Acesso na Rede:    http://192.168.0.106:5000
  PIN de Segurança:  1234
  Arquivo de Logs:   silva-agent/android_agent/logs/llama_server.log
========================================================
  Pressione Ctrl+C a qualquer momento para encerrar.
  Para encerrar em segundo plano: ./stop-silva.sh
--------------------------------------------------------
```

### Como Acessar a Interface:
* **No próprio celular:** Abra o Chrome ou qualquer navegador e acerte em: `http://localhost:5000` (ou `http://127.0.0.1:5000`).
* **A partir de um PC ou tablet no mesmo Wi-Fi:** Acesse `http://<IP_DO_CELULAR>:5000` (o IP local é exibido diretamente no banner).
* **Para encerrar a qualquer momento:** Pressione `Ctrl+C` no terminal ou execute `./stop-silva.sh`.

---

## 🔧 5. Guia Completo de Solução de Problemas (Troubleshooting)

Abaixo estão os 8 problemas reais mais comuns documentados em ambientes Termux com suas respectivas causas e comandos de correção imediata:

---

### 1. Erro de Repositório no Termux (`403 Forbidden` ou `Repository under maintenance`)
* **Sintoma:** Ao rodar `pkg update`, surgem erros `Repository under maintenance` ou `403 Forbidden` nos repositórios Bintray.
* **Causa:** O Termux foi baixado pela Google Play Store (versão abandonada desde 2020).
* **Solução:** Desinstale o Termux e o Termux:API da Play Store e instale as versões mais recentes a partir do **F-Droid** ou GitHub. Caso já esteja no F-Droid e apenas o espelho esteja fora do ar, troque o mirror com:
```bash
termux-change-repo
```

---

### 2. `llama-server: command not found` ou erro ao carregar `libllama.so`
* **Sintoma:** O banner acusa motor LLM offline e a inicialização falha procurando o binário `llama-server` ou acusando biblioteca dinâmica ausente.
* **Causa:** O pacote oficial do `llama-cpp` não foi instalado ou a compilação local foi interrompida.
* **Solução:** Instale o pacote pré-compilado oficial do repositório Termux ou force a compilação:
```bash
pkg install -y llama-cpp
# ou reexecute o instalador automático
./install-silva.sh
```

---

### 3. Motor LLM Offline no Banner (`Timeout de 15s` ou `Connection refused (Errno 111)`)
* **Sintoma:** O banner do `./start_silva.sh` avisa que o motor está offline após 15 segundos de espera.
* **Causa:** O arquivo `silva-135m.gguf` não está na pasta `models/` ou a quantidade de memória RAM do aparelho rejeitou o contexto.
* **Solução:** Verifique o log detalhado de inicialização do motor e reconfigure o modelo:
```bash
cat android_agent/logs/llama_server.log
./config-silva.sh
```

---

### 4. `Address already in use (Errno 98)` na porta 5000 ou 8080
* **Sintoma:** Ao iniciar o `./start_silva.sh`, surge erro em Python: `OSError: [Errno 98] Address already in use`.
* **Causa:** Uma sessão anterior do `web_server.py` ou do `llama-server` continuou em execução em segundo plano.
* **Solução:** Execute o script oficial de desligamento para varrer os processos e liberar as portas:
```bash
./stop-silva.sh
```

---

### 5. Área de Transferência Vazia (`get_clipboard` retorna vazio)
* **Sintoma:** O comando `"O que tem no meu clipboard?"` retorna que a área de transferência está vazia ou bloqueada.
* **Causa:** O Android 10+ bloqueia a leitura da área de transferência por processos em segundo plano por motivos de privacidade.
* **Solução:** Traga o aplicativo Termux para o primeiro plano ou envie a mensagem diretamente pela interface web aberta no navegador do celular.

---

### 6. Nome da Rede Wi-Fi Oculto ou Indisponível no `scan_wifi` / `get_wifi_info`
* **Sintoma:** A ferramenta de varredura ou status do Wi-Fi não exibe o SSID da rede conectada (retorna `[Oculto/Sem Permissão]`).
* **Causa:** O serviço de Localização (GPS) do smartphone está desativado ou o Termux:API não possui permissão de Localização Precisa. O Android exige GPS ativo para ler nomes de redes Wi-Fi.
* **Solução:** Ligue a Localização (GPS) no painel de notificações do Android e conceda permissão de Localização Precisa ao aplicativo Termux:API:
```bash
# Teste se a API consegue ler os dados de Wi-Fi:
termux-wifi-connectioninfo
```

---

### 7. Reconhecimento de Voz Não Funciona ("Segure para falar")
* **Sintoma:** Ao pressionar o botão de microfone na Web UI, o navegador recusa a captura ou exibe aviso de permissão de áudio.
* **Causa:** Os navegadores móveis (Chrome, Firefox) restringem a Web Speech API e a Web Audio API a **Contextos Seguros** (`https://` ou `localhost`). Ao acessar pelo IP de rede (`192.168.x.x`) sem certificado SSL, o navegador desativa o microfone.
* **Solução:** No próprio celular, acesse sempre pelo endereço local que é considerado seguro nativamente pelo navegador:
```text
http://localhost:5000  (ou http://127.0.0.1:5000)
```

---

### 8. Compilação do llama.cpp Trava o Celular (OOM Killer)
* **Sintoma:** Durante a compilação do `llama.cpp` pelo `install-silva.sh`, o Termux fecha repentinamente ou o terminal exibe `Killed`.
* **Causa:** O compilador utilizou todos os núcleos da CPU (`-j$(nproc)`), esgotando a memória RAM do smartphone e acionando o Out-Of-Memory Killer do kernel Linux.
* **Solução:** Limite a compilação a no máximo 2 threads paralelas com o comando otimizado:
```bash
cd ~/llama.cpp && cmake --build build -j2
```

---

## 🛠️ 6. Catálogo Completo das 39 Ferramentas Nativas

O Silva implementa **39 ferramentas nativas** divididas em 5 domínios funcionais. Todas foram extensivamente testadas com frases reais do cotidiano em Português do Brasil:

### 📱 1. Hardware, Sensores & Mídia (15 Ferramentas)

| Nome da Ferramenta | Descrição Técnica | Exemplo de Frase em Português (Testada) |
| :--- | :--- | :--- |
| `get_battery()` | Consulta nível percentual, saúde, temperatura e carregamento da bateria. | *"Quantos por cento tá a minha bateria?"* |
| `set_torch(state)` | Liga (`True`) ou desliga (`False`) a lanterna traseira do dispositivo. | *"Liga a lanterna"* / *"Desliga o flash"* |
| `vibrate(duration_ms)` | Aciona vibração háptica no aparelho pelo tempo especificado em milissegundos. | *"Faz o celular vibrar por 2 segundos"* |
| `take_photo(camera_id)` | Captura foto com a câmera traseira (`0`) ou frontal (`1` selfie) e exibe no chat. | *"Tira uma selfie"* / *"Tira uma foto com a traseira"* |
| `record_video(duration, camera_id)` | Grava vídeo nativo pelo tempo indicado e gera player inline na conversa. | *"Grava um vídeo de 10 segundos"* |
| `take_screenshot()` | Captura print da tela do smartphone e disponibiliza imagem no chat. | *"Tira um print da tela"* / *"Captura a tela"* |
| `get_location()` | Obtém coordenadas GPS atuais e renderiza card visual de mapa estático. | *"Onde eu estou agora?"* / *"Pega minha localização"* |
| `get_last_location()` | Retorna a última localização registrada em cache offline mesmo com GPS desligado. | *"Qual foi minha última localização conhecida?"* |
| `set_location_state(state)` | Ativa ou desativa o serviço de GPS do aparelho. | *"Liga o GPS"* / *"Desativa o sensor de localização"* |
| `get_clipboard()` | Lê o texto atualmente copiado na área de transferência do dispositivo. | *"O que está copiado no meu celular?"* |
| `set_clipboard(text)` | Copia texto especificado para a área de transferência do sistema. | *"Copia o código 4892 para o clipboard"* |
| `set_volume(stream, level)` | Ajusta volume de canais de áudio (`media`, `ring`, `alarm`) de 0% a 100%. | *"Coloca o volume de mídia no 80"* / *"Volume no talo"* |
| `set_brightness(level)` | Ajusta o brilho da tela do smartphone de 0% a 100%. | *"Aumenta o brilho da tela para 70%"* |
| `set_dnd(state)` | Ativa ou desativa o modo Não Perturbe / Silencioso do Android. | *"Ativa o modo não perturbe"* / *"Modo silencioso"* |
| `media_control(action)` | Controla reprodução de mídia (`play`, `pause`, `next`, `previous`). | *"Pausa a música"* / *"Avança para a próxima faixa"* |

---

### 🌐 2. Conectividade & Redes Wi-Fi (4 Ferramentas)

| Nome da Ferramenta | Descrição Técnica | Exemplo de Frase em Português (Testada) |
| :--- | :--- | :--- |
| `scan_wifi()` | Escaneia redes Wi-Fi próximas exibindo SSID, sinal (dBm e %), frequência e proteção. | *"Quais redes Wi-Fi tem ao meu redor?"* |
| `connect_wifi(ssid, password)` | Conecta a uma rede Wi-Fi específica com cópia segura e fallback em SQLite. | *"Se conecte ao wifi HENRIQUE_NET//SENHA123"* |
| `get_wifi_info()` | Exibe telemetria da conexão atual (SSID, IP local, sinal % e velocidade de link). | *"Qual Wi-Fi estou conectado?"* / *"Info do Wi-Fi"* |
| `set_wifi_state(state)` | Liga ou desliga a interface Wi-Fi do smartphone via Termux:API e fallback svc. | *"Liga o Wi-Fi"* / *"Desconecta da internet sem fio"* |

---

### 📲 3. Aplicativos & Sistema Android (6 Ferramentas)

| Nome da Ferramenta | Descrição Técnica | Exemplo de Frase em Português (Testada) |
| :--- | :--- | :--- |
| `open_app(app_name)` | Abre aplicativos instalados pelo nome popular ou pacote oficial. | *"Abre o WhatsApp"* / *"Inicia o YouTube"* |
| `install_app(app_name)` | Abre a Google Play Store na página de instalação do app solicitado. | *"Instala o aplicativo do Duolingo"* |
| `make_call(number)` | Inicia chamada telefônica para número informado ou contato. | *"Liga para 11999998888"* / *"Chama o João"* |
| `send_sms(number, message)` | Envia mensagem SMS para número com DDD ou contato da agenda. | *"Manda um SMS para 11988887777 dizendo Cheguei"* |
| `get_last_sms(limit)` | Lê as últimas mensagens SMS recebidas na caixa de entrada do aparelho. | *"Lê as últimas 3 mensagens de SMS"* |
| `get_notifications(app)` | Consulta notificações ativas recentes na barra de status do Android. | *"Quais notificações chegaram agora?"* |

---

### 🔍 4. Automação, Web, Clima & Utilitários (10 Ferramentas)

| Nome da Ferramenta | Descrição Técnica | Exemplo de Frase em Português (Testada) |
| :--- | :--- | :--- |
| `search_google(query, open_browser)` | Pesquisa multi-fonte em cascata (Wikipédia PT-BR + Google News RSS) com card visual. | *"Pesquise sobre a história do GTA V"* |
| `get_weather(day, time, location)` | Previsão do tempo detalhada via Open-Meteo sem necessidade de chave de API. | *"Vai chover amanhã em São Paulo?"* |
| `order_food(query, app)` | Abre app de delivery (iFood ou 99 Food) buscando o prato ou restaurante desejado. | *"Pede uma pizza de calabresa no iFood"* |
| `request_ride(destination, app)` | Abre aplicativo de transporte (Uber ou 99) configurando o destino desejado. | *"Chama um Uber até a Avenida Paulista"* |
| `set_timer(minutes, label)` | Inicia timer ou contagem regressiva no relógio nativo do Android. | *"Coloca um timer de meia hora para o bolo"* |
| `set_alarm(time, label, days)` | Cria alarme no relógio nativo para o horário informado com rótulo. | *"Acorda às 7 da manhã amanhã"* |
| `cancel_alarm(time, day, label)` | Descarta ou desativa alarmes programados no relógio do sistema. | *"Cancela o alarme das 7 horas"* |
| `schedule_event(title, date, time)` | Cria compromisso na agenda local e no Calendário nativo do smartphone. | *"Marca dentista amanhã às 15 horas"* |
| `calculate(expression)` | Calculadora científica, aritmética e financeira segura processada via AST. | *"Quanto é 15 por cento de 350 reais?"* |
| `tell_joke()` | Retorna uma piada bem-humorada do banco offline em português. | *"Me conta uma piada"* |

---

### 🧠 5. Memória de Longo Prazo, Ajuda & Conversação (4 Ferramentas)

| Nome da Ferramenta | Descrição Técnica | Exemplo de Frase em Português (Testada) |
| :--- | :--- | :--- |
| `remember_note(key, value)` | Salva informações permanentes no banco relacional SQLite com indexação FTS5. | *"Lembra que o aniversário da Maria é 20 de outubro"* |
| `recall_note(query)` | Busca híbrida (BM25 + LIKE) de notas e memórias salvas anteriormente. | *"Quando é o aniversário da Maria?"* / *"Qual a anotação..."* |
| `list_capabilities()` | Apresenta resumo estruturado com todas as capacidades e comandos do agente. | *"O que você sabe fazer?"* / *"Quais seus comandos?"* |
| `none()` | Emissão neutra para interações sociais cotidianas e saudações. | *"Olá, bom dia!"* / *"Como você está?"* |

---

## 🔒 7. Privacidade, Segurança e Modo de Uso

* **100% On-Device:** Nenhum dado pessoal, áudio gravado, captura de câmera, SMS ou coordenada sai do seu telefone para servidores externos.
* **Autenticação Local por PIN:** A API REST do servidor web exige validação do cabeçalho `X-Access-Pin` em todas as rotas operacionais, garantindo que terceiros na sua rede Wi-Fi não possam controlar o aparelho sem a chave configurada em `./config-silva.sh`.
* **Segurança de Execução:** Todas as funções acionadas passam pelo compilador AST do Python (`parser.py`), bloqueando qualquer tentativa de injeção arbitrária de comandos ou execução de funções fora da lista estrita de permissões.
