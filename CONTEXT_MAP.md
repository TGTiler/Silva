# Silva — Context Map Técnico

> Documento de referência gerado por inspeção estática do projeto. Escopo inspecionado: `2026-11-21`, checkout `silva-agent` em `ce97d28965bbd196287446f357a80e94be2ea5eb` (`main`). Convenções: `arquivo:linha` identifica a implementação; nomes de chaves, rotas e funções aparecem exatamente como no código.

## 1. Estrutura de Pastas e Árvore de Arquivos

### 1.1 Árvore do código do projeto

A árvore abaixo cobre a raiz do workspace, o repositório autoral `silva-agent/`, artefatos binários e diretórios gerados. `.git/` é metadado gerado do Git; seu conteúdo interno não é código do produto.

```text
Silva/
├── apply_tools_update.sh                    # autoral: substitui tools.py no Termux e reinicia o agente
├── install_model_and_restart.sh             # autoral: instala novo GGUF, arquiva o anterior e reinicia
├── resolved_activities.py                   # autoral: cópia do mapa de activities Android
├── screen_termux.png                        # artefato: captura de tela de uma execução anterior
├── silva_deploy.tar.gz                      # artefato: pacote de implantação desatualizado
├── silva_update.tar.gz                      # artefato: patch de implantação desatualizado
├── start_silva_bootstrap.sh                 # autoral: extrai, instala e inicia o Silva no Termux
├── termux-api-fdroid.apk                    # artefato: APK binário Termux:API (F-Droid)
├── termux-api.apk                           # artefato: APK binário Termux:API
├── test_open.py                             # autoral: teste manual de abertura da calculadora
├── update_and_restart.sh                    # autoral: extrai patch, encerra API Python e reinicia
├── update_direct.sh                         # autoral: sincroniza arquivos modificados via ADB no Termux e reinicia o Silva
├── platform-tools/                          # artefato de terceiros: Android platform-tools 37.0.3
│   ├── NOTICE.txt                           # licença do pacote platform-tools
│   ├── adb                                  # cliente ADB compilado
│   ├── etc1tool                             # utilitário ETC1 compilado
│   ├── fastboot                             # ferramenta fastboot compilada
│   ├── hprof-conv                           # conversor Android hprof compilado
│   ├── make_f2fs                            # maker F2FS compilado
│   ├── make_f2fs_casefold                   # maker F2FS casefold compilado
│   ├── mke2fs                               # maker ext4 compilado
│   ├── mke2fs.conf                          # configuração de defaults do mke2fs
│   ├── sqlite3                              # CLI SQLite compilado
│   ├── source.properties                    # metadados de versão do platform-tools
│   └── lib64/                               # biblioteca nativa do package
│       └── libc++.so                        # runtime C++ do platform-tools
└── silva-agent/                             # repositório Git autoral do produto
    ├── .env.example                         # autoral: template de configuração do runtime
    ├── .gitignore                           # autoral: exclusões de dados, modelos e caches
    ├── README.md                            # autoral: documentação de arquitetura, uso e treinamento
    ├── .git/                                # artefato gerado: metadados e objetos do Git
    ├── android_agent/                       # runtime de produção no Termux
    │   ├── config.py                        # autoral: configuração, paths e prompt do LLM
    │   ├── intent_fallback.py               # autoral: roteador determinístico de intenções PT-BR com normalização matemática e de cidades
    │   ├── llm_client.py                    # autoral: cliente do llama-server e fallback local
    │   ├── main.py                          # autoral: entrypoint CLI/Web
    │   ├── parser.py                        # autoral: parser AST, whitelist e executor de calls
    │   ├── scheduler.py                     # autoral: daemon background que monitora compromissos locais e dispara alertas
    │   ├── setup_termux.sh                  # autoral: instala Termux, dependências e llama.cpp
    │   ├── start_silva.sh                   # autoral: boot resiliente, limpeza cirúrgica de órfãos e gestão de PIDs
    │   ├── tools.py                         # autoral: implementação das 35 ferramentas Android
    │   ├── web_server.py                    # autoral: servidor ReusableThreadingHTTPServer com SO_REUSEADDR, fallback de porta e API REST
    │   ├── __pycache__/                     # artefato gerado: bytecode Python 3.12
    │   │   ├── config.cpython-312.pyc       # bytecode de config.py
    │   │   ├── intent_fallback.cpython-312.pyc # bytecode de intent_fallback.py
    │   │   ├── llm_client.cpython-312.pyc    # bytecode de llm_client.py
    │   │   ├── parser.cpython-312.pyc        # bytecode de parser.py
    │   │   ├── tools.cpython-312.pyc         # bytecode de tools.py
    │   │   └── web_server.cpython-312.pyc    # bytecode de web_server.py
    │   ├── captures/                        # diretório de estado gerado: fotos, vídeos, prints e mapas
    │   │   └── .gitkeep                     # placeholder versionado
    │   ├── data/                            # diretório de estado gerado: memória, localização, PIDs e DND
    │   │   └── .gitkeep                     # placeholder versionado
    │   ├── models/                          # diretório de artefatos de modelo
    │   │   ├── .gitkeep                     # placeholder versionado
    │   │   ├── silva-135m.gguf              # artefato: modelo local ativo, Q5_K_M
    │   │   └── old/                         # artefato: versões anteriores do modelo
    │   │       ├── silva-135m-V0.0.1.gguf   # artefato: modelo GGUF V0.0.1
    │   │       └── silva-135m-V0.0.2.gguf   # artefato: modelo GGUF V0.0.2
    │   └── static/                          # frontend estático sem build
    │       └── index.html                   # autoral: interface web, CSS e JavaScript inline
    ├── dataset/                             # engenharia e artefatos de dados autorais
    │   ├── schema.json                      # autoral: contrato customizado de ferramentas/parâmetros
    │   ├── seed_examples.jsonl              # autoral: 104 exemplos-base
    │   ├── train.jsonl                      # autoral/estado: 4.888 exemplos; contém calls fora do schema
    │   ├── train.jsonl.bak                  # autoral/backup: 4.140 exemplos anteriores ao reparo
    │   ├── train_clean.jsonl                # autoral/estado: 4.356 exemplos limpos de treino
    │   ├── eval_clean.jsonl                 # autoral/estado: 229 exemplos limpos de avaliação
    │   ├── silva_colab_dataset.jsonl        # autoral/estado: 4.585 exemplos consolidados
    │   ├── prepare_final_dataset.py          # autoral: valida, enriquece, deduplica e divide
    │   ├── repair_train_dataset.py           # autoral: corrige e enriquece o dataset de treino
    │   ├── validate_dataset.py               # autoral: validador AST/schema dos JSONL
    │   └── __pycache__/                     # artefato gerado: bytecode Python 3.12
    │       └── prepare_final_dataset.cpython-312.pyc # bytecode do preparador
    └── pc_training/                         # pipeline de treinamento e exportação
        ├── colab_train_silva.py             # autoral: pipeline autônomo de SFT, merge e quantização
        ├── train_sft.py                     # autoral: pipeline SFT local, sem chamada à função train()
        ├── export_gguf.py                   # autoral: merge, conversão e quantização GGUF
        ├── requirements_pc.txt              # autoral: dependências do pipeline desktop
        └── __pycache__/                     # artefato gerado: bytecode Python 3.12
            └── colab_train_silva.cpython-312.pyc # bytecode potencialmente obsoleto do Colab
```

### 1.2 Inventário de arquivos autorais e artefatos

Contagens usam linhas físicas. Arquivos de dados JSONL são autorais; binários, `.pyc`, pacotes e `.git/` são artefatos.

