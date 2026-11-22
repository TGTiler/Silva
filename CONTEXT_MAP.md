# Silva — Context Map Técnico

> Documento de referência gerado por inspeção estática do projeto. Escopo inspecionado: `2026-11-22`, checkout `silva-agent` em `e36dd44` (`main`). Convenções: `arquivo:linha` identifica a implementação; nomes de chaves, rotas e funções aparecem exatamente como no código.

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
    │   ├── tools/                           # autoral: pacote modular das 36 ferramentas Android
    │   │   ├── __init__.py                  # re-export retrocompatível e AVAILABLE_TOOLS
    │   │   ├── core.py                      # paths, locks, processos, telefones e apps
    │   │   ├── hardware.py                  # bateria, lanterna, DND, vibração, volume, brilho, scan_wifi
    │   │   ├── media.py                     # foto, screenshot, gravação de vídeo, media_control
    │   │   ├── comms.py                     # SMS, discagem, notificações, clipboard
    │   │   ├── weather_web.py               # GPS, mapa, previsão Open-Meteo e busca web
    │   │   ├── apps_mobility.py             # open_app, uber, ifood, play store, piadas, list_capabilities
    │   │   └── memory_schedule.py           # SQLite FTS5, alarmes, agenda, timer e calculadora AST
    │   ├── web_server.py                    # autoral: servidor ReusableThreadingHTTPServer com SO_REUSEADDR, fallback de porta e API REST
    │   ├── __pycache__/                     # artefato gerado: bytecode Python 3.12
    │   │   ├── config.cpython-312.pyc       # bytecode de config.py
    │   │   ├── intent_fallback.cpython-312.pyc # bytecode de intent_fallback.py
    │   │   ├── llm_client.cpython-312.pyc    # bytecode de llm_client.py
    │   │   ├── parser.cpython-312.pyc        # bytecode de parser.py
    │   │   └── web_server.cpython-312.pyc    # bytecode de web_server.py
    │   ├── captures/                        # diretório de estado gerado: fotos, vídeos, prints e mapas
    │   │   └── .gitkeep                     # placeholder versionado
    │   ├── data/                            # diretório de estado: SQLite FTS5 (memory.db), localização, PIDs, DND e lembretes
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
    │   ├── schema.json                      # autoral: contrato customizado de 36 ferramentas/41 parâmetros
    │   ├── seed_examples.jsonl              # autoral: 104 exemplos-base
    │   ├── train.jsonl                      # autoral/estado: 5.743 exemplos limpos e enriquecidos
    │   ├── train.jsonl.bak                  # autoral/backup: 4.140 exemplos anteriores ao reparo
    │   ├── train_clean.jsonl                # autoral/estado: 5.790 exemplos limpos de treino
    │   ├── eval_clean.jsonl                 # autoral/estado: 304 exemplos limpos de avaliação
    │   ├── silva_colab_dataset.jsonl        # autoral/estado: 6.094 exemplos consolidados
    │   ├── prepare_final_dataset.py          # autoral: valida, enriquece, deduplica e divide
    │   ├── repair_train_dataset.py           # autoral: corrige e enriquece o dataset de treino
    │   ├── validate_dataset.py               # autoral: validador AST/schema dos JSONL
    │   └── __pycache__/                     # artefato gerado: bytecode Python 3.12
    │       └── prepare_final_dataset.cpython-312.pyc # bytecode do preparador
    ├── pc_training/                         # pipeline de treinamento e exportação
    │   ├── colab_train_silva.py             # autoral: pipeline autônomo de SFT, merge e quantização
    │   ├── train_sft.py                     # autoral: pipeline SFT local, sem chamada à função train()
    │   ├── export_gguf.py                   # autoral: merge, conversão e quantização GGUF
    │   ├── requirements_pc.txt              # autoral: dependências do pipeline desktop
    │   └── __pycache__/                     # artefato gerado: bytecode Python 3.12
    │       └── colab_train_silva.cpython-312.pyc # bytecode potencialmente obsoleto do Colab
    └── tests/                               # autoral: suíte de testes unitários e de integração (18 testes)
        ├── __init__.py                      # marcador de pacote de testes
        ├── test_contracts.py                # validação de schemas, tools e prompts sincronizados
        ├── test_parser_and_fallback.py      # testes de AST, whitelist, fallback e multi-mídia
        ├── test_tools_and_memory.py         # testes de FTS5, migração JSON, calculadora AST e hardware
        └── test_web_server.py               # testes HTTP, autenticação PIN e proteção contra Path Traversal
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
| `silva-agent/README.md` (215 linhas) | Documentação principal com arquitetura, catálogo das 36 ferramentas e guia de execução. |
| `silva-agent/android_agent/config.py` (70 linhas) | Configuração, paths e prompt de function calling. |
| `silva-agent/android_agent/intent_fallback.py` (966 linhas) | Regras determinísticas de intents (36 tools), normalizador matemático/científico, scan Wi-Fi e sanitização de cidades. |
| `silva-agent/android_agent/llm_client.py` (119 linhas) | Cliente HTTP do `llama-server`. |
| `silva-agent/android_agent/main.py` (114 linhas) | Entry point CLI/Web com inicialização segura do daemon `scheduler`. |
| `silva-agent/android_agent/parser.py` (174 linhas) | Parser AST, whitelist de 36 ferramentas, execução e propagação de status real (`ok`, `partial_error`, `error`). |
| `silva-agent/android_agent/scheduler.py` (83 linhas) | Daemon em background thread-safe e reentrante para monitoramento de eventos e alarmes locais. |
| `silva-agent/android_agent/setup_termux.sh` (48 linhas) | Setup de dependências e build do `llama-server`. |
| `silva-agent/android_agent/start_silva.sh` (176 linhas) | Orquestração de inicialização idempotente, limpeza de processos e gestão de PIDs. |
| `silva-agent/android_agent/tools/` (3.922 linhas totais) | Pacote modular das 36 ferramentas em 8 módulos (`core`, `hardware`, `media`, `comms`, `weather_web`, `apps_mobility`, `memory_schedule`, `__init__`). |
| `silva-agent/android_agent/web_server.py` (265 linhas) | Servidor HTTP com SO_REUSEADDR, autenticação por PIN no chat e em `/captures/*`, proteção anti-path traversal e fallback de porta. |
| `silva-agent/android_agent/static/index.html` (1.803 linhas) | Frontend responsivo estilo Claude/DeepSeek com multi-mídia segura e zero emojis. |
| `silva-agent/tests/` (480 linhas totais) | Suíte de testes automatizados unitários e de integração (18 testes 100% passando). |
| `silva-agent/dataset/schema.json` (402 linhas) | Contrato estrito de 36 ferramentas e 41 parâmetros. |
| `silva-agent/dataset/prepare_final_dataset.py` (383 linhas) | Preparação e split do dataset final. |
| `silva-agent/dataset/repair_train_dataset.py` (572 linhas) | Reparo/enriquecimento do dataset de treino. |
| `silva-agent/dataset/validate_dataset.py` (185 linhas) | Validador de dataset. |
| `silva-agent/dataset/seed_examples.jsonl` (104 linhas) | Base canônica de 104 exemplos. |
| `silva-agent/dataset/train.jsonl` (5.743 linhas) | Estado local de treino enriquecido com novas ferramentas e casos de uso. |
| `silva-agent/dataset/train.jsonl.bak` (4.140 linhas) | Backup anterior ao reparo. |
| `silva-agent/dataset/train_clean.jsonl` (5.790 linhas) | Divisão limpa de treino (95% do dataset consolidado). |
| `silva-agent/dataset/eval_clean.jsonl` (304 linhas) | Divisão limpa de avaliação (5% do dataset consolidado). |
| `silva-agent/dataset/silva_colab_dataset.jsonl` (6.094 linhas) | Dataset consolidado usado no Colab (100% aderente ao schema de 36 tools). |
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