| Caminho | Papel |
|---|---|
| `apply_tools_update.sh` (10 linhas) | Atualização ad hoc de `tools.py` e restart no Termux. |
| `install_model_and_restart.sh` (22 linhas) | Troca do GGUF ativo, backup de modelos e restart. |
| `resolved_activities.py` (70 linhas) | Mapa auxiliar de 70 pacotes Android para activities. |
| `start_silva_bootstrap.sh` (17 linhas) | Bootstrap de implantação Termux. |
| `test_open.py` (9 linhas) | Teste manual de `open_app("calculadora")`. |
| `update_and_restart.sh` (10 linhas) | Aplicação de patch e restart da API. |
| `update_direct.sh` (31 linhas) | Sincronização direta via ADB e reinício controlado no Termux. |
| `silva-agent/.env.example` (20 linhas) | Contrato de variáveis de ambiente. |
| `silva-agent/.gitignore` (41 linhas) | Exclusões de secrets, mídia, modelos, caches e backups. |
| `silva-agent/README.md` (214 linhas) | Documentação principal com arquitetura, catálogo de 35 ferramentas e guia de execução. |
| `silva-agent/android_agent/config.py` (69 linhas) | Configuração, paths e prompt de function calling. |
| `silva-agent/android_agent/intent_fallback.py` (828 linhas) | Regras determinísticas de intents, normalizador matemático e sanitização de cidades. |
| `silva-agent/android_agent/llm_client.py` (116 linhas) | Cliente HTTP do `llama-server`. |
| `silva-agent/android_agent/main.py` (104 linhas) | Entry point CLI/Web. |
| `silva-agent/android_agent/parser.py` (166 linhas) | Parser AST, whitelist e execução. |
| `silva-agent/android_agent/scheduler.py` (63 linhas) | Daemon em background para monitoramento de eventos e alarmes locais. |
| `silva-agent/android_agent/setup_termux.sh` (48 linhas) | Setup de dependências e build do `llama-server`. |
| `silva-agent/android_agent/start_silva.sh` (176 linhas) | Orquestração de inicialização idempotente, limpeza de processos e gestão de PIDs. |
| `silva-agent/android_agent/tools.py` (2.995 linhas) | Implementação das 35 ferramentas nativas. |
| `silva-agent/android_agent/web_server.py` (235 linhas) | Servidor HTTP com SO_REUSEADDR, fallback de porta e API de chat. |
| `silva-agent/android_agent/static/index.html` (1.776 linhas) | Frontend responsivo estilo Claude/DeepSeek com histórico local. |
| `silva-agent/dataset/schema.json` (393 linhas) | Contrato estrito de 35 ferramentas e 42 parâmetros. |
| `silva-agent/dataset/prepare_final_dataset.py` (383 linhas) | Preparação e split do dataset final. |
| `silva-agent/dataset/repair_train_dataset.py` (572 linhas) | Reparo/enriquecimento do dataset de treino. |
| `silva-agent/dataset/validate_dataset.py` (185 linhas) | Validador de dataset. |
| `silva-agent/dataset/seed_examples.jsonl` (104 linhas) | Base canônica de 104 exemplos. |
| `silva-agent/dataset/train.jsonl` (5.008 linhas) | Estado local de treino enriquecido com novas ferramentas e casos de uso. |
| `silva-agent/dataset/train.jsonl.bak` (4.140 linhas) | Backup anterior ao reparo. |
| `silva-agent/dataset/train_clean.jsonl` (4.356 linhas) | Divisão limpa de treino. |
| `silva-agent/dataset/eval_clean.jsonl` (229 linhas) | Divisão limpa de avaliação. |
| `silva-agent/dataset/silva_colab_dataset.jsonl` (4.585 linhas) | Dataset consolidado usado no Colab. |
| `silva-agent/pc_training/colab_train_silva.py` (339 linhas) | Pipeline completo Google Colab. |
| `silva-agent/pc_training/train_sft.py` (181 linhas) | Treinamento SFT desktop previsto. |
| `silva-agent/pc_training/export_gguf.py` (102 linhas) | Conversão HF→GGUF e quantização previstas. |
| `silva-agent/pc_training/requirements_pc.txt` (21 linhas) | Dependências não fixadas do treinamento. |
| `screen_termux.png` | Evidência visual de execução anterior; não é fonte. |
| `silva_deploy.tar.gz` | Snapshot de implantação antigo; não contém `intent_fallback.py`. |
| `silva_update.tar.gz` | Patch de implantação antigo; `tools.py` e fallback divergentes. |
| `termux-api.apk`, `termux-api-fdroid.apk` | Builds binários de terceiros. |
| `platform-tools/**` | Android platform-tools de terceiros, revisão `37.0.3`. |
| `silva-agent/android_agent/models/**/*.gguf` | Três binários GGUF; somente `silva-135m.gguf` é referenciado pelo start. |
| `**/__pycache__/*.pyc` | Bytecode Python 3.12 gerado. |
| `silva-agent/.git/**` | Metadados e objetos do Git. |

**Mecanismo real de persistência:** não há banco de dados. Runtime usa JSON local em `silva-agent/android_agent/data/`: `memory.json`, `last_location.json` e `dnd_backup.json` (`silva-agent/android_agent/tools.py:26-28`, `silva-agent/android_agent/tools.py:1190-1191`, `silva-agent/android_agent/tools.py:1673-1690`). Multimídia usa arquivos em `silva-agent/android_agent/captures/`; configuração usa `.env`; navegador usa `localStorage["silva_pin"]`; treinamento usa JSONL e artefatos GGUF. Não há escrita atômica, transação, lock ou versionamento de estado.

## 2. Anatomia Completa do Estado e Modelos de Dados

### 2.1 Raiz do estado do runtime

Não existe uma estrutura central única. O estado é distribuído entre:

1. memória volátil do processo: `llm_client` global, `_LAST_JOKE` e argumentos locais (`silva-agent/android_agent/web_server.py:21-22`, `silva-agent/android_agent/tools.py:1384-1392`);
2. arquivos JSON em `android_agent/data/`;
3. arquivos de mídia em `android_agent/captures/`;
4. configuração carregada de `.env`/`.env.example` (`silva-agent/android_agent/config.py:26-49`);
5. PIN persistido no navegador (`silva-agent/android_agent/static/index.html:505-510`).

### 2.2 `memory.json`

Raiz: objeto JSON `dict`; cada chave é a chave textual da nota. Escrita em `remember_note()` e lida por `_load_memory()` (`silva-agent/android_agent/tools.py:1677-1717`).

```text
{
  "<key>": {
    "value": string,
    "timestamp": "YYYY-MM-DD HH:MM:SS"
  }
}
```

- `key`: `str(key).strip()`, obrigatório e não vazio (`silva-agent/android_agent/tools.py:1702-1705`).
- `value`: `str(value).strip()`, obrigatório e não vazio (`silva-agent/android_agent/tools.py:1702-1705`).
- `timestamp`: `datetime.now().strftime("%Y-%m-%d %H:%M:%S")` (`silva-agent/android_agent/tools.py:1708-1711`).
- Campo persistido: todo o dicionário.
- Campo efêmero: score, tokens normalizados e candidatos durante `recall_note()` (`silva-agent/android_agent/tools.py:1734-1773`).

### 2.3 `last_location.json`

Raiz: objeto JSON; criado por `get_location()` nos modos simulado e real (`silva-agent/android_agent/tools.py:799-860`).

```text
{
  "latitude": float,
  "longitude": float,
  "timestamp": string ISO-8601,
  "maps_url": string,
  "image_url": string | null,
  "provider": string
}
```