**Mecanismo real de persistência:** O sistema utiliza **SQLite 3 com motor de busca textual FTS5 (`silva-agent/android_agent/data/memory.db`)** para memória persistente de longo prazo (tabela `memories` e índice virtual `memories_fts` sincronizado por triggers, transações ACID, modo WAL e classificação automática por categoria). Para os arquivos de estado JSON (`last_location.json`, `events.json`, `dnd_backup.json`), emprega escrita atômica segura (`_atomic_write_json` via arquivo temporário + `fsync` + `replace`) protegida por lock reentrante de threads (`_FILE_LOCK = threading.RLock()`). Multimídia usa arquivos em `silva-agent/android_agent/captures/`; configuração usa `.env`; navegador usa `localStorage["silva_pin"]`; agendamento usa daemon reentrante `scheduler.py`; treinamento usa JSONL (6.094 amostras) e artefatos GGUF.

## 2. Anatomia Completa do Estado e Modelos de Dados

### 2.1 Raiz do estado do runtime

Não existe uma estrutura central única. O estado é distribuído entre:

1. memória volátil do processo: `llm_client` global, `_LAST_JOKE` e argumentos locais (`silva-agent/android_agent/web_server.py:21-22`, `silva-agent/android_agent/tools.py:1760-1768`);
2. banco de dados relacional e motor de busca: SQLite 3 com tabela virtual FTS5 em `silva-agent/android_agent/data/memory.db`;
3. arquivos JSON gravados com escrita atômica e protegidos por `_FILE_LOCK = threading.RLock()` em `silva-agent/android_agent/data/` (`events.json`, `last_location.json`, `dnd_backup.json`, `llama.pid`, `web.pid`);
4. arquivos de mídia em `android_agent/captures/`;
5. configuração carregada de `.env`/`.env.example` (`silva-agent/android_agent/config.py:26-49`);
6. PIN persistido no navegador (`silva-agent/android_agent/static/index.html`).

### 2.2 `data/memory.db` (SQLite 3 com FTS5)

Motor de memória de longo prazo transacional (ACID) com `PRAGMA journal_mode=WAL;` e inicialização idempotente via `_init_memory_db()`.

#### Schema Relacional:
```sql
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    value TEXT NOT NULL,
    category TEXT DEFAULT 'geral',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    key,
    value,
    category,
    content='memories',
    content_rowid='id'
);
```

- **Triggers de Sincronização Automática**:
  - `memories_ai`: Dispara `AFTER INSERT ON memories` mantendo o índice FTS5 sincronizado.
  - `memories_ad`: Dispara `AFTER DELETE ON memories` removendo a entrada do índice virtual.
  - `memories_au`: Dispara `AFTER UPDATE ON memories` atualizando os campos em `memories_fts`.
- **Categorização Automática**: `_classify_memory_category(key, value)` atribui semanticamente uma categoria: `wifi` (senhas/redes), `senha` (credenciais/códigos), `estudo` (aulas/matérias), `pessoal` (preferências/anotações) ou `geral`.
- **Migração Transparente e Sem Perdas**: Função `_migrate_json_to_sqlite()` detecta a existência de `data/memory.json` legado, importa todas as chaves e timestamps via `INSERT OR REPLACE` e renomeia o arquivo original para `memory.json.migrated`.
- **Busca Híbrida**: `recall_note(query)` executa ranqueamento BM25 por `memories_fts MATCH ? ORDER BY rank` e, em caso de sintaxe FTS restrita ou ausência de match, aciona fallback relacional com `LIKE ?` e correspondência de tokens com ordenação decrescente de relevância.
- **Thread-Safety**: Todas as operações de leitura e escrita são enclausuradas em `with _FILE_LOCK:`, garantindo concorrência segura entre requisições web e daemons.

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

O contrato de tools é `dataset/schema.json:1-402`, mas é customizado e não JSON Schema Draft-07 aplicável. Contém 36 ferramentas, 41 parâmetros, tipos `string|integer|boolean`; obrigatoriedade é marcada por `"required": true` dentro do parâmetro (`silva-agent/dataset/schema.json:6-401`).

| Ferramenta | Parâmetros: tipo, obrigatoriedade, default | Schema |
|---|---|---|
| `get_battery` | nenhum | `silva-agent/dataset/schema.json:7-10` |
| `get_last_sms` | `limit: integer?`, default `5` | `silva-agent/dataset/schema.json:11-20` |
| `send_sms` | `number: string`; `message: string` | `silva-agent/dataset/schema.json:21-35` |
| `take_photo` | `camera_id: integer?`, default `0` | `silva-agent/dataset/schema.json:36-45` |
| `take_screenshot` | nenhum | `silva-agent/dataset/schema.json:46-49` |
| `search_google` | `query: string`; `open_browser: boolean?`, default `false` | `silva-agent/dataset/schema.json:50-64` |
| `open_app` | `app_name: string` | `silva-agent/dataset/schema.json:65-74` |
| `make_call` | `number: string` | `silva-agent/dataset/schema.json:75-84` |
| `get_location` | nenhum | `silva-agent/dataset/schema.json:85-88` |
| `set_torch` | `state: boolean` | `silva-agent/dataset/schema.json:89-98` |
| `set_dnd` | `state: boolean` | `silva-agent/dataset/schema.json:99-108` |
| `vibrate` | `duration_ms: integer?`, default `500` | `silva-agent/dataset/schema.json:109-118` |
| `get_clipboard` | nenhum | `silva-agent/dataset/schema.json:119-122` |
| `set_clipboard` | `text: string` | `silva-agent/dataset/schema.json:123-132` |
| `tell_joke` | nenhum | `silva-agent/dataset/schema.json:133-136` |
| `set_alarm` | `time: string`; `label: string?`; `days: string?` | `silva-agent/dataset/schema.json:137-156` |
| `cancel_alarm` | `time: string?`; `day: string?`; `label: string?` | `silva-agent/dataset/schema.json:157-176` |
| `schedule_event` | `title: string`; `date: string?`; `time: string?` | `silva-agent/dataset/schema.json:177-196` |
| `remember_note` | `key: string`; `value: string` | `silva-agent/dataset/schema.json:197-211` |
| `recall_note` | `query: string` | `silva-agent/dataset/schema.json:212-221` |
| `get_notifications` | `app: string?` | `silva-agent/dataset/schema.json:222-231` |
| `set_volume` | `stream: string?`, default `"media"`; `level: integer` | `silva-agent/dataset/schema.json:232-247` |
| `set_brightness` | `level: integer` | `silva-agent/dataset/schema.json:248-257` |
| `set_timer` | `minutes: integer`; `label: string?` | `silva-agent/dataset/schema.json:258-272` |
| `calculate` | `expression: string` | `silva-agent/dataset/schema.json:273-282` |
| `set_location_state` | `state: boolean` | `silva-agent/dataset/schema.json:283-292` |
| `get_last_location` | nenhum | `silva-agent/dataset/schema.json:293-296` |
| `get_weather` | `day: string?`, default `"hoje"`; `time: string?`, default `""`; `location: string?`, default `""` | `silva-agent/dataset/schema.json:297-319` |
| `record_video` | `duration: integer?`, default `10`; `camera_id: integer?`, default `0` | `silva-agent/dataset/schema.json:320-336` |
| `request_ride` | `destination: string`; `app: string?`, default `"uber"` | `silva-agent/dataset/schema.json:337-353` |
| `order_food` | `query: string`; `app: string?`, default `"ifood"` | `silva-agent/dataset/schema.json:354-370` |
| `install_app` | `app_name: string` | `silva-agent/dataset/schema.json:371-380` |
| `media_control` | `action: string` (`play/pause/next/previous`) | `silva-agent/dataset/schema.json:381-390` |
| `list_capabilities` | nenhum | `silva-agent/dataset/schema.json:391-394` |
| `scan_wifi` | nenhum | `silva-agent/dataset/schema.json:395-398` |
| `none` | nenhum | `silva-agent/dataset/schema.json:399-402` |

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