- Simulação: `latitude=-23.550520`, `longitude=-46.633308`, `provider="simulated"` (`silva-agent/android_agent/tools.py:801-812`).
- Real: latitude/longitude convertidos para `float`; `provider=data.get("provider", "termux")` (`silva-agent/android_agent/tools.py:835-850`).
- `timestamp`: `datetime.now().isoformat()` (`silva-agent/android_agent/tools.py:808`, `silva-agent/android_agent/tools.py:846`).
- `image_url`: preview de mapa local ou `null` (`silva-agent/android_agent/tools.py:804-810`, `silva-agent/android_agent/tools.py:842-849`).

### 2.4 `dnd_backup.json`

Raiz: objeto JSON de volumes por stream (`silva-agent/android_agent/tools.py:1190-1231`).

```text
{
  "ring": integer,
  "notification": integer,
  "system": integer
}
```

- Streams alvo: `ring`, `notification`, `system` (`silva-agent/android_agent/tools.py:1206-1207`).
- Valor lido: `item.get("volume", 5)` (`silva-agent/android_agent/tools.py:1217-1220`).
- Default de stream ausente: `5` (`silva-agent/android_agent/tools.py:1224-1227`).
- Arquivo removido após restauração (`silva-agent/android_agent/tools.py:1256-1260`).

### 2.5 Capturas persistidas

Não há metadados em banco; o filename é parte do estado:

| Padrão | Entidade | Criação |
|---|---|---|
| `capture_YYYYMMDD_HHMMSS.jpg` | foto | `silva-agent/android_agent/tools.py:406-446` |
| `screen_<epoch>.png` | screenshot | `silva-agent/android_agent/tools.py:449-540` |
| `vid_<epoch>.mp4` | vídeo | `silva-agent/android_agent/tools.py:543-615` |
| `loc_<epoch>.png` | mapa | `silva-agent/android_agent/tools.py:710-796` |

### 2.6 Estado do cliente web

| Chave | Tipo | Default | Persistência |
|---|---|---|---|
| `silva_pin` | `string` | `"1234"` | `localStorage` (`silva-agent/android_agent/static/index.html:505-510`). |

Mensagens, histórico, anexos e preferências não são persistidos.

### 2.7 Modelo do dataset

Cada linha dos JSONL é um registro com duas chaves obrigatórias (`silva-agent/dataset/seed_examples.jsonl:1-104`):

```text
{
  "prompt": string,
  "completion": string contendo "<call>...</call>"
}
```

O contrato de tools é `dataset/schema.json:1-393`, mas é customizado e não JSON Schema Draft-07 aplicável. Contém 35 ferramentas, 42 parâmetros, tipos `string|integer|boolean`; obrigatoriedade é marcada por `"required": true` dentro do parâmetro (`silva-agent/dataset/schema.json:6-392`).

| Ferramenta | Parâmetros: tipo, obrigatoriedade, default | Schema |
|---|---|---|
| `get_battery` | nenhum | `silva-agent/dataset/schema.json:7-10` |
| `get_last_sms` | `limit: integer?`, default `5` | `silva-agent/dataset/schema.json:11-20` |
| `send_sms` | `number: string`; `message: string` | `silva-agent/dataset/schema.json:21-35` |
| `take_photo` | `camera_id: integer?`, default `0` | `silva-agent/dataset/schema.json:36-45` |
| `take_screenshot` | nenhum | `silva-agent/dataset/schema.json:46-49` |
| `search_google` | `query: string` | `silva-agent/dataset/schema.json:50-59` |
| `open_app` | `app_name: string` | `silva-agent/dataset/schema.json:60-69` |
| `make_call` | `number: string` | `silva-agent/dataset/schema.json:70-79` |
| `get_location` | nenhum | `silva-agent/dataset/schema.json:80-83` |
| `set_torch` | `state: boolean` | `silva-agent/dataset/schema.json:84-93` |
| `set_dnd` | `state: boolean` | `silva-agent/dataset/schema.json:94-103` |
| `vibrate` | `duration_ms: integer?`, default `500` | `silva-agent/dataset/schema.json:104-113` |
| `get_clipboard` | nenhum | `silva-agent/dataset/schema.json:114-117` |
| `set_clipboard` | `text: string` | `silva-agent/dataset/schema.json:118-127` |
| `tell_joke` | nenhum | `silva-agent/dataset/schema.json:128-131` |
| `set_alarm` | `time: string`; `label: string?`; `days: string?` | `silva-agent/dataset/schema.json:132-151` |
| `cancel_alarm` | `time: string?`; `day: string?`; `label: string?` | `silva-agent/dataset/schema.json:152-171` |
| `schedule_event` | `title: string`; `date: string?`; `time: string?` | `silva-agent/dataset/schema.json:172-191` |
| `remember_note` | `key: string`; `value: string` | `silva-agent/dataset/schema.json:192-206` |
| `recall_note` | `query: string` | `silva-agent/dataset/schema.json:207-216` |
| `get_notifications` | `app: string?` | `silva-agent/dataset/schema.json:217-226` |
| `set_volume` | `stream: string?`, default `"media"`; `level: integer` | `silva-agent/dataset/schema.json:227-242` |
| `set_brightness` | `level: integer` | `silva-agent/dataset/schema.json:243-252` |
| `set_timer` | `minutes: integer`; `label: string?` | `silva-agent/dataset/schema.json:253-267` |
| `calculate` | `expression: string` | `silva-agent/dataset/schema.json:268-277` |
| `set_location_state` | `state: boolean` | `silva-agent/dataset/schema.json:278-287` |
| `get_last_location` | nenhum | `silva-agent/dataset/schema.json:288-291` |
| `get_weather` | `day: string?`, default `"hoje"`; `time: string?`, default `""`; `location: string?`, default `""` | `silva-agent/dataset/schema.json:292-314` |
| `record_video` | `duration: integer?`, default `10`; `camera_id: integer?`, default `0` | `silva-agent/dataset/schema.json:315-331` |
| `request_ride` | `destination: string`; `app: string?`, default `"uber"` | `silva-agent/dataset/schema.json:332-348` |
| `order_food` | `query: string`; `app: string?`, default `"ifood"` | `silva-agent/dataset/schema.json:349-365` |
| `install_app` | `app_name: string` | `silva-agent/dataset/schema.json:366-375` |
| `media_control` | `action: string` (`play/pause/next/previous`) | `silva-agent/dataset/schema.json:376-385` |
| `list_capabilities` | nenhum | `silva-agent/dataset/schema.json:386-389` |
| `none` | nenhum | `silva-agent/dataset/schema.json:390-393` |

Não há enums formais. Limites citados (`camera_id` 0/1, vídeo 3–120, volume/brilho 0–100) aparecem em descrições, não como `enum`, `minimum` ou `maximum` (`silva-agent/dataset/schema.json:36-45`, `silva-agent/dataset/schema.json:227-252`, `silva-agent/dataset/schema.json:315-331`).

### 2.8 Persistência efêmera de execução

- `parsed`, `raw_blocks`, `valid_calls`: parse local por requisição (`silva-agent/android_agent/parser.py:26-90`).
- `calls`, `executed_details`, `messages`, `raw_calls`: consolidação por execução (`silva-agent/android_agent/parser.py:112-155`).
- `latest_image_url` e `latest_video_url`: apenas a última mídia de cada tipo sobrevive no topo (`silva-agent/android_agent/parser.py:116-135`).
- `_LAST_JOKE`: evita repetição consecutiva, mas é compartilhado entre threads (`silva-agent/android_agent/tools.py:1384-1392`).

## 3. Mapeamento Detalhado de Todos os Arquivos Backend / Core

### 3.1 `silva-agent/android_agent/config.py`

Configuração central e prompt.

- `load_env(env_path: Path)` → `None`: lê `.env`, ignora vazios/comentários/linhas sem `=`, remove aspas e não sobrescreve variáveis existentes (`silva-agent/android_agent/config.py:11-23`).
- `BASE_DIR` → `Path`: diretório do pacote (`silva-agent/android_agent/config.py:26`).
- `PROJECT_ROOT` → `Path`: raiz do repositório (`silva-agent/android_agent/config.py:27`).
- `ENV_FILE` → `Path`: `.env`, com fallback para `.env.example` (`silva-agent/android_agent/config.py:28-32`).
- `WEB_HOST` → `str`, default `"0.0.0.0"`; `WEB_PORT` → `int`, default `5000`; `ACCESS_PIN` → `str`, default `"1234"` (`silva-agent/android_agent/config.py:34-37`).
- `LLAMA_SERVER_URL` → `str`, default `"http://127.0.0.1:8080"`; `LLM_TIMEOUT_SECONDS` → `int`, default `15` (`silva-agent/android_agent/config.py:39-41`).
- `CAPTURES_DIR` → `Path`: sempre `BASE_DIR / "captures"`; diretório criado no import (`silva-agent/android_agent/config.py:43-45`).
- `HAS_TERMUX` → `bool`; `SIMULATE_HARDWARE` → `bool` (`silva-agent/android_agent/config.py:47-49`).
- `SILVA_SYSTEM_PROMPT` → `str`: lista as tools e restringe output a tags `<call>` (`silva-agent/android_agent/config.py:51-68`).

### 3.2 `silva-agent/android_agent/main.py`

- `print_banner()` → `None`: imprime URL do LLM e estado de simulação (`silva-agent/android_agent/main.py:17-30`).
- `run_cli_mode()` → `None`: loop `input()`, aceita calls diretas, consulta o cliente LLM e executa (`silva-agent/android_agent/main.py:33-75`).
- `run_web_mode(host: str, port: int)` → `None`: banner, PIN em claro e `start_server()` (`silva-agent/android_agent/main.py:78-85`).
- `main()` → `None`: parse de `--web`, `--cli`, `--host`, `--port`; web é o default (`silva-agent/android_agent/main.py:87-100`).

### 3.3 `silva-agent/android_agent/web_server.py`

- `ReusableThreadingHTTPServer(ThreadingHTTPServer)`: subclasse com `allow_reuse_address = True` (`SO_REUSEADDR`) e `daemon_threads = True` para liberação imediata da porta e encerramento limpo (`silva-agent/android_agent/web_server.py:24-30`).
- `SilvaHTTPRequestHandler._send_json(data: dict, status: int = HTTPStatus.OK)` → `None`: JSON UTF-8 e CORS `*` (`silva-agent/android_agent/web_server.py:33-41`).
- `SilvaHTTPRequestHandler._send_file(file_path: Path, mime_type: str)` → `None`: envia arquivo ou 404 (`silva-agent/android_agent/web_server.py:43-53`).
- `SilvaHTTPRequestHandler.do_OPTIONS()` → `None`: preflight 204 (`silva-agent/android_agent/web_server.py:55-61`).
- `SilvaHTTPRequestHandler.do_GET()` → `None`: roteia `/`, `/index.html`, `/captures/*`, `/api/health` (`silva-agent/android_agent/web_server.py:63-102`).
- `SilvaHTTPRequestHandler.do_POST()` → `None`: valida PIN/body, gera call e executa (`silva-agent/android_agent/web_server.py:104-165`).
- `start_server(host: str = WEB_HOST, port: int = WEB_PORT)` → `None`: instancia `ReusableThreadingHTTPServer`, com fallback dinâmico de portas (`port` até `port + 5`) em caso de `errno.EADDRINUSE`, registra handlers de `SIGINT`/`SIGTERM` e chama `shutdown()`/`server_close()` no encerramento (`silva-agent/android_agent/web_server.py:168-235`).

### 3.4 `silva-agent/android_agent/llm_client.py`

- `SilvaLLMClient.__init__(base_url: str = LLAMA_SERVER_URL, timeout: int = LLM_TIMEOUT_SECONDS)` → `None`: normaliza URL (`silva-agent/android_agent/llm_client.py:18-20`).
- `SilvaLLMClient.check_health()` → `dict`: tenta `/health`, depois `/`; retorna `online/status/url/error` (`silva-agent/android_agent/llm_client.py:22-37`).
- `SilvaLLMClient.generate_call(user_prompt: str)` → `Tuple[Optional[str], float, Optional[str]]`: fallback local, prompt ChatML, `POST /completion`, normalização da tag e validação superficial de tool (`silva-agent/android_agent/llm_client.py:39-116`).

### 3.5 `silva-agent/android_agent/intent_fallback.py`

- `normalize_text(text: str)` → `str`: NFKD, remove diacríticos, minúsculas e `strip()` (`silva-agent/android_agent/intent_fallback.py:14-18`).
- `_normalize_math_expression(raw_text: str)` → `Optional[str]`: traduz números por extenso (`zero`..`mil`), operadores (`vezes`, `x`, `dividido por`, `mais`, `menos`, `ao quadrado`, etc.) e porcentagens para expressão Python válida (`silva-agent/android_agent/intent_fallback.py:35-115`).
- `_clean_weather_location(raw_loc: str)` → `str`: sanitiza nomes de cidades/estados, remove termos de tempo e ruídos (`hoje`, `amanhã`, turnos, `silva`, `por favor`), aceita preposições `de/em/no/na/para/pra` e normaliza capitalização (`silva-agent/android_agent/intent_fallback.py:278-348`).
- `parse_single_intent(raw_cmd: str)` → `Optional[str]`: roteamento determinístico cobrindo 35 ferramentas nativas (`silva-agent/android_agent/intent_fallback.py:351-792`).
- `match_intent_fallback(user_prompt: str)` → `Optional[str]`: divide cláusulas por conectores (` e `, ` depois `, ` em seguida `, `;`), executa fallback por cláusula e combina tags em chamadas compostas (`silva-agent/android_agent/intent_fallback.py:795-828`).

### 3.6 `silva-agent/android_agent/parser.py`

- `parse_function_calls(model_output: str)` → `List[Tuple[str, Dict[str, Any]]]`: extrai tags, aplica whitelist, AST literal, binding de assinatura, defaults e validação estrita de `bool` (`silva-agent/android_agent/parser.py:19-90`).
- `parse_function_call(model_output: str)` → `Dict[str, Any]`: compatibilidade de call única; sempre retorna `is_valid=True` porque a entrada é normalizada para `none()` (`silva-agent/android_agent/parser.py:93-104`).
- `execute_call(model_output: str)` → `Dict[str, Any]`: executa calls em sequência, agrega mensagens/dados e retorna status externo fixo `"ok"` (`silva-agent/android_agent/parser.py:107-166`).

### 3.7 `silva-agent/android_agent/tools.py`

#### Helpers e estruturas

- `sanitize_phone_number(number: str)` → `str`: mantém dígitos e `+` inicial (`silva-agent/android_agent/tools.py:203-208`).
- `resolve_contact_or_number(target: str)` → `str`: resolve contato por substring ou sanitiza número (`silva-agent/android_agent/tools.py:211-239`).
- `_run_termux_cmd(cmd: list[str], timeout: int = 10)` → `subprocess.CompletedProcess`: argv sem shell, resolução de binários e fallback shell (`silva-agent/android_agent/tools.py:242-282`).
- `_exec_android_intent(cmd_str: str, timeout: int = 6)` → `subprocess.CompletedProcess`: executa string via `sh -c` (`silva-agent/android_agent/tools.py:285-307`).
- `_generate_map_preview(lat: float, lon: float)` → `Optional[str]`: tile Web Mercator OSM ou mapa Pillow local (`silva-agent/android_agent/tools.py:710-796`).
- `_load_memory()` → `dict`; `_save_memory(data: dict)` → `None`: JSON local de notas (`silva-agent/android_agent/tools.py:1677-1690`).
- `_normalize_text(text: str)` → `str`: normalização usada na busca de notas (`silva-agent/android_agent/tools.py:1693-1697`).
- `SafeMathEvaluator(ast.NodeVisitor)` com `visit`, `generic_visit`, `visit_Expression`, `visit_Constant`, `visit_UnaryOp`, `visit_BinOp`: allowlist aritmética (`silva-agent/android_agent/tools.py:1951-2001`).