- `print_banner()` → `None`: imprime URL do LLM, status do scheduler e estado de simulação (`silva-agent/android_agent/main.py:17-34`).
- `run_cli_mode()` → `None`: inicializa `scheduler.start_scheduler()`, loop `input()`, aceita calls diretas, consulta o cliente LLM e executa (`silva-agent/android_agent/main.py:37-82`).
- `run_web_mode(host: str, port: int)` → `None`: inicializa `scheduler.start_scheduler()`, banner, PIN em claro e `start_server()` (`silva-agent/android_agent/main.py:85-94`).
- `main()` → `None`: parse de `--web`, `--cli`, `--host`, `--port`; web é o default (`silva-agent/android_agent/main.py:96-114`).

### 3.3 `silva-agent/android_agent/web_server.py`

- `ReusableThreadingHTTPServer(ThreadingHTTPServer)`: subclasse com `allow_reuse_address = True` (`SO_REUSEADDR`) e `daemon_threads = True` para liberação imediata da porta e encerramento limpo (`silva-agent/android_agent/web_server.py:24-30`).
- `SilvaHTTPRequestHandler._send_json(data: dict, status: int = HTTPStatus.OK)` → `None`: JSON UTF-8 e CORS `*` (`silva-agent/android_agent/web_server.py:33-41`).
- `SilvaHTTPRequestHandler._send_file(file_path: Path, mime_type: str)` → `None`: envia arquivo ou 404 (`silva-agent/android_agent/web_server.py:43-53`).
- `SilvaHTTPRequestHandler.do_OPTIONS()` → `None`: preflight 204 (`silva-agent/android_agent/web_server.py:55-61`).
- `SilvaHTTPRequestHandler.do_GET()` → `None`: roteia `/`, `/index.html`, `/captures/*`, `/api/health` (`silva-agent/android_agent/web_server.py:63-102`).
- `SilvaHTTPRequestHandler.do_POST()` → `None`: valida PIN/body, gera call, executa e propaga status real (`ok`, `partial_error`, `error`) (`silva-agent/android_agent/web_server.py:104-165`).
- `start_server(host: str = WEB_HOST, port: int = WEB_PORT)` → `None`: instancia `ReusableThreadingHTTPServer`, com fallback dinâmico de portas (`port` até `port + 5`) em caso de `errno.EADDRINUSE`, registra handlers de `SIGINT`/`SIGTERM` e chama `shutdown()`/`server_close()` no encerramento (`silva-agent/android_agent/web_server.py:168-235`).

### 3.4 `silva-agent/android_agent/llm_client.py`

- `SilvaLLMClient.__init__(base_url: str = LLAMA_SERVER_URL, timeout: int = LLM_TIMEOUT_SECONDS)` → `None`: normaliza URL (`silva-agent/android_agent/llm_client.py:18-20`).
- `SilvaLLMClient.check_health()` → `dict`: tenta `/health`, depois `/`; retorna `online/status/url/error` (`silva-agent/android_agent/llm_client.py:22-37`).
- `SilvaLLMClient.generate_call(user_prompt: str)` → `Tuple[Optional[str], float, Optional[str]]`: fallback local, prompt ChatML, `POST /completion`, normalização da tag e validação superficial de tool (`silva-agent/android_agent/llm_client.py:39-119`).

### 3.5 `silva-agent/android_agent/intent_fallback.py` e Pacote `android_agent/nlp/`

Arquitetura modular de NLP e intent fallback determinístico dividida em 4 pilares:

- **Pilar A: Parser Numérico Composto (`android_agent/nlp/numbers.py`)**:
  - `parse_ptbr_numbers(text: str)` → `str`: Converte números compostos por extenso (`"vinte e cinco"` → `"25"`, `"dois mil e quinhentos"` → `"2500"`, `"cento e vinte e cinco"` → `"125"`).
  - Tratamento contextual prioritário de horários: `"meia-noite"` → `"00:00"`, `"meio-dia"` → `"12:00"`, `"meia hora"` → `"30 minutos"`, `"uma hora e meia"` → `"01:30"` (em contexto de alarme) ou `"90 minutos"` (timer).
  - Desambiguação de dígitos ditados sequencialmente (`"nove nove oito meia cinco"` → `"9 9 8 6 5"`).
  - Proteção estrita de artigos indefinidos (`"um"`/`"uma"` não viram número antes de substantivos de ação como `"um uber"`, `"uma foto"`, `"um alarme"`).
- **Pilar B: Normalizador de Gírias, Níveis e Typos (`android_agent/nlp/colloquial.py`)**:
  - `normalize_colloquial_ptbr(text: str)` → `str`: Traduz expressões de nível em volume/brilho (`"no talo"`, `"no máximo"` → `"100%"`; `"no mínimo"`, `"no mudo"`, `"zerado"` → `"0%"`; `"na metade"` → `"50%"`).
  - Normaliza gírias de apps: `"zap"`, `"zapzap"`, `"wpp"`, `"whats"` → `"whatsapp"`; `"insta"` → `"instagram"`; `"yt"` → `"youtube"`; `"spot"` → `"spotify"`; `"playstore"` → `"play store"`.
  - Tolerância a erros de digitação (typos) com `difflib.get_close_matches(cutoff=0.82)` sobre vocabulário canônico (`"baterria"` → `"bateria"`, `"lanterana"` → `"lanterna"`, `"calcura"` → `"calcula"`).
- **Pilar C: Roteador por Pontuação de Intenção (`android_agent/nlp/router.py`)**:
  - `ScoredIntentRouter`: Registra extratores por domínio que retornam `(score: float, call_str: str)`.
  - Resolução explícita de ambiguidades por peso:
    - Wi-Fi com senha → `recall_note` (score 0.95);
    - Wi-Fi com abrir/configurações → `open_app` (score 0.90);
    - Wi-Fi com escanear/listar/redes/perto → `scan_wifi` (score 0.95).
  - Bloqueio de perguntas conceituais/enciclopédicas sem verbo de comando para permitir resposta semântica pelo LLM.
  - Cobertura completa de todas as 36 ferramentas do catálogo.
  - Formatação 100% segura de chamadas com `_format_call(func_name, **kwargs)` usando `repr()`.
- **Pilar D: Splitter Inteligente de Cláusulas Compostas (`intent_fallback.py`)**:
  - `match_intent_fallback(user_prompt: str)` → `Optional[str]`: Protege nomes próprios compostos (`Abreu e Lima`), roda o parser numérico composto **antes** da divisão por `" e "`, normaliza gírias/typos e divide apenas quando o trecho seguinte inicia com verbo de comando (`COMMAND_VERBS`). Concatena `<call>...</call><call>...</call>` para comandos múltiplos.
  - `parse_single_intent(raw_cmd: str)` → `Optional[str]`: Roteia comandos unitários via `_ROUTER.route()`.
  - `normalize_text(text: str)` → `str`: Remove diacríticos, pontuação e converte para minúsculas.

### 3.6 `silva-agent/android_agent/parser.py`