#### Catálogo integral das ferramentas

| Função → retorno | Efeito principal | Referência |
|---|---|---|
| `get_battery()` → `dict` | Estado e carga da bateria | `silva-agent/android_agent/tools.py:310-339` |
| `get_last_sms(limit=5)` → `dict` | Lê SMS recentes | `silva-agent/android_agent/tools.py:342-373` |
| `send_sms(number, message)` → `dict` | Envia SMS | `silva-agent/android_agent/tools.py:376-403` |
| `take_photo(camera_id=0)` → `dict` | Captura JPEG | `silva-agent/android_agent/tools.py:406-446` |
| `take_screenshot()` → `dict` | Captura tela | `silva-agent/android_agent/tools.py:449-540` |
| `record_video(duration=10, camera_id=0)` → `dict` | Intent de gravação e cópia do arquivo | `silva-agent/android_agent/tools.py:543-615` |
| `open_app(app_name)` → `dict` | Abre activity Android | `silva-agent/android_agent/tools.py:618-681` |
| `make_call(number)` → `dict` | Disca | `silva-agent/android_agent/tools.py:684-707` |
| `get_location()` → `dict` | GPS e persiste `last_location.json` | `silva-agent/android_agent/tools.py:799-863` |
| `set_location_state(state)` → `dict` | Liga/desliga GPS ou abre settings | `silva-agent/android_agent/tools.py:866-905` |
| `get_last_location()` → `dict` | Lê último JSON e formata data | `silva-agent/android_agent/tools.py:908-951` |
| `get_weather(day="hoje", time="", location="")` → `dict` | Open-Meteo | `silva-agent/android_agent/tools.py:976-1143` |
| `set_torch(state)` → `dict` | Liga/desliga lanterna | `silva-agent/android_agent/tools.py:1146-1170` |
| `set_dnd(state)` → `dict` | DND nativo ou fallback por volume | `silva-agent/android_agent/tools.py:1173-1273` |
| `vibrate(duration_ms=500)` → `dict` | Vibração | `silva-agent/android_agent/tools.py:1276-1297` |
| `get_clipboard()` → `dict` | Lê clipboard | `silva-agent/android_agent/tools.py:1300-1321` |
| `set_clipboard(text)` → `dict` | Escreve clipboard | `silva-agent/android_agent/tools.py:1324-1351` |
| `tell_joke()` → `dict` | Piada aleatória sem repetição consecutiva | `silva-agent/android_agent/tools.py:1387-1397` |
| `parse_ptbr_date(date_str)` → `date` | Interpreta datas PT-BR | `silva-agent/android_agent/tools.py:1416-1495` |
| `parse_time_str(time_str)` → `tuple[int,int]` | Interpreta hora | `silva-agent/android_agent/tools.py:1498-1526` |
| `set_alarm(time, label="", days="")` → `dict` | Intent `SET_ALARM` | `silva-agent/android_agent/tools.py:1529-1565` |
| `cancel_alarm(time="", day="", label="")` → `dict` | Intent `DISMISS_ALARM` | `silva-agent/android_agent/tools.py:1568-1614` |
| `schedule_event(title, date="", time="")` → `dict` | Intent de calendário | `silva-agent/android_agent/tools.py:1617-1670` |
| `remember_note(key, value)` → `dict` | Salva nota | `silva-agent/android_agent/tools.py:1700-1717` |
| `recall_note(query)` → `dict` | Busca ranqueada de notas | `silva-agent/android_agent/tools.py:1720-1779` |
| `get_notifications(app="")` → `dict` | Lê notificações | `silva-agent/android_agent/tools.py:1782-1836` |
| `set_volume(stream="media", level=50)` → `dict` | Ajusta volume | `silva-agent/android_agent/tools.py:1839-1886` |
| `set_brightness(level)` → `dict` | Ajusta brilho | `silva-agent/android_agent/tools.py:1889-1911` |
| `set_timer(minutes, label="")` → `dict` | Intent `SET_TIMER` | `silva-agent/android_agent/tools.py:1914-1948` |
| `calculate(expression)` → `dict` | Avaliador aritmético seguro com AST | `silva-agent/android_agent/tools.py:2400-2440` |
| `search_google(query)` → `dict` | Abre Google e busca snippet DDG | `silva-agent/android_agent/tools.py:2445-2510` |
| `request_ride(destination, app="uber")` → `dict` | Intent para Uber ou 99 com destino configurado | `silva-agent/android_agent/tools.py:2550-2595` |
| `order_food(query, app="ifood")` → `dict` | Intent para iFood ou 99Food buscando o prato | `silva-agent/android_agent/tools.py:2598-2645` |
| `install_app(app_name)` → `dict` | Abre Google Play Store na página do app | `silva-agent/android_agent/tools.py:2648-2688` |
| `media_control(action)` → `dict` | Controle de mídia via `cmd media_session` e KeyEvents | `silva-agent/android_agent/tools.py:2691-2740` |
| `list_capabilities()` → `dict` | Catálogo de ferramentas e exemplos | `silva-agent/android_agent/tools.py:2743-2790` |
| `none()` → `dict` | Resposta neutra | `silva-agent/android_agent/tools.py:2800-2810` |

`AVAILABLE_TOOLS` registra exatamente essas 35 funções, sem wrappers ou aliases (`silva-agent/android_agent/tools.py:2950-2995`).

### 3.8 `silva-agent/dataset/validate_dataset.py`

- `load_schema(schema_path)` → `dict`: lê o schema (`silva-agent/dataset/validate_dataset.py:19-24`).
- `parse_call_args(args_str)` → `dict`: extrai kwargs via regex/AST e rejeita positional args (`silva-agent/dataset/validate_dataset.py:27-46`).
- `validate_args_against_schema(tool_name, args, tool_def)` → `tuple[bool,str]`: checa tool, chaves, required e tipos (`silva-agent/dataset/validate_dataset.py:49-73`).
- `validate_dataset(jsonl_path, schema_path)` → `dict`: valida cada linha e produz contagens/percentuais (`silva-agent/dataset/validate_dataset.py:76-176`).

### 3.9 `silva-agent/dataset/prepare_final_dataset.py`

- `load_schema(schema_file)` → `dict` (`silva-agent/dataset/prepare_final_dataset.py:30-35`).
- `parse_call_args(args_str)` → `dict` (`silva-agent/dataset/prepare_final_dataset.py:38-52`).
- `validate_args(tool_name, args, tool_def)` → `tuple[bool,str]` (`silva-agent/dataset/prepare_final_dataset.py:55-77`).
- `validate_line(item, tools_schema)` → `tuple[bool,str]` (`silva-agent/dataset/prepare_final_dataset.py:80-111`).
- `generate_named_contact_examples(count_needed=300)` → `list[dict]`: gera exemplos de `make_call` e `send_sms` (`silva-agent/dataset/prepare_final_dataset.py:114-242`).
- `main()` → `None`: combina fontes, valida, deduplica, embaralha e grava consolidado/splits (`silva-agent/dataset/prepare_final_dataset.py:245-379`).

### 3.10 `silva-agent/dataset/repair_train_dataset.py`