- `parse_function_calls(model_output: str)` → `List[Tuple[str, Dict[str, Any]]]`: extrai tags, aplica whitelist de 36 ferramentas, AST literal, binding de assinatura, defaults e validação estrita de tipos (`silva-agent/android_agent/parser.py:19-90`).
- `parse_function_call(model_output: str)` → `Dict[str, Any]`: compatibilidade de call única; sempre retorna `is_valid=True` porque a entrada é normalizada para `none()` (`silva-agent/android_agent/parser.py:93-104`).
- `execute_call(model_output: str)` → `Dict[str, Any]`: executa calls em sequência, agrega mensagens/dados e retorna status real consolidado (`"ok"`, `"partial_error"` ou `"error"`) (`silva-agent/android_agent/parser.py:107-174`).

### 3.7 `silva-agent/android_agent/tools/` (Pacote Modular)

O antigo monolito `tools.py` (3.621 linhas) foi decomposto em um pacote modular desacoplado sob `silva-agent/android_agent/tools/`:

- **`core.py` (344 linhas):** Paths (`DATA_DIR`, `CAPTURES_DIR`), lock reentrante (`_FILE_LOCK = threading.RLock()`), escrita atômica segura (`_atomic_write_json`), serialização de eventos (`_load_events`, `_save_events`), execução segura de comandos de terminal e intents (`_run_termux_cmd`, `_exec_android_intent`), sanitização e resolução de contatos (`sanitize_phone_number`, `resolve_contact_or_number`) e mapas de aplicativos Android (`APP_PACKAGES`, `RESOLVED_APP_ACTIVITIES`).
- **`hardware.py` (447 linhas):** Bateria (`get_battery`), lanterna (`set_torch`), Não Perturbe (`set_dnd`), vibração (`vibrate`), volume (`set_volume`), brilho de tela (`set_brightness`) e varredura de redes Wi-Fi (`scan_wifi`).
- **`media.py` (321 linhas):** Captura de fotos (`take_photo`), gravação de vídeo (`record_video`), print de tela com validação de cabeçalho PNG (`take_screenshot`, `_is_valid_png`) e controle de sessão de mídia (`media_control`).
- **`comms.py` (282 linhas):** Leitura e envio de SMS (`get_last_sms`, `send_sms`), discagem nativa (`make_call`), notificações ativas do sistema (`get_notifications`) e leitura/escrita na área de transferência (`get_clipboard`, `set_clipboard`).
- **`weather_web.py` (939 linhas):** Localização geográfica e mapa OSM (`get_location`, `set_location_state`, `get_last_location`, `_generate_map_preview`), previsão do tempo Open-Meteo com filtro anti-chuvisco falso (`get_weather`) e busca web multi-fonte resiliente (`search_google`, `DuckDuckGoHTMLParser`, `_fetch_wikipedia_summary`).
- **`apps_mobility.py` (557 linhas):** Abertura de aplicativos (`open_app`), mobilidade urbana com rotas no Uber/99 (`request_ride`), delivery no iFood/99Food (`order_food`), instalação na Play Store (`install_app`), piadas sem repetição imediata (`tell_joke`), capacidades do agente (`list_capabilities`) e chamada nula neutra (`none`).
- **`memory_schedule.py` (828 linhas):** Memória persistente transacional SQLite 3 FTS5 (`_get_memory_db`, `_init_memory_db`, `_migrate_json_to_sqlite`, `remember_note`, `recall_note`), interpretação de datas e horas em português (`parse_ptbr_date`, `parse_time_str`), alarmes e eventos (`set_alarm`, `cancel_alarm`, `schedule_event`, `set_timer`) e avaliador matemático científico via AST (`SafeMathEvaluator`, `calculate`).
- **`__init__.py` (204 linhas):** Re-exporta todas as funções públicas, helpers internos e o catálogo canônico `AVAILABLE_TOOLS` (36 ferramentas nativas), mantendo 100% de compatibilidade retroativa para todos os clientes e módulos.

#### Catálogo integral das 36 ferramentas

| Função → retorno | Efeito principal | Submódulo |
|---|---|---|
| `get_battery()` → `dict` | Estado e carga da bateria | `hardware.py` |
| `get_last_sms(limit=5)` → `dict` | Lê SMS recentes | `comms.py` |
| `send_sms(number, message)` → `dict` | Envia SMS | `comms.py` |
| `take_photo(camera_id=0)` → `dict` | Captura JPEG | `media.py` |
| `take_screenshot()` → `dict` | Captura tela | `media.py` |
| `record_video(duration=10, camera_id=0)` → `dict` | Intent de gravação e cópia do arquivo | `media.py` |
| `open_app(app_name)` → `dict` | Abre activity Android | `apps_mobility.py` |
| `make_call(number)` → `dict` | Disca | `comms.py` |
| `get_location()` → `dict` | GPS e persiste `last_location.json` | `weather_web.py` |
| `set_location_state(state)` → `dict` | Liga/desliga GPS ou abre settings | `weather_web.py` |
| `get_last_location()` → `dict` | Lê último JSON atômico e formata data | `weather_web.py` |
| `get_weather(day="hoje", time="", location="")` → `dict` | Open-Meteo com filtro de chuva e geocoding BR | `weather_web.py` |
| `set_torch(state)` → `dict` | Liga/desliga lanterna | `hardware.py` |
| `set_dnd(state)` → `dict` | DND nativo ou fallback por volume | `hardware.py` |
| `vibrate(duration_ms=500)` → `dict` | Vibração | `hardware.py` |
| `get_clipboard()` → `dict` | Lê clipboard | `comms.py` |
| `set_clipboard(text)` → `dict` | Escreve clipboard | `comms.py` |
| `tell_joke()` → `dict` | Piada aleatória sem repetição consecutiva | `apps_mobility.py` |
| `parse_ptbr_date(date_str)` → `date` | Interpreta datas PT-BR | `memory_schedule.py` |
| `parse_time_str(time_str)` → `tuple[int,int]` | Interpreta hora | `memory_schedule.py` |
| `set_alarm(time, label="", days="")` → `dict` | Intent `SET_ALARM` | `memory_schedule.py` |
| `cancel_alarm(time="", day="", label="")` → `dict` | Intent `DISMISS_ALARM` | `memory_schedule.py` |
| `schedule_event(title, date="", time="")` → `dict` | Agenda compromisso local com alarme e gravação atômica | `memory_schedule.py` |
| `remember_note(key, value)` → `dict` | Salva nota com categorização em SQLite FTS5 | `memory_schedule.py` |
| `recall_note(query)` → `dict` | Busca híbrida FTS5 (BM25 + LIKE fallback) | `memory_schedule.py` |
| `get_notifications(app="")` → `dict` | Lê notificações do sistema | `comms.py` |
| `set_volume(stream="media", level=50)` → `dict` | Ajusta volume | `hardware.py` |
| `set_brightness(level)` → `dict` | Ajusta brilho | `hardware.py` |
| `set_timer(minutes, label="")` → `dict` | Intent `SET_TIMER` | `memory_schedule.py` |
| `calculate(expression)` → `dict` | Avaliador matemático científico seguro via AST | `memory_schedule.py` |
| `search_google(query, open_browser=False)` → `dict` | Busca web multi-fonte (Wikipédia, DDG Instant Answer, DDG HTML Lite) | `weather_web.py` |
| `scan_wifi()` → `dict` | Escaneia redes Wi-Fi próximas, intensidade (dBm/%), banda e segurança | `hardware.py` |
| `request_ride(destination, app="uber")` → `dict` | Intent para Uber ou 99 com destino configurado | `apps_mobility.py` |
| `order_food(query, app="ifood")` → `dict` | Intent para iFood ou 99Food buscando o prato | `apps_mobility.py` |
| `install_app(app_name)` → `dict` | Abre Google Play Store na página do app | `apps_mobility.py` |
| `media_control(action)` → `dict` | Controle de mídia via `cmd media_session` e KeyEvents | `media.py` |
| `list_capabilities()` → `dict` | Catálogo completo das 36 ferramentas com exemplos | `apps_mobility.py` |
| `none()` → `dict` | Resposta neutra | `apps_mobility.py` |

`AVAILABLE_TOOLS` registra exatamente essas 36 funções, sem wrappers ou aliases (`android_agent/tools/__init__.py`).

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

Pipeline autônomo completo para Google Colab (GPU T4):

1. **Instalação e Compilação:** Remove `torchao` conflitante, instala stack Hugging Face (`transformers`, `peft`, `trl`, `accelerate`, `gguf`) e compila `llama-quantize` no `llama.cpp` (`silva-agent/pc_training/colab_train_silva.py:9-52`).
2. **Carregamento e Split Determinístico:** Carrega arquivos separados (`train_clean.jsonl` e `eval_clean.jsonl`) ou dataset consolidado (`silva_colab_dataset.jsonl`) com split determinístico `seed=42` em 95% treino (~5.790) e 5% avaliação (~304) (`silva-agent/pc_training/colab_train_silva.py:54-150`).
3. **Auditoria de Tokens e SFT/LoRA com Mascaramento Manual de Labels:**
   - Separação estrita de `eos_token_id` (`<|im_end|>`) e `pad_token_id` (`<|endoftext|>`), impedindo que o collator mascare o token de parada.
   - Auditoria pré-treino com média, P99 e detecção de truncamento na janela `max_length=1024` via ChatML template.
   - Tokenização manual via `tokenize_chatml_example(item)` em duas partes: Prompt mascarado com `labels = -100` e Resposta treinável com token de parada explícito `<|im_end|>`. Se a sequência total exceder a janela, o início do prompt é podado, garantindo 100% de integridade da completion e do token de encerramento.
   - `DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True, label_pad_token_id=-100)` com `Trainer`.
   - Auditoria visual obrigatória pré-treino com assertions rigorosas garantindo início com `<call>`, término com `<|im_end|>` e ausência de vazamento do prompt nas labels ativas.
   - Otimização de VRAM para GPU T4: `per_device_train_batch_size=4`, `gradient_accumulation_steps=8` (mantendo batch efetivo de 32), `gradient_checkpointing=True` com `base_model.config.use_cache=False`, `PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"` e limpeza preventiva de memória via `torch.cuda.empty_cache()` e `gc.collect()`.
   - Treinamento calibrado por 4 épocas (`learning_rate=3e-4`, cosine scheduler, `load_best_model_at_end=True`, `metric_for_best_model="eval_loss"`), auditoria do melhor checkpoint e fusão `merge_and_unload()` (`silva-agent/pc_training/colab_train_silva.py:152-450`).
4. **Bateria de Inferência Pós-Merge:** Validação via `apply_chat_template(..., add_generation_prompt=True)` com `eos_token_id=eos_id`, `pad_token_id=tokenizer.pad_token_id`, `temperature=0.0` / `do_sample=False` e corte limpo no primeiro `<|im_end|>` ou `</call>` em 10 cenários essenciais (`silva-agent/pc_training/colab_train_silva.py:452-510`).
5. **Conversão e Quantização GGUF:** Conversão para FP16, quantização `Q5_K_M` (~105MB) e download automático no navegador (`silva-agent/pc_training/colab_train_silva.py:512-545`).

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
(silva-agent/android_agent/tools/comms.py)

video duration = max(3, min(int(duration), 120))
camera_id = 1 if int(camera_id) == 1 else 0
(silva-agent/android_agent/tools/media.py)

vibration duration = max(50, min(int(duration_ms), 5000))
(silva-agent/android_agent/tools/hardware.py)

brightness percent = max(0, min(int(level), 100))
brightness_255 = round((brightness_percent / 100.0) * 255)
(silva-agent/android_agent/tools/hardware.py)

volume percent = max(0, min(int(level), 100))
volume = round((volume_percent / 100.0) * max_volume)
(silva-agent/android_agent/tools/hardware.py)

timer minutes = max(1, int(minutes))
timer seconds = minutes * 60
(silva-agent/android_agent/tools/memory_schedule.py)

event begin_ms = int(dt_event.timestamp() * 1000)
event end_ms = begin_ms + (3600 * 1000)
(silva-agent/android_agent/tools/memory_schedule.py)
```

### 4.2 Projeção Web Mercator do mapa

```text
n = 1 << zoom                         # zoom = 16
x_exact = (lon + 180.0) / 360.0 * n
x_tile = int(x_exact)
lat_rad = math.radians(lat)
y_exact = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
y_tile = int(y_exact)
(silva-agent/android_agent/tools/weather_web.py)
```

### 4.3 Busca e ranqueamento da memória (SQLite FTS5)

```text
1. Consulta primária com BM25 FTS5:
   SELECT key, value, category FROM memories_fts 
   WHERE memories_fts MATCH ? 
   ORDER BY rank LIMIT 3;
(silva-agent/android_agent/tools/memory_schedule.py)

2. Fallback relacional (LIKE + Token scoring):
   Disparado se query contiver sintaxe FTS restrita ou retornar vazia:
   SELECT key, value, category FROM memories 
   WHERE key LIKE ? OR value LIKE ?;
   Scoring:
     exact_match => score += 10
     query_in_key => score += 6
     key_in_query => score += 5
     token_intersection => score += 2 * len(query_tokens & key_tokens)
     query_in_value => score += 3
   Ordenação decrescente por score; seleciona as 3 primeiras notas.