- `load_schema(schema_file)` → `dict` (`silva-agent/dataset/repair_train_dataset.py:25-27`).
- `fix_line(item)` → `dict`: corrige parâmetros legados e normaliza calls (`silva-agent/dataset/repair_train_dataset.py:30-57`).
- `generate_enrichment_samples()` → `list[dict]`: gera amostras adicionais (`silva-agent/dataset/repair_train_dataset.py:60-472`).
- `main()` → `None`: repara, valida parcialmente, deduplica e regrava `train.jsonl` (`silva-agent/dataset/repair_train_dataset.py:475-568`).

### 3.11 `silva-agent/pc_training/train_sft.py`

- `detect_device()` → `str`: escolhe `cuda`, `directml` ou `cpu` (`silva-agent/pc_training/train_sft.py:40-56`).
- `format_dataset_samples(jsonl_path)` → `list[dict]`: converte JSONL em amostras ChatML (`silva-agent/pc_training/train_sft.py:59-81`).
- `train(...)` → `None`: carrega base/adapter, cria `SFTTrainer` e salva output (`silva-agent/pc_training/train_sft.py:84-165`).
- CLI em `silva-agent/pc_training/train_sft.py:168-181`: apenas imprime configuração; não chama `train()`.

### 3.12 `silva-agent/pc_training/export_gguf.py`

- `merge_lora_weights(...)` → `None`: funde adapter no modelo HF (`silva-agent/pc_training/export_gguf.py:17-40`).
- `convert_to_gguf(...)` → `None`: converte HF para GGUF FP16 (`silva-agent/pc_training/export_gguf.py:43-65`).
- `quantize_gguf(...)` → `None`: executa `llama-quantize` (`silva-agent/pc_training/export_gguf.py:68-88`).
- CLI em `silva-agent/pc_training/export_gguf.py:91-102`: apenas imprime configuração; não chama as três etapas.

### 3.13 `silva-agent/pc_training/colab_train_silva.py`

Sem classes ou funções; pipeline top-level:

1. instalação/setup de dependências e `llama.cpp` (`silva-agent/pc_training/colab_train_silva.py:9-52`);
2. upload e leitura do JSONL (`silva-agent/pc_training/colab_train_silva.py:54-72`);
3. formatação ChatML e SFT/LoRA (`silva-agent/pc_training/colab_train_silva.py:74-253`);
4. inferência de teste (`silva-agent/pc_training/colab_train_silva.py:255-299`);
5. conversão e quantização GGUF (`silva-agent/pc_training/colab_train_silva.py:301-339`).

### 3.14 Scripts operacionais autorais

| Arquivo | Operação e efeitos |
|---|---|
| `silva-agent/android_agent/setup_termux.sh` | Atualiza índices, instala `python`, `termux-api` e toolchain; constrói `llama-server`; cria `captures/`/`models/` (`silva-agent/android_agent/setup_termux.sh:10-44`). |
| `silva-agent/android_agent/start_silva.sh` | Localiza servidor/modelo, instala trap, inicia `llama-server` e `main.py --web --port 5000` (`silva-agent/android_agent/start_silva.sh:6-83`). |
| `start_silva_bootstrap.sh` | Extrai `silva_deploy.tar.gz`, executa setup e start (`start_silva_bootstrap.sh:3-17`). |
| `update_and_restart.sh` | Extrai `silva_update.tar.gz`, mata APIs Python e reinicia (`update_and_restart.sh:1-10`). |
| `apply_tools_update.sh` | Copia `tools.py`, mata processos e reinicia (`apply_tools_update.sh:1-10`). |
| `install_model_and_restart.sh` | Move GGUF anterior, copia novo, encerra serviços e reinicia (`install_model_and_restart.sh:1-22`). |
| `resolved_activities.py` | Define `RESOLVED_APP_ACTIVITIES` com 70 pacotes (`resolved_activities.py:1-70`). |
| `test_open.py` | Executa `monkey` e `tools.open_app("calculadora")`, sem assertions (`test_open.py:1-9`). |

## 4. Fórmulas Reais, Regras de Negócio e Fluxos Críticos

### 4.1 Limites e conversões

```text
SMS limit = max(1, min(int(limit), 20))
(silva-agent/android_agent/tools.py:344)

video duration = max(3, min(int(duration), 120))
camera_id = 1 if int(camera_id) == 1 else 0
(silva-agent/android_agent/tools.py:545-546)

vibration duration = max(50, min(int(duration_ms), 5000))
(silva-agent/android_agent/tools.py:1278)

brightness percent = max(0, min(int(level), 100))
brightness_255 = round((brightness_percent / 100.0) * 255)
(silva-agent/android_agent/tools.py:1891-1892)

volume percent = max(0, min(int(level), 100))
volume = round((volume_percent / 100.0) * max_volume)
(silva-agent/android_agent/tools.py:1851-1855)

timer minutes = max(1, int(minutes))
timer seconds = minutes * 60
(silva-agent/android_agent/tools.py:1916-1917)

event begin_ms = int(dt_event.timestamp() * 1000)
event end_ms = begin_ms + (3600 * 1000)
(silva-agent/android_agent/tools.py:1625-1627)
```

### 4.2 Projeção Web Mercator do mapa

```text
n = 1 << zoom                         # zoom = 16
x_exact = (lon + 180.0) / 360.0 * n
x_tile = int(x_exact)
lat_rad = math.radians(lat)
y_exact = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
y_tile = int(y_exact)
(silva-agent/android_agent/tools.py:721-727)
```

### 4.3 Score da memória

```text
score = 0
if norm_query == norm_key: score += 10
elif norm_query in norm_key: score += 6
elif norm_key in norm_query: score += 5
score += 2 * len(query_tokens & key_tokens)
if norm_query in norm_value: score += 3
keep score > 0
sort descending
return first 3
(silva-agent/android_agent/tools.py:1734-1778)
```

### 4.4 Resolução de data e hora

- `hoje`: data corrente; `amanhã`: `+1 dia`; `depois de amanhã`: `+2 dias` (`silva-agent/android_agent/tools.py:1423-1431`).
- Weekday: `(target_weekday - today_weekday) % 7`; se o alvo é o dia atual, avança 7 (`silva-agent/android_agent/tools.py:1433-1448`).
- Data por extenso com ano de dois dígitos: `year + 2000`; data passada sem ano explícito passa ao ano seguinte (`silva-agent/android_agent/tools.py:1450-1468`).
- Data inválida/não reconhecida retorna hoje; hora inválida retorna `(9, 0)` (`silva-agent/android_agent/tools.py:1492-1495`, `silva-agent/android_agent/tools.py:1498-1502`).

### 4.5 Clima

```text
amanhã: today + 1 day
depois de amanhã: today + 2 days
weekday: (target - today.weekday()) % 7; current weekday => +7
night => 20h; tarde => 15h; manhã => 9h; madrugada => 3h
(silva-agent/android_agent/tools.py:1022-1067)
```

Sem cidade e sem última localização, usa `-7.9408, -34.8730, "Paulista"` (`silva-agent/android_agent/tools.py:1017-1020`).

### 4.6 Avaliador matemático

Permite `+`, `-`, `*`, `/`, `//`, `%`, `**`, unário `+`/`-`; constantes `int`/`float`. Exponente só é rejeitado quando `abs(right) > 1000`; divisão/módulo por zero são rejeitados (`silva-agent/android_agent/tools.py:1951-2001`). Formatação fracionária:

```text
f"{result:.4f}".rstrip("0").rstrip(".")
(silva-agent/android_agent/tools.py:2017-2020)
```

### 4.7 Dataset