(silva-agent/android_agent/tools/memory_schedule.py)
```

### 4.4 Resolução de data e hora

- `hoje`: data corrente; `amanhã`: `+1 dia`; `depois de amanhã`: `+2 dias` (`silva-agent/android_agent/tools/memory_schedule.py`).
- Weekday: `(target_weekday - today_weekday) % 7`; se o alvo é o dia atual, avança 7 (`silva-agent/android_agent/tools/memory_schedule.py`).
- Data por extenso com ano de dois dígitos: `year + 2000`; data passada sem ano explícito passa ao ano seguinte (`silva-agent/android_agent/tools/memory_schedule.py`).
- Data inválida/não reconhecida retorna hoje; hora inválida retorna `(9, 0)` (`silva-agent/android_agent/tools/memory_schedule.py`).

### 4.5 Clima

```text
amanhã: today + 1 day
depois de amanhã: today + 2 days
weekday: (target - today.weekday()) % 7; current weekday => +7
night => 20h; tarde => 15h; manhã => 9h; madrugada => 3h
(silva-agent/android_agent/tools/weather_web.py)
```

Sem cidade e sem última localização, usa `-7.9408, -34.8730, "Paulista"` (`silva-agent/android_agent/tools/weather_web.py`).
Filtro de chuva calibra falsos positivos quando probabilidade $< 35\%$ e volume $\le 0.5\text{ mm}$ (`silva-agent/android_agent/tools.py:1120-1145`).

### 4.6 Avaliador matemático e científico (`SafeMathEvaluator`)

Permite:
- Operações aritméticas: `+`, `-`, `*`, `/`, `//`, `%`, `**`, unário `+`/`-`.
- Funções matemáticas seguras: `sqrt`, `cbrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `log`, `log10`, `log2`, `exp`, `factorial`, `abs`, `round`, `floor`, `ceil`.
- Constantes: `pi`, `e`.
- Regras de segurança estritas:
  - Rejeita valores booleanos (`isinstance(node.value, bool)` gera erro para impedir casts indevidos).
  - Expoente máximo protegido: rejeita quando `abs(right) > 1000`.
  - Divisão ou módulo por zero rejeitados com mensagem amigável.
  - Formatação fracionária limpa: `f"{result:.6f}".rstrip("0").rstrip(".")` (`silva-agent/android_agent/tools.py:2770-2810`).

### 4.7 Dataset

```text
total_consolidado = 6094 exemplos (silva_colab_dataset.jsonl)
eval_count = max(1, int(total_consolidado * 0.05)) # 304 amostras (eval_clean.jsonl)
train_count = total_consolidado - eval_count       # 5790 amostras (train_clean.jsonl)
Aderência ao schema: 100% nas 36 ferramentas e 41 parâmetros formais.
(silva-agent/dataset/prepare_final_dataset.py:327-340)
```

Parâmetros SFT/LoRA no Colab: `r=16`, `lora_alpha=32`, `lora_dropout=0.05`, módulos `q,k,v,o,gate,up,down`, `epochs=3`, `batch_size=16`, `gradient_accumulation_steps=2`, `learning_rate=3e-4`, `weight_decay=0.01`, `warmup_steps=20`, `max_length=256` (`silva-agent/pc_training/colab_train_silva.py:165-203`).

### 4.8 Fluxo de boot

1. `start_silva.sh` entra no diretório do runtime e solicita wake lock (`silva-agent/android_agent/start_silva.sh:6-9`).
2. Localiza `llama-server` e GGUF (`silva-agent/android_agent/start_silva.sh:15-32`).
3. Instala trap de cleanup unificada (`silva-agent/android_agent/start_silva.sh:35-45`).
4. Inicia `llama-server` em `127.0.0.1:8080`, contexto 2048 e 4 threads (`silva-agent/android_agent/start_silva.sh:47-56`).
5. Executa `python3 main.py --web --port 5000` (`silva-agent/android_agent/start_silva.sh:83`).

### 4.9 Fluxo HTTP de chat

1. `do_POST` valida `X-Access-Pin` contra `ACCESS_PIN` (`silva-agent/android_agent/web_server.py:93-101`).
2. Lê `Content-Length`, body e JSON (`silva-agent/android_agent/web_server.py:103-112`).
3. Exige `body["message"]` não vazio (`silva-agent/android_agent/web_server.py:114-119`).
4. Call direta `<call>...</call>` é executada; demais mensagens vão a `generate_call()` (`silva-agent/android_agent/web_server.py:121-128`).
5. `generate_call()` tenta fallback determinístico antes do LLM (`silva-agent/android_agent/llm_client.py:44-51`).
6. Sem fallback, envia ChatML ao `POST /completion` (`silva-agent/android_agent/llm_client.py:53-81`).
7. O parser extrai, valida e executa sequencialmente (`silva-agent/android_agent/parser.py:19-174`).
8. A resposta HTTP agrega `latency_ms` e propaga o status real consolidado (`silva-agent/android_agent/web_server.py:141-145`).

### 4.10 Fluxo de dataset e treinamento

1. Amostras canônicas e enriquecidas são processadas por `repair_train_dataset.py` e validadas por `validate_dataset.py`.
2. `prepare_final_dataset.py` consolida, deduplica e valida todas as amostras contra `schema.json` (36 ferramentas).
3. O conjunto de 6.094 amostras é dividido em 5.790 treino e 304 avaliação (`silva-agent/dataset/silva_colab_dataset.jsonl`).
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
| `POST /api/chat` | body `{"message": string}`; header `X-Access-Pin` se `ACCESS_PIN` configurado | 403 `{"status":"error","message":"PIN de acesso inválido ou ausente."}`; 400 para JSON inválido ou mensagem vazia; 200 com o retorno de `execute_call()` propagando status real (`ok`, `partial_error`, `error`) (`silva-agent/android_agent/web_server.py:93-145`). |
| `OPTIONS *` | headers de preflight | 204; CORS `*`, métodos `GET, POST, OPTIONS`, headers `Content-Type, X-Access-Pin` (`silva-agent/android_agent/web_server.py:50-56`). |
| `GET /api/health` (llama-server) | nenhum | Health local do modelo; fallback para `GET /` (`silva-agent/android_agent/llm_client.py:22-37`). |
| `POST /completion` (llama-server) | `prompt`, `temperature=0.0`, `n_predict=48`, `stop`, `stream=false`, `cache_prompt=true` | Retorna `content`; latência medida (`silva-agent/android_agent/llm_client.py:53-109`). |

Formato de resposta do parser, base do `/api/chat`:

```json
{
  "status": "ok | partial_error | error",
  "message": "string",
  "raw_call": "string",
  "func_name": "string | multi_call",
  "calls": [{"func_name": "string", "args": {}, "status": "ok | error", "data": null}],
  "data": [],
  "image_url": null,
  "video_url": null,
  "latency_ms": 0.0
}
```

Referências: `silva-agent/android_agent/parser.py:157-173`, `silva-agent/android_agent/web_server.py:141-145`.

### 5.2 Comandos CLI

| Comando | Parâmetros | Ação |
|---|---|---|
| `python3 main.py --web` | `--host`, `--port` opcionais | Inicia servidor web com daemon scheduler; `--web` é default (`silva-agent/android_agent/main.py:85-114`). |
| `python3 main.py --cli` | entrada stdin | Entra no loop de perguntas com daemon scheduler ativo (`silva-agent/android_agent/main.py:37-82`). |
| `sair`, `exit`, `quit` no CLI | nenhum | Encerra CLI (`silva-agent/android_agent/main.py:56-58`). |
| `<call>get_battery()</call>` no CLI/Web | tag completa | Execução direta, processada pelo parser (`silva-agent/android_agent/main.py:60-63`, `silva-agent/android_agent/web_server.py:121-125`). |

### 5.3 Handlers/ferramentas

Todas as 36 funções de `AVAILABLE_TOOLS` são comandos de function calling (`silva-agent/android_agent/tools.py:3580-3621`). Assinaturas, defaults, efeitos e referências estão em §3.7.

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
   - `intent_fallback.py` normaliza números por extenso em português (`zero`..`mil`), operadores (`vezes`, `x`, `dividido por`, `mais`, `menos`), raízes, trigonometria e valida expressões via AST antes de chamar `calculate()`.
3. **Calibração Meteorológica e Resolução Geográfica**:
   - Pacote `tools/` calibra códigos WMO de chuvisco/chuva leve para `Céu limpo` ou `Parcialmente nublado` quando a probabilidade for $< 35\%$ e o volume $\le 0.5\text{ mm}$, eliminando falsos positivos.
   - Geocoding Open-Meteo prioriza localidades no Brasil (`country_code == 'BR'`) com desempate por estado/UF (`UF_TO_STATE`).
   - `intent_fallback.py` aceita preposições `de/em/no/na/para/pra`, remove ruídos temporais, protege nomes compostos (`Abreu e Lima`) e preserva capitalização limpa de cidades.
4. **Redesign da Interface Web**:
   - Interface 100% offline inspirada em Claude/DeepSeek, com sidebar retrátil, histórico de conversas no `localStorage`, badges de telemetria e cards rápidos.
5. **36 Ferramentas Nativas e Nova Ferramenta `scan_wifi()`**:
   - `AVAILABLE_TOOLS` e `dataset/schema.json` cobrem formalmente 36 ferramentas nativas (41 parâmetros).
   - `scan_wifi()` escaneia redes Wi-Fi próximas, calcula percentual de intensidade via RSSI, identifica frequência (2.4 GHz vs 5 GHz), criptografia (WPA3, WPA2, Aberta) e a rede atualmente conectada, com tratamento seguro de dicionários de erro (`API_ERROR` quando o GPS/Localização do Android estiver desligado).
6. **Busca Web Multi-Fonte em Cascata**:
   - `search_google()` opera com cascata tripla: 1ª Wikipédia PT-BR REST API; 2ª DuckDuckGo Instant Answer API; 3ª DuckDuckGo HTML Lite via parser nativo `DuckDuckGoHTMLParser(HTMLParser)` sem dependências externas, com parâmetro `open_browser=False`.
7. **Calculadora Científica Robusta via AST**:
   - `SafeMathEvaluator` com operações aritméticas, potência segura ($\le 1000$), funções científicas (`math.sqrt`, `cbrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `log`, `log10`, `log2`, `exp`, `factorial`, `abs`, `round`, `floor`, `ceil`), constantes `pi` e `e`, e bloqueio de booleanos.
8. **Memória Persistente SQLite FTS5 ACID e Escrita Atômica**:
   - Memória de longo prazo transacional em `data/memory.db` com busca textual FTS5 (BM25 + fallback LIKE), triggers automáticos de sincronização, modo WAL e migração sem perdas de `memory.json`.
   - Estados JSON (`events.json`, `last_location.json`, `dnd_backup.json`) gravados de forma atômica (`_atomic_write_json`) com lock reentrante de concorrência (`_FILE_LOCK = threading.RLock()`).
9. **Daemon Scheduler Ativo no Boot e Dataset Consolidado**:
   - `scheduler.py` thread-safe e reentrante disparado no boot do `main.py` para alertas e notificações em segundo plano.
   - Dataset consolidado de 6.094 amostras limpas (`silva_colab_dataset.jsonl`), dividido em 5.790 treino e 304 avaliação, com 100% de conformidade com o schema.
10. **Refatoração Modular do Pacote `android_agent/tools/`**:
    - O monolito `tools.py` (3.621 linhas) foi decomposto em um pacote coeso com 8 submódulos (`core`, `hardware`, `media`, `comms`, `weather_web`, `apps_mobility`, `memory_schedule`, `__init__`), preservando 100% de compatibilidade retroativa para imports diretos (`from android_agent.tools import ...` e `from tools import ...`) e zero dependências externas.
    - Scripts de sincronização (`update_direct.sh`, `apply_tools_update.sh`) atualizados para deploy do pacote modular.
11. **Blindagem de Mídia com PIN, Path Traversal e Suporte a Múltiplas Mídias**:
    - O endpoint `GET /captures/<filename>` foi protegido com validação de `ACCESS_PIN` via query param (`?pin=...`) ou header (`X-Access-Pin`) usando `hmac.compare_digest`.
    - Sanitização contra Directory Traversal com `target_path.resolve().is_relative_to(CAPTURES_DIR.resolve())` retornando HTTP 403 Forbidden para tentativas de escape.
    - O parser passou a retornar lista acumulada `"media_items": [{"type": "image"|"video", "url": ...}]` mantendo retrocompatibilidade com `image_url` e `video_url`.
    - Frontend web atualizado com helper `withPin(url)` e renderização de múltiplas mídias via DOM API sem `innerHTML` e sem emojis.
12. **Refatoração Segura do Pipeline de Treinamento no Colab (`colab_train_silva.py`)**:
    - Janela de contexto ampliada para `max_length=512` em `SFTConfig` e `TrainingArguments`.
    - Sincronização estrita (caractere por caractere) do `SILVA_SYSTEM_PROMPT` com `android_agent/config.py` (36 ferramentas).
    - Split determinístico automático com `random.seed(42)` em 95% treino (~5.790) e 5% avaliação (~304) para arquivos consolidados (`silva_colab_dataset.jsonl`) ou carregamento direto de `train_clean.jsonl` e `eval_clean.jsonl`.
    - Auditoria estatística pré-treino de tokens (média, P99 e detecção de truncamento com alerta explícito).
    - Hiperparâmetros calibrados para 4 épocas: LoRA com `r=16`, `alpha=32`, `dropout=0.08` em todos os módulos lineares; taxa de aprendizado suave `2.5e-4` com `cosine`, `weight_decay=0.01`, `eval_strategy="epoch"` e salvamento a cada época (`save_total_limit=2`).
    - Blindagem anti-overfitting via `load_best_model_at_end=True` monitorando `metric_for_best_model="eval_loss"`, com log explícito de auditoria do checkpoint selecionado para fusão GGUF.
    - Bateria de inferência pós-merge atualizada com 10 cenários essenciais (`temperature=0.0` / `do_sample=False`) cobrindo ferramentas de hardware, mobilidade, delivery, mídia, apps, clima, cálculo e conversa neutra (`none()`).
13. **Suíte Completa de Testes Automatizados (`silva-agent/tests/`)**:
    - Suíte com testes automatizados em Python stdlib (`unittest`), cobrindo conformidade de schemas e dataset (`test_contracts.py`), validação de AST, fallback e clima (`test_parser_and_fallback.py`), persistência SQLite FTS5, mocks de hardware e calculadora (`test_tools_and_memory.py`), e servidor HTTP com autenticação PIN e proteção contra traversal (`test_web_server.py`).
14. **Reestruturação do Motor de Linguagem Natural com 4 Pilares (`android_agent/nlp/`)**:
    - Decomposição modular do monolito `intent_fallback.py` em submódulos especializados (`numbers.py`, `colloquial.py`, `router.py`, `__init__.py`).
    - *Pilar A (Parser Numérico Composto)*: `parse_ptbr_numbers()` traduz números compostos por extenso (`vinte e cinco` → `25`, `dois mil e quinhentos` → `2500`), trata horários contextuais (`meia-noite` → `00:00`, `meia hora` → `30 minutos`), dígitos sequenciais e protege artigos indefinidos (`um`/`uma`).
    - *Pilar B (Normalizador de Gírias e Typos)*: `normalize_colloquial_ptbr()` converte expressões de nível (`no talo` → `100%`, `no mudo` → `0%`), gírias de apps (`zap` → `whatsapp`, `insta` → `instagram`) e corrige erros de digitação via `difflib.get_close_matches(cutoff=0.82)`.
    - *Pilar C (Roteador por Pontuação)*: `ScoredIntentRouter` com extratores por domínio ponderados, resolução explícita de ambiguidades (Wi-Fi senha vs scan vs abrir) e bloqueio de perguntas conceituais.
    - *Pilar D (Splitter Inteligente)*: Divisão de cláusulas encadeadas após a normalização numérica, evitando divisões errôneas de números no conector `" e "`. Suíte expandida para 22 testes com 100% de aprovação.
15. **Mascaramento Manual de Labels e Token de Parada Explícito (`pc_training/colab_train_silva.py`)**:
    - Separação estrita entre `eos_token_id` (`<|im_end|>`) e `pad_token_id` (`<|endoftext|>`, token ID 0), prevenindo que o collator mascare o token de parada com `-100`.
    - Tokenização determinística em duas partes via `tokenize_chatml_example`: prompt com `labels = -100` e completion com paragem explícita `+ [eos_id]`.
    - Uso de `DataCollatorForSeq2Seq(tokenizer=tokenizer, padding=True, label_pad_token_id=-100)` com `Trainer`, eliminando qualquer dependência de Jinja `{% generation %}` do TRL.
    - Auditoria pré-treino com validação formal via `assert` garantindo que as labels ativas comecem com `<call>`, terminem com `<|im_end|>` e não contenham vazamentos do prompt.
    - Janela estendida para 1024 tokens com micro-batch 4, acumulação 8 e `gradient_checkpointing=True`, eliminando estouros de VRAM (`OutOfMemoryError`) na GPU T4.
    - Inferência pós-merge `[4/5]` atualizada com `eos_token_id=eos_id`, `pad_token_id=tokenizer.pad_token_id` e corte limpo no primeiro `<|im_end|>` ou `</call>`.