```text
half = count_needed // 2
call_samples = half
send_sms_samples = count_needed - half
# count_needed=300 => 150 + 150
(silva-agent/dataset/prepare_final_dataset.py:211-242)

dedup_key = " ".join(item["prompt"].strip().lower().split())
(silva-agent/dataset/prepare_final_dataset.py:310-321)

eval_count = max(1, int(total_total * 0.05))
train_count = total_total - eval_count
# 4585 => eval=229, train=4356
(silva-agent/dataset/prepare_final_dataset.py:327-333)
```

Parâmetros SFT/LoRA no Colab: `r=16`, `lora_alpha=32`, `lora_dropout=0.05`, módulos `q,k,v,o,gate,up,down`, `epochs=3`, `batch_size=16`, `gradient_accumulation_steps=2`, `learning_rate=3e-4`, `weight_decay=0.01`, `warmup_steps=20`, `max_length=256` (`silva-agent/pc_training/colab_train_silva.py:165-203`).

### 4.8 Fluxo de boot

1. `start_silva.sh` entra no diretório do runtime e solicita wake lock (`silva-agent/android_agent/start_silva.sh:6-9`).
2. Localiza `llama-server` e GGUF (`silva-agent/android_agent/start_silva.sh:15-32`).
3. Instala trap de cleanup (`silva-agent/android_agent/start_silva.sh:35-45`).
4. Inicia `llama-server` em `127.0.0.1:8080`, contexto 2048 e 4 threads (`silva-agent/android_agent/start_silva.sh:47-56`).
5. Executa `python3 main.py --web --port 5000` (`silva-agent/android_agent/start_silva.sh:83`).

### 4.9 Fluxo HTTP de chat

1. `do_POST` valida `X-Access-Pin` contra `ACCESS_PIN` (`silva-agent/android_agent/web_server.py:93-101`).
2. Lê `Content-Length`, body e JSON (`silva-agent/android_agent/web_server.py:103-112`).
3. Exige `body["message"]` não vazio (`silva-agent/android_agent/web_server.py:114-119`).
4. Call direta `<call>...</call>` é executada; demais mensagens vão a `generate_call()` (`silva-agent/android_agent/web_server.py:121-128`).
5. `generate_call()` tenta fallback determinístico antes do LLM (`silva-agent/android_agent/llm_client.py:44-51`).
6. Sem fallback, envia ChatML ao `POST /completion` (`silva-agent/android_agent/llm_client.py:53-81`).
7. O parser extrai, valida e executa sequencialmente (`silva-agent/android_agent/parser.py:19-166`).
8. A resposta HTTP agrega `latency_ms` (`silva-agent/android_agent/web_server.py:141-145`).

### 4.10 Fluxo de dataset e treinamento

1. Backup `train.jsonl.bak` é reparado e enriquecido por `repair_train_dataset.py` (`silva-agent/dataset/repair_train_dataset.py:475-568`).
2. `train.jsonl` + seed + contatos sintéticos são validados/deduplicados (`silva-agent/dataset/prepare_final_dataset.py:245-321`).
3. O conjunto é embaralhado e dividido 4.356/229 (`silva-agent/dataset/prepare_final_dataset.py:323-349`).
4. O Colab converte registros em ChatML, aplica LoRA/SFT, funde o adapter e gera GGUF (`silva-agent/pc_training/colab_train_silva.py:74-339`).
5. O runtime carrega o GGUF via `llama-server` (`silva-agent/android_agent/start_silva.sh:26-56`).

## 5. Catálogo Completo de Rotas, Endpoints e Comandos

### 5.1 API HTTP

| Método + URL | Payload / Parâmetros | Ação e resposta |
|---|---|---|
| `GET /` | nenhum | 200 com `static/index.html`; 404 se ausente (`silva-agent/android_agent/web_server.py:62-65`). |
| `GET /index.html` | nenhum | Mesmo arquivo da raiz (`silva-agent/android_agent/web_server.py:62-65`). |
| `GET /captures/<filename>` | filename URL-decoded | 200 com arquivo; 404 ausente; 403 se `safe_path` não iniciar com o prefixo de `CAPTURES_DIR` (`silva-agent/android_agent/web_server.py:67-76`). |
| `GET /api/health` | nenhum | 200 `{"status":"ok","agent":"Silva","llm":{"online":bool,"status":str,"url":str,"error"?:str}}` (`silva-agent/android_agent/web_server.py:78-85`). |
| `POST /api/chat` | body `{"message": string}`; header `X-Access-Pin` se `ACCESS_PIN` configurado | 403 `{"status":"error","message":"PIN de acesso inválido ou ausente."}`; 400 para JSON inválido ou mensagem vazia; 200 com o retorno de `execute_call()` (`silva-agent/android_agent/web_server.py:93-145`). |
| `OPTIONS *` | headers de preflight | 204; CORS `*`, métodos `GET, POST, OPTIONS`, headers `Content-Type, X-Access-Pin` (`silva-agent/android_agent/web_server.py:50-56`). |
| `GET /api/health` (llama-server) | nenhum | Health local do modelo; fallback para `GET /` (`silva-agent/android_agent/llm_client.py:22-37`). |
| `POST /completion` (llama-server) | `prompt`, `temperature=0.0`, `n_predict=48`, `stop`, `stream=false`, `cache_prompt=true` | Retorna `content`; latência medida (`silva-agent/android_agent/llm_client.py:53-109`). |

Formato de sucesso do parser, base do `/api/chat`:

```json
{
  "status": "ok",
  "message": "string",
  "raw_call": "string",
  "func_name": "string | multi_call",
  "calls": [{"func_name": "string", "args": {}, "status": "string", "data": null}],
  "data": [],
  "image_url": null,
  "video_url": null,
  "latency_ms": 0.0
}
```

Referências: `silva-agent/android_agent/parser.py:157-165`, `silva-agent/android_agent/web_server.py:141-145`.

### 5.2 Comandos CLI

| Comando | Parâmetros | Ação |
|---|---|---|
| `python3 main.py --web` | `--host`, `--port` opcionais | Inicia servidor web; `--web` é default (`silva-agent/android_agent/main.py:87-100`). |
| `python3 main.py --cli` | entrada stdin | Entra no loop de perguntas (`silva-agent/android_agent/main.py:33-75`). |
| `sair`, `exit`, `quit` no CLI | nenhum | Encerra CLI (`silva-agent/android_agent/main.py:49-51`). |
| `<call>get_battery()</call>` no CLI/Web | tag completa | Execução direta, ainda passa pelo parser (`silva-agent/android_agent/main.py:53-56`, `silva-agent/android_agent/web_server.py:121-125`). |

### 5.3 Handlers/ferramentas

Todas as 35 funções de `AVAILABLE_TOOLS` são comandos de function calling (`silva-agent/android_agent/tools.py:2950-2995`). Assinaturas, defaults, efeitos e referências estão em §3.7.

## 6. Arquitetura do Frontend / Interface de Usuário

### 6.1 Bootstrap e estado cliente

Não há framework ou bundler externo. `static/index.html` contém CSS e JavaScript moderno inline, 100% offline (sem CDNs ou dependências externas), e é servido diretamente pelo `ReusableThreadingHTTPServer` (`silva-agent/android_agent/web_server.py:63-102`).

- Inicialização: captura elementos DOM, restaura `localStorage["silva_pin"] || "1234"` e carrega a lista de conversas de `localStorage["silva_chats_v2"]` (`silva-agent/android_agent/static/index.html`).
- Health: `checkHealth()` consulta `/api/health` a cada 10 segundos, atualizando os badges de status do servidor e da LLM no topo da tela.
- Estado em runtime: gerenciamento local de histórico de conversas em `chats = {}` e `activeChatId`, permitindo criar novas sessões, alternar entre chats anteriores e limpar o histórico.
- Chat: envio via `handleSend()` disparando `POST /api/chat` com payload JSON `{"message": string}` e header de segurança `X-Access-Pin`.