16. **Blindagem de `scan_wifi()` contra Falhas de Localização e API do Android**:
    - `tools/hardware.py` atualizado para tratar respostas da `Termux:API` retornadas como dicionário contendo `"API_ERROR"` (quando o GPS/Localização estiver desligado no Android 10+), evitando quebras por `AttributeError: 'str' object has no attribute 'get'`.
    - Mapeamento dinâmico de chaves `"frequency_mhz"` e `"frequency"`, além de tratamento resiliente de RSSI e segurança.
    - Testado em hardware real no smartphone via Wi-Fi (`192.168.0.106:5000`) com 16 redes reais escaneadas com sucesso.
17. **Deploy Automático e Sincronização via ADB**:
    - Fluxo de empacotamento atômico do código-fonte (`silva_code_update.tar.gz`) e transferência do modelo binário `silva-135m.gguf` via ADB sobre TCP/IP.
    - Scripts operacionais (`apply_code_update.sh` e `install_model_and_restart.sh`) com parada cirúrgica de instâncias antigas do `llama-server` e inicialização de background segura.
18. **Guia Passo a Passo para Usuários (`dataset/PASSO_A_PASSO.md`)**:
    - Documentação prática orientando o fluxo de edição de dados, execução de `prepare_final_dataset.py`, validação sintática via `validate_dataset.py` e upload no Google Colab.
19. **Calibração Fina de Roteamento Determinístico (Volume/Brilho, Typos Matemáticos e Restrição do `recall_note`)**:
    - *Extensibilidade de Nível em Volume e Brilho (`_extract_level`)*: Mapeamento determinístico de sinônimos de nível máximo (`total`, `totalmente`, `maximo`, `ao maximo`, `no maximo`, `no talo`, `no ultimo`, `completo`, `100%`, `tudo`) para `level=100`, nível mínimo (`minimo`, `ao minimo`, `no minimo`, `zerado`, `zero`, `mudo`, `silenciar`, `0%`) para `level=0`, e meio/metade para `level=50`.
    - *Tolerância a Typos no Normalizador Matemático (`_normalize_math_expression`)*: Pré-tratamento com `difflib.get_close_matches(cutoff=0.80)` nos tokens das expressões matemáticas contra o vocabulário de cálculo (`raiz`, `quadrada`, `cubica`, etc.), flexibilização de regexes de raízes quadradas (`quadrad[aoei]\w*` e `raiz de`) e cúbicas (`c[uú]bic[aoei]\w*`), além de remoção de fillers como `qual a ...` para extração limpa da AST.
    - *Restrição Estrita do `recall_note` e Bloqueio Enciclopédico*: Remoção da captura genérica gulosa baseada em `qual o`/`qual a`, exigência de marcadores explícitos de memória pessoal (`onde guardei`, `onde anotei`, `minha nota`, `qual a senha`, `lembra`, etc.), e bloqueio de termos matemáticos/perguntas enciclopédicas gerais para permitir resposta direta pelo LLM (ex: `qual a capital da franca` retorna `None`).
    - *Suíte Expandida e Deploy*: 23 testes automatizados passando 100% e atualização validada no hardware real do dispositivo via ADB e API HTTP.
20. **Ecossistema Wi-Fi Completo (`connect_wifi`, `get_wifi_info`, `set_wifi_state` — Catálogo Expandido para 39 Tools)**:
    - *`connect_wifi(ssid, password)`*: Conexão inteligente em duas camadas (Camada 1: `cmd wifi connect-network` direto com subprocesso seguro sem `shell=True`; Camada 2: Fallback sem root para Android 10+ copiando senha para o clipboard via `termux-clipboard-set` e abrindo `android.settings.WIFI_SETTINGS`). Salvamento automático da credencial na memória SQLite FTS5 (`remember_note(key='wifi <ssid>', value=password)`).
    - *`get_wifi_info()`*: Leitura de conexão atual via `termux-wifi-connectioninfo`, com conversão automática de IP inteiro de 32 bits little-endian para IPv4 pontuado via `socket.inet_ntoa(struct.pack('<I', ip_int))`, detecção de qualidade de sinal (%) e dBm, velocidade de link (Mbps) e montagem de link pronto para acesso web (`http://<ip>:<WEB_PORT>`).
    - *`set_wifi_state(state)`*: Controle liga/desliga de Wi-Fi via `termux-wifi-enable`, fallback `svc wifi` e fallback assistido em configurações.
    - *Roteamento Determinístico e Desambiguação Estrita*: Separação exata sem colisões entre `connect_wifi` (preservando maiúsculas e caracteres especiais de SSID e senha), `get_wifi_info` (status atual e IP), `set_wifi_state` (ligar/desligar), `scan_wifi` (varredura de redes próximas) e `recall_note` (senhas salvas), com deduplicação de chamadas consecutivas idênticas.
    - *Sincronia Total de Contratos e Dataset*: Schema JSON formal com 39 ferramentas e 46 parâmetros, `SILVA_SYSTEM_PROMPT` em `config.py` e `colab_train_silva.py` sincronizados, dataset consolidado com 6.381 amostras e suíte de 25 testes automatizados com 100% de aprovação.
21. **Resolução de Falso Negativo de Desconexão e Desambiguação de Wi-Fi vs Memória**:
    - *Tratamento de SSID Oculto sem GPS (`get_wifi_info`)*: No Android 10+, com localização desativada, `termux-wifi-connectioninfo` retorna `ssid="<unknown ssid>"`. A ferramenta não trata mais isso como desconexão se `supplicant_state == "COMPLETED"` ou se houver IPv4 válido, exibindo `"SSID oculto (ative o GPS para exibir o nome)"`. Adicionado fallback via socket UDP (`8.8.8.8:80`) para obtenção do IP local da LAN caso o comando omita o IP.
    - *Desambiguação `"qual meu wifi"` vs `"recall_note"`*: Adicionados gatilhos diretos para `get_wifi_info()` (`"qual meu wifi"`, `"qual o meu wifi"`, `"meu wifi"`, etc.), com bloqueio em `extract_memory()` para que perguntas sobre Wi-Fi sem a palavra `"senha"` não sejam capturadas como memória pessoal. Preserva `recall_note(query='senha do wifi')` quando a palavra `"senha"` estiver explicitamente presente.

### 7.2 Pontos de Atenção e Acoplamentos Restantes

1. **HTTP em texto claro (Plaintext).** A comunicação na rede local Wi-Fi ocorre sobre HTTP sem TLS (`0.0.0.0:5000`), dependendo do PIN estático (`X-Access-Pin`) para autorização na rede local.
2. **Snapshots de release binários legados.** Arquivos como `silva_deploy.tar.gz` e `silva_update.tar.gz` na raiz do workspace representam snapshots antigos e devem ser gerados novamente se for necessária uma distribuição empacotada.
3. **API e recursos privileged sem confirmação manual.** O PIN protege o endpoint `/api/chat`; chamadas telefônicas, SMS, câmera e volume executam imediatamente após a validação da chamada no parser.
4. **Dependência de permissões do Termux:API.** Chamadas nativas de hardware (Wi-Fi scan, GPS, SMS, câmera, áudio) exigem que as permissões do sistema Android tenham sido concedidas previamente ao aplicativo Termux:API.

### 7.3 Ordem recomendada para evolução futura do sistema

1. **Endurecimento de segurança na rede local.** Adicionar suporte opcional a HTTPS autoassinado na LAN e rate limiting básico de tentativas no endpoint de autenticação `/api/chat`.
2. **Pipeline de release e empacotamento.** Regenerar os arquivos de snapshot (`silva_deploy.tar.gz`) incorporando os novos scripts (`update_direct.sh`, `scheduler.py`), o catálogo completo de 36 ferramentas no pacote modular `tools/`, SQLite FTS5 e a nova suíte de testes.
3. **Testes de Integração em Hardware Real (Android/Termux).** Executar a suíte de testes diretamente no Termux do smartphone conectado via ADB para validar as chamadas nativas de `termux-api`.