### 6.2 Telas e módulos visuais

| Módulo | Elementos DOM | Estilo e Funcionalidade | Contrato |
|---|---|---|---|
| Sidebar de Conversas | `#sidebar`, `#btnNewChat`, `#chatList`, `#btnClearHistory` | Sidebar retrátil lateral esquerda com histórico persistido em `localStorage` | `localStorage["silva_chats_v2"]` |
| Header Minimalista | `#sidebarToggle`, `#statusDot`, `#statusText`, `#btnSetPin` | Barra superior estilo Claude/ChatGPT com status da LLM, toggle de sidebar e modal de PIN | `localStorage["silva_pin"]`, `GET /api/health` |
| Tela de Boas-Vindas | `.welcome-screen`, `.quick-grid`, `.quick-card` | Cards interativos no início do chat para acionamento rápido de capacidades | `sendQuick(text)` |
| Área de Mensagens | `#chatArea`, `.message-bubble`, `.message-avatar` | Bolhas de mensagens com suporte a Markdown offline básico, cards de localização e players de mídia | `POST /api/chat` |
| Barra de Input | `#chatForm`, `#messageInput`, `#sendBtn` | Campo de texto expansível com envio por Enter e bloqueio durante requisições | `handleSend(event)` |
| Modal de PIN | `#pinModal`, `#pinInputModal`, `#savePinBtn` | Modal nativo para configuração e armazenamento seguro do PIN na rede local | `localStorage["silva_pin"]` |
| Modal de Imagem | `#imageModal`, `#modalImg`, `#closeModal` | Visualização fullscreen de fotos tiradas pela câmera e capturas de tela | `image_url` |

### 6.3 Funções JavaScript Principais

| Função | Efeito |
|---|---|
| `checkHealth()` | Atualiza indicadores de telemetria da LLM e servidor consumindo `GET /api/health`. |
| `saveChats()` / `loadChats()` | Serializa e restaura sessões de chat em `localStorage["silva_chats_v2"]`. |
| `createNewChat()` / `switchChat(id)` | Cria uma nova sessão ou carrega histórico existente na área de mensagens. |
| `sendQuick(text)` | Insere texto da ação rápida no input e dispara o envio automaticamente. |
| `appendMessage(role, data)` | Renderiza balão de mensagem do usuário ou do Silva, incluindo badges de latência, tags de debug e mídias. |
| `formatMarkdown(text)` | Renderizador Markdown seguro e offline (negrito, itálico, código em bloco, quebras). |
| `handleSend(event)` | Submete a mensagem ao endpoint `/api/chat`, exibe estado de loading e trata respostas de erro. |
| `openImageModal(url)` | Abre fotos capturadas em visualizador modal com fundo escurecido. |

### 6.4 Tokens visuais

Design System com tema escuro refinado (`#18181b` / `#09090b`):
- Fundo e superfícies: `--bg-primary: #09090b`, `--bg-secondary: #18181b`, `--bg-tertiary: #27272a`.
- Acentos e bordas: `--border: #27272a`, `--accent: #6366f1`, `--accent-hover: #4f46e5`.
- Textos: `--text-primary: #f4f4f5`, `--text-secondary: #a1a1aa`, `--text-muted: #71717a`.
- Status: `--status-online: #10b981`, `--status-offline: #ef4444`.

## 7. Pontos de Atenção, Pendências e Acoplamentos Importantes

### 7.1 Melhorias Recentes Concluídas

1. **Blindagem de Sockets e Idempotência de Boot**:
   - `web_server.py` utiliza `ReusableThreadingHTTPServer` com `SO_REUSEADDR` e threads daemon, além de fallback dinâmico de portas (`5000` a `5005`), eliminando travamentos por `Address already in use` (`Errno 98`).
   - `start_silva.sh` implementa limpeza cirúrgica prévia de instâncias órfãs de `llama-server` e `main.py`, respeita a variável `WEB_PORT` do `.env` e gerencia PIDs via `data/llama.pid` e `data/web.pid` com `trap cleanup EXIT INT TERM` unificado.
2. **Normalização Matemática e de Linguagem Natural**:
   - `intent_fallback.py` normaliza números por extenso em português (`zero`..`mil`), operadores (`vezes`, `x`, `dividido por`, `mais`, `menos`, `ao quadrado`, `%`) e valida expressões via AST antes de chamar `calculate()`.
3. **Calibração Meteorológica e Resolução Geográfica**:
   - `tools.py` calibra códigos WMO de chuvisco/chuva leve para `Céu limpo` ou `Parcialmente nublado` quando a probabilidade for $< 35\%$ e o volume $\le 0.5\text{ mm}$, eliminando falsos positivos.
   - Geocoding Open-Meteo prioriza localidades no Brasil (`country_code == 'BR'`) com desempate por estado/UF (`UF_TO_STATE`).
   - `intent_fallback.py` aceita preposições `de/em/no/na/para/pra`, remove ruídos temporais e preserva capitalização limpa de cidades.
4. **Redesign da Interface Web**:
   - Interface 100% offline inspirada em Claude/DeepSeek, com sidebar retrátil, histórico de conversas no `localStorage`, badges de telemetria e cards rápidos.
5. **Expansão de Ferramentas**:
   - `AVAILABLE_TOOLS` e `dataset/schema.json` agora cobrem formalmente 35 ferramentas nativas (incluindo `request_ride`, `order_food`, `install_app`, `media_control`, `list_capabilities`).

### 7.2 Pontos de Atenção e Acoplamentos Restantes

1. **JSON sem escrita atômica.** `memory.json`, `last_location.json` e `dnd_backup.json` são escritos diretamente; interrupção abrupta no Android pode truncar o arquivo (`silva-agent/android_agent/tools.py`).
2. **Read-modify-write sem lock na memória.** `remember_note()` carrega o JSON completo e regrava; duas requisições simultâneas em threads separadas podem sobrescrever notas.
3. **HTTP em texto claro (Plaintext).** A comunicação na rede local Wi-Fi ocorre sobre HTTP sem TLS (`0.0.0.0:5000`), dependendo do PIN estático (`X-Access-Pin`) para autorização básica.
4. **Snapshots de release binários legados.** Arquivos como `silva_deploy.tar.gz` e `silva_update.tar.gz` na raiz do workspace representam snapshots antigos e devem ser gerados novamente se for necessária uma distribuição empacotada.
5. **Atualização isolada de arquivos.** Atualizar `tools.py` isoladamente sem regenerar o dataset de treino ou vice-versa pode gerar discrepâncias de vocabulário e chamadas aceitas.
6. **API e recursos privileged sem confirmação manual.** O PIN protege o endpoint `/api/chat`; chamadas telefônicas, SMS, câmera e volume executam imediatamente após a validação da chamada no parser.

### 7.3 Ordem recomendada para evolução futura do sistema

1. **Persistência transacional.** Implementar escrita JSON atômica (arquivo temporário + `fsync` + `rename`) e locks simples para evitar perda de dados em encerramentos abruptos no Android.
2. **Endurecimento de segurança na rede local.** Adicionar suporte opcional a HTTPS autoassinado na LAN e rate limiting básico de tentativas no endpoint de autenticação `/api/chat`.
3. **Pipeline de release e empacotamento.** Regenerar os arquivos de snapshot (`silva_deploy.tar.gz`) incorporando os novos scripts (`update_direct.sh`, `scheduler.py`), o catálogo completo de 35 ferramentas e o novo frontend minimalista.
4. **Automação de testes de regressão.** Criar uma suíte leve de testes unitários offline no repositório cobrindo o validador AST do `parser.py`, o normalizador do `intent_fallback.py` e os mocks de hardware do `tools.py`.
