# Silva — Context Map Técnico

> Documento de referência atualizado por inspeção do projeto. Escopo inspecionado: `2026-11-25` (`main`). Convenções: `arquivo:linha` identifica a implementação; nomes de chaves, rotas e funções aparecem exatamente como no código. Suíte de testes: 101 testes unitários com 100% de aprovação (`Ran 101 tests in 3.151s, OK`).

## 1. Estrutura de Pastas e Árvore de Arquivos

### 1.1 Árvore do código do projeto

A árvore abaixo cobre a raiz do workspace, o repositório autoral `silva-agent/`, artefatos binários e diretórios gerados. `.git/` é metadado gerado do Git; seu conteúdo interno não é código do produto.

```text
Silva/
├── _archive_legacy/                         # arquivo morto: scripts, tarballs e capturas legadas movidos da raiz
├── update_direct.sh                         # autoral: sincroniza arquivos via ADB no Termux, reinicia com --background e valida PIDs + /api/health
├── termux-api-fdroid.apk                    # artefato: APK binário Termux:API (F-Droid)
├── termux-api.apk                           # artefato: APK binário Termux:API
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
    ├── README.md                            # autoral: documentação completa com arquitetura, fluxo Plug & Play, catálogo e diagnósticos
    ├── install-silva.sh                     # autoral: [1/4] instalador completo e idempotente para Termux e Linux desktop
    ├── config-silva.sh                      # autoral: [2/4] assistente interativo CLI para configuração (.env)
    ├── start_silva.sh                       # autoral: [3/4] inicializador unificado (llama-server + web_server + wake-lock + PIDs)
    ├── stop-silva.sh                        # autoral: [4/4] encerramento seguro e cirúrgico (runtime.pids, portas, wake-unlock)
    ├── .git/                                # artefato gerado: metadados e objetos do Git
    ├── android_agent/                       # runtime de produção no Termux
    │   ├── config.py                        # autoral: configuração, paths, TTS flags e prompt do LLM
    │   ├── conversation_context.py          # autoral: memória conversacional de curto prazo (multi-turno, TTL 30m) e resolução anafórica
    │   ├── intent_fallback.py               # autoral: roteador determinístico PT-BR com normalização estrutural e splitter com $prev_result
    │   ├── llm_client.py                    # autoral: cliente do llama-server com resolução anafórica e injeção de histórico recente
    │   ├── main.py                          # autoral: entrypoint CLI/Web
    │   ├── parser.py                        # autoral: parser AST, whitelist, encadeamento $prev_result e executor de calls
    │   ├── scheduler.py                     # autoral: daemon proativo (10s) sobre scheduled_events com pré-alerta, TTS (termux-tts-speak) e fila Web
    │   ├── start_silva.sh                   # autoral: wrapper de compatibilidade delegando para ../start_silva.sh
    │   ├── stop-silva.sh                    # autoral: wrapper de compatibilidade delegando para ../stop-silva.sh
    │   ├── nlp/                             # autoral: pacote modular de Processamento de Linguagem Natural
    │   │   ├── __init__.py                  # inicializador do pacote e exports principais
    │   │   ├── numbers.py                   # parser numérico composto extenso PT-BR
    │   │   ├── colloquial.py                # normalizador de gírias, níveis e correção de erros tipográficos (typos)
    │   │   └── router.py                    # roteador por pontuação de intenção (39 ferramentas), WhatsApp, tela UI e clima relativo
    │   ├── tools/                           # autoral: pacote modular das 39 ferramentas Android auditado via AST
    │   │   ├── __init__.py                  # re-export retrocompatível e AVAILABLE_TOOLS
    │   │   ├── adb_bridge.py                # ponte ADB local (127.0.0.1/Wi-Fi) com auto-reconexão e fallback Termux:API
    │   │   ├── contacts.py                  # resolvedor unificado de contatos (número -> memory.db -> termux-contact-list + desambiguação)
    │   │   ├── ui_automator.py              # motor de visão/interação Android via uiautomator XML + input tap/clipboard PT-BR
    │   │   ├── core.py                      # paths, locks, processos, telefones, apps e cache de localização (save/load)
    │   │   ├── hardware.py                  # bateria, lanterna, DND, vibração, volume, brilho, ecossistema Wi-Fi
    │   │   ├── media.py                     # foto, screenshot, gravação de vídeo, media_control
    │   │   ├── comms.py                     # SMS, automação WhatsApp, discagem com contatos, notificações, clipboard
    │   │   ├── weather_web.py               # GPS, mapa, previsão Open-Meteo em 3 níveis com cache, e busca web multi-fonte
    │   │   ├── apps_mobility.py             # open_app, interact_screen, uber, ifood, play store, piadas, list_capabilities
    │   │   └── memory_schedule.py           # SQLite FTS5 + scheduled_events (migração events.json), alarmes, recorrência e calculadora AST
    │   ├── web_server.py                    # autoral: servidor ReusableThreadingHTTPServer com SO_REUSEADDR, fallback de porta e API REST
    │   ├── __pycache__/                     # artefato gerado: bytecode Python 3.12
    │   ├── captures/                        # diretório de estado gerado: fotos, vídeos, prints e mapas
    │   │   └── .gitkeep                     # placeholder versionado
    │   ├── data/                            # diretório de estado: SQLite FTS5 (memory.db), last_location.json, runtime.pids
    │   │   └── .gitkeep                     # placeholder versionado
    │   ├── models/                          # diretório de artefatos de modelo
    │   │   ├── .gitkeep                     # placeholder versionado
    │   │   ├── silva-135m.gguf              # artefato: modelo local ativo, Q5_K_M
    │   │   └── old/                         # artefato: versões anteriores do modelo
    │   │       ├── silva-135m-V0.0.1.gguf   # artefato: modelo GGUF V0.0.1
    │   │       └── silva-135m-V0.0.2.gguf   # artefato: modelo GGUF V0.0.2
    │   └── static/                          # frontend estático sem build
    │       └── index.html                   # autoral: UI web responsiva, modo de voz "Segure para falar", ondas sonoras e SVG
    ├── dataset/                             # engenharia e artefatos de dados autorais
    │   ├── schema.json                      # autoral: contrato customizado de 39 ferramentas/44 parâmetros
    │   ├── seed_examples.jsonl              # autoral: 149 exemplos-base (incluindo clima relativo e variações de temperatura)
    │   ├── train.jsonl                      # autoral/estado: 5.743 exemplos limpos e enriquecidos
    │   ├── train.jsonl.bak                  # autoral/backup: 4.140 exemplos anteriores ao reparo
    │   ├── train_clean.jsonl                # autoral/estado: 5.790 exemplos limpos de treino
    │   ├── eval_clean.jsonl                 # autoral/estado: 304 exemplos limpos de avaliação
    │   ├── silva_colab_dataset.jsonl        # autoral/estado: 6.381 exemplos consolidados (100% schema)
    │   ├── prepare_final_dataset.py          # autoral: valida, enriquece, deduplica e divide
    │   ├── repair_train_dataset.py           # autoral: corrige e enriquece o dataset de treino
    │   ├── validate_dataset.py               # autoral: validador AST/schema dos JSONL
    │   └── __pycache__/                     # artefato gerado: bytecode Python 3.12
    ├── pc_training/                         # pipeline de treinamento e exportação
    │   ├── colab_train_silva.py             # autoral: pipeline autônomo de SFT, merge e quantização
    │   ├── train_sft.py                     # autoral: pipeline SFT local, sem chamada à função train()
    │   ├── export_gguf.py                   # autoral: merge, conversão e quantização GGUF
    │   └── requirements_pc.txt              # autoral: dependências do pipeline desktop
    └── tests/                               # autoral: suíte de testes unitários e de integração (69 testes 100% passando)
        ├── __init__.py                      # marcador de pacote de testes
        ├── test_adb_bridge.py               # testes da ponte ADB local e fallback Termux:API
        ├── test_contacts_and_scheduler.py   # testes de contacts.py, migração scheduled_events e scheduler proativo TTS
        ├── test_contracts.py                # validação de schemas (39 tools), dataset consolidado e prompts sincronizados
        ├── test_conversation_pipeline.py    # testes de memória multi-turno, isolamento de sessões e $prev_result
        ├── test_intent_fallback.py          # testes de casamento de intenções, clima relativo e desambiguação
        ├── test_parser_and_fallback.py      # testes de AST, whitelist, fallback e tolerâncias
        ├── test_tools_and_memory.py         # testes de FTS5, calculadora, fallback de clima em 3 níveis e smoke test das 39 tools
        ├── test_ui_automator.py             # testes de uiautomator XML, WhatsApp e interação de tela
        └── test_web_server.py               # testes HTTP, autenticação PIN e proteção contra Path Traversal
```

### 1.2 Inventário de arquivos autorais e artefatos

Contagens usam linhas físicas. Arquivos de dados JSONL são autorais; binários, `.pyc`, pacotes e `.git/` são artefatos.

| Caminho | Papel |
|---|---|
| `update_direct.sh` | Sincronização direta via ADB para `/data/data/com.termux/files/home/silva-agent`, reinício via `./start_silva.sh --background` e validação real de PIDs (`kill -0`) + `GET /api/health`. |
| `silva-agent/.env.example` | Contrato de variáveis de ambiente (inclui `ADB_TARGET`, `ENABLE_PROACTIVE_TTS`, `WEB_AUTO_TTS`). |
| `silva-agent/.gitignore` | Exclusões de secrets, mídia, modelos, caches e backups. |
| `silva-agent/README.md` | Documentação principal completa com arquitetura, fluxo Plug & Play em 4 scripts, ciclo de vida de processos, catálogo das 39 ferramentas e resolução de problemas. |
| `silva-agent/install-silva.sh` | [1/4] Instalador completo e idempotente (Termux/Desktop): dependências base, compilação/instalação de llama-server, diretórios e .env. |
| `silva-agent/config-silva.sh` | [2/4] Assistente interativo CLI para configuração de PIN, porta web, TTS (`ENABLE_VOICE_TTS`, `ENABLE_PROACTIVE_TTS`, `WEB_AUTO_TTS`), hardware e cidade padrão no .env. |
| `silva-agent/start_silva.sh` | [3/4] Inicializador unificado com modo `--background`/`--daemon`, desacoplamento via `setsid`/`nohup` (`</dev/null`, `logs/llama.log`, `logs/web.log`), wake-lock e tracking em `data/runtime.pids` (`llama_pid=`, `web_pid=`). |
| `silva-agent/stop-silva.sh` | [4/4] Encerramento seguro e cirúrgico de instâncias via `data/runtime.pids` (suporta `chave=PID` e `PID` puro), liberação de portas e wake-unlock. |
| `silva-agent/android_agent/config.py` | Configuração, paths, flags ADB/TTS e prompt de function calling. |
| `silva-agent/android_agent/conversation_context.py` | Memória conversacional de curto prazo (TTL 30m, até 6 turnos), resolução anafórica e contexto compacto para o LLM. |
| `silva-agent/android_agent/intent_fallback.py` | Roteador determinístico de intenções PT-BR com mascaramento de entidades (Camada 1), splitter protegido contra contexto (Camada 6) e encadeamento `$prev_result`. |
| `silva-agent/android_agent/nlp/` | Pacote modular NLP (`numbers.py`, `colloquial.py`, `router.py`, `__init__.py`) com blindagem em 6 camadas: mascaramento reversível (`_mask_protected_entities`), limpeza de vocativos/cortesia (`_strip_conversational_fillers`), validação estrita de slots, guarda global de negações/passado (`none()`), margem de confiança (`MIN_CONFIDENCE_MARGIN=0.12`) e tabela de desempate. |
| `silva-agent/android_agent/llm_client.py` | Cliente HTTP do `llama-server` com resolução anafórica, Recordação Ativa Pré-LLM (`active_recall_search`), orçamento dinâmico de tokens (`LLM_CONTEXT_SIZE=2048`), circuit breaker (`30s`), histórico recente e medição de latência. |
| `silva-agent/android_agent/main.py` | Entry point CLI/Web com `session_id="cli_local"` no modo CLI e inicialização do daemon `scheduler`. |
| `silva-agent/android_agent/parser.py` | Parser AST, whitelist de 63 ferramentas, substituição dinâmica de `$prev_result` (até 600 chars) e atualização da sessão. |
| `silva-agent/android_agent/scheduler.py` | Daemon proativo (poll 10s) sobre `scheduled_events` e `context_reminders` (gatilhos por Wi-Fi) no `memory.db` com pré-alerta (10 min), vibração, notificação, `termux-tts-speak`, recorrências (`daily`/`weekdays`/`weekly`) e fila `pop_triggered_alerts()`. |
| `silva-agent/android_agent/start_silva.sh` | Wrapper leve de compatibilidade que delega a execução para `../start_silva.sh`. |
| `silva-agent/android_agent/stop-silva.sh` | Wrapper leve de compatibilidade que delega o encerramento para `../stop-silva.sh`. |
| `silva-agent/android_agent/tools/` | Pacote modular das **63 ferramentas** em 11 arquivos (`core`, `adb_bridge`, `contacts`, `ui_automator`, `hardware`, `media`, `comms`, `weather_web`, `apps_mobility`, `memory_schedule`, `__init__`), incluindo Notas & Lembretes Multimodais (`save_voice_note`, `get_voice_notes`, `check_voice_note` na tabela `voice_notes`), Memória Inteligente 2.0 (`remember_note` com captura livre e TTL, `recall_note` com tempo relativo e auto-clipboard, `forget_note`, `list_memories`, `remind_on_wifi`), listas dinâmicas (`add_list_item`, `get_list`, `remove_list_item` na tabela `lists` do `memory.db`), `navigate_to`, `play_media`, `send_whatsapp`, `summarize_notifications`, `record_audio`, `convert_units`, `get_datetime`, `get_system_info`, `read_screen`, `save_contact`, `get_contact` e controles de conectividade ADB, auditado via AST. |
| `silva-agent/android_agent/web_server.py` | Servidor HTTP com `SO_REUSEADDR`, limite `HTTP 413` (`8 MB`), whitelist `ALLOWED_AUDIO_EXTENSIONS`, rate-limit progressivo de PIN, `X-Session-Id`/`session_id` em `POST /api/chat`, `POST /api/voice-notes/check`, `POST /api/voice-notes/upload`, `triggered_alerts` + `web_auto_tts` em `GET /api/health` e proteção anti-path traversal. |
| `silva-agent/android_agent/static/index.html` | Frontend responsivo estilo Claude/DeepSeek com `session_id` por conversa, modo "Segure para falar", atalho rápido "🎙️ Nota" (`MediaRecorder`), checklist interativo multimodal com player `<audio>` e checkbox animado, botão de voz TTS (`window.speechSynthesis` PT-BR), botão `"📋 Copiar"` para `clipboard_text` e toast de alertas proativos. |
| `silva-agent/tests/` | Suíte de testes automatizados unitários, adversariais (`test_router_conflicts.py`), auditoria de contratos (`test_contracts.py` via `inspect.signature`) e integração (**101 testes 100% passando** em `3.151s`). |
| `silva-agent/dataset/schema.json` (450 linhas) | Contrato estrito de 39 ferramentas e 44 parâmetros. |
| `silva-agent/dataset/seed_examples.jsonl` (149 linhas) | Base canônica de 149 exemplos com casos de clima relativo e variações de temperatura. |
| `silva-agent/dataset/train.jsonl` (5.743 linhas) | Estado local de treino enriquecido com novas ferramentas e casos de uso. |
| `silva-agent/dataset/train.jsonl.bak` (4.140 linhas) | Backup anterior ao reparo. |
| `silva-agent/dataset/train_clean.jsonl` (5.790 linhas) | Divisão limpa de treino (95% do dataset consolidado). |
| `silva-agent/dataset/eval_clean.jsonl` (304 linhas) | Divisão limpa de avaliação (5% do dataset consolidado). |
| `silva-agent/dataset/silva_colab_dataset.jsonl` (6.381 linhas) | Dataset consolidado usado no Colab (100% aderente ao schema de 39 tools). |
| `silva-agent/dataset/prepare_final_dataset.py` (383 linhas) | Preparação e split do dataset final. |
| `silva-agent/dataset/repair_train_dataset.py` (572 linhas) | Reparo/enriquecimento do dataset de treino. |
| `silva-agent/dataset/validate_dataset.py` (185 linhas) | Validador de dataset. |
| `silva-agent/pc_training/colab_train_silva.py` (339 linhas) | Pipeline completo Google Colab. |
| `silva-agent/pc_training/train_sft.py` (181 linhas) | Treinamento SFT desktop previsto. |
| `silva-agent/pc_training/export_gguf.py` (102 linhas) | Conversão HF→GGUF e quantização previstas. |
| `silva-agent/pc_training/requirements_pc.txt` (21 linhas) | Dependências não fixadas do treinamento. |
| `screen_termux.png` | Evidência visual de execução anterior; não é fonte. |
| `silva_deploy.tar.gz` | Snapshot de implantação antigo. |
| `silva_update.tar.gz` | Patch de implantação antigo. |
| `termux-api.apk`, `termux-api-fdroid.apk` | Builds binários de terceiros. |
| `platform-tools/**` | Android platform-tools de terceiros, revisão `37.0.3`. |
| `silva-agent/android_agent/models/**/*.gguf` | Três binários GGUF; somente `silva-135m.gguf` é referenciado pelo start. |
| `**/__pycache__/*.pyc` | Bytecode Python 3.12 gerado. |
| `silva-agent/.git/**` | Metadados e objetos do Git. |

**Mecanismo real de persistência:** O sistema utiliza **SQLite 3 com motor de busca textual FTS5 (`silva-agent/android_agent/data/memory.db`)** para memória persistente de longo prazo (tabela `memories` e índice virtual `memories_fts` sincronizado por triggers, transações ACID, modo WAL e classificação automática por categoria). Para os arquivos de estado JSON (`last_location.json`, `events.json`, `dnd_backup.json`), emprega escrita atômica segura (`_atomic_write_json` via arquivo temporário + `fsync` + `replace`) protegida por lock reentrante de threads (`_FILE_LOCK = threading.RLock()`). Rastreamento de processos é feito em `silva-agent/android_agent/data/runtime.pids`. Multimídia usa arquivos em `silva-agent/android_agent/captures/`; configuração usa `.env`; navegador usa `localStorage["silva_pin"]`; agendamento usa daemon reentrante `scheduler.py`; treinamento usa JSONL (6.381 amostras) e artefatos GGUF.

## 2. Anatomia Completa do Estado e Modelos de Dados

### 2.1 Raiz do estado do runtime

O estado do runtime é distribuído de forma determinística entre:

1. **Memória volátil do processo:** `llm_client` global, `_LAST_JOKE` e argumentos locais (`web_server.py`, `tools/apps_mobility.py`);
2. **Banco de dados relacional e motor de busca:** SQLite 3 com tabela virtual FTS5 em `silva-agent/android_agent/data/memory.db`;
3. **Arquivos JSON gravados com escrita atômica e protegidos por `_FILE_LOCK = threading.RLock()` em `silva-agent/android_agent/data/`:**
   - `events.json`: agenda e lembretes locais;
   - `last_location.json`: cache persistente da última localização conhecida com rótulo geocodificado;
   - `dnd_backup.json`: backup de volumes por stream de áudio durante o modo Não Perturbe;
   - `runtime.pids`: arquivo com PIDs dos processos ativos em background (`llama_pid`, `web_pid`);
4. **Arquivos de mídia em `android_agent/captures/`:** fotos, vídeos, screenshots e mapas;
5. **Configuração carregada de `.env`/`.env.example` (`android_agent/config.py`);**
6. **PIN e preferências persistidos no navegador (`localStorage["silva_pin"]`).**

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

### 2.3 `last_location.json` (Cache Persistente de Localização)

Raiz: objeto JSON; mantido por `save_last_location()` e consultado por `load_last_location()` e `get_weather()` (`android_agent/tools/core.py:115-155`, `android_agent/tools/weather_web.py:110-180`).

```json
{
  "latitude": -23.55052,
  "longitude": -46.633308,
  "label": "São Paulo, SP",
  "updated_at": "2026-11-24T10:45:00",
  "timestamp": "2026-11-24T10:45:00",
  "maps_url": "https://www.google.com/maps?q=-23.55052,-46.633308",
  "image_url": null,
  "provider": "termux"
}
```

- **Gravação Atômica e Thread-Safe:** Atualizado via `save_last_location(lat, lon, label)` usando `_atomic_write_json()` sob `_FILE_LOCK`.
- **Retrocompatibilidade de Campos:** Garante tanto `updated_at` quanto `timestamp` para preservar clientes legados e novos módulos.
- **Resolução de Rótulo Amigável (`_reverse_geocode_label`):** Executa reverse geocoding em cascata:
  1. Nominatim (OpenStreetMap) via `https://nominatim.openstreetmap.org/reverse` com timeout de 3s e `User-Agent: SilvaAgent/1.0`.
  2. BigDataCloud Client API via `https://api.bigdatacloud.net/data/reverse-geocode-client` com timeout de 3s.
  3. Formatação pura de coordenadas `Lat -XX.XXXX, Lon -YY.YYYY` caso os serviços remotos estejam inacessíveis.

### 2.4 `runtime.pids` (Controle de Processos em Execução)

Raiz: formato chave-valor texto ou linhas de PIDs gravadas pelo script de inicialização (`silva-agent/start_silva.sh:160-175`).

```text
llama_pid=12345
web_pid=12346
```

- **Criação:** `./start_silva.sh` grava os PIDs em segundo plano de `llama-server` e `python3 main.py` no arquivo `android_agent/data/runtime.pids`.
- **Consumo:** `./stop-silva.sh` lê os PIDs salvos, envia sinal gracioso `kill -TERM`, monitora término por até 2s, e aplica `kill -KILL` caso necessário, removendo o arquivo em seguida.

### 2.5 `dnd_backup.json`

Raiz: objeto JSON de volumes por stream (`silva-agent/android_agent/tools/hardware.py`).

```json
{
  "ring": 5,
  "notification": 5,
  "system": 5
}
```

- Streams alvo: `ring`, `notification`, `system`.
- Arquivo removido atomicamente após a restauração dos volumes ao desativar o Não Perturbe (`set_dnd(False)`).

### 2.6 Capturas persistidas

| Padrão | Entidade | Criação |
|---|---|---|
| `capture_YYYYMMDD_HHMMSS.jpg` | foto | `silva-agent/android_agent/tools/media.py` |
| `screen_<epoch>.png` | screenshot | `silva-agent/android_agent/tools/media.py` |
| `vid_<epoch>.mp4` | vídeo | `silva-agent/android_agent/tools/media.py` |
| `loc_<epoch>.png` | mapa | `silva-agent/android_agent/tools/weather_web.py` |

### 2.7 Estado do cliente web

| Chave | Tipo | Default | Persistência |
|---|---|---|---|
| `silva_pin` | `string` | `"1234"` | `localStorage` (`android_agent/static/index.html`). |
| `silva_chats_v2` | `object` | `{}` | `localStorage` (`android_agent/static/index.html`). |

### 2.8 Modelo do dataset

Cada linha dos JSONL é um registro com duas chaves obrigatórias (`silva-agent/dataset/seed_examples.jsonl`):

```json
{
  "prompt": "string",
  "completion": "<call>func_name(arg='val')</call>"
}
```

O contrato formal de tools é `dataset/schema.json`, cobrindo 39 ferramentas e 44 parâmetros formais, tipos `string|integer|boolean`; obrigatoriedade é marcada por `"required": true` dentro do parâmetro.

## 3. Mapeamento Detalhado de Todos os Arquivos Backend / Core

### 3.1 `silva-agent/android_agent/config.py`

Configuração central e prompt.
- `load_env(env_path: Path)` → `None`: lê `.env`, ignora vazios/comentários/linhas sem `=`, remove aspas e não sobrescreve variáveis existentes.
- Paths: `BASE_DIR`, `PROJECT_ROOT`, `ENV_FILE`, `CAPTURES_DIR`.
- Parâmetros: `WEB_HOST` (`"0.0.0.0"`), `WEB_PORT` (`5000`), `ACCESS_PIN` (`"1234"`), `LLAMA_SERVER_URL` (`"http://127.0.0.1:8080"`), `LLM_TIMEOUT_SECONDS` (`15`).
- Flags de ambiente: `HAS_TERMUX`, `SIMULATE_HARDWARE`.
- `SILVA_SYSTEM_PROMPT`: lista das 39 ferramentas com exemplos e restrição estrita de saída a tags `<call>...</call>`.

### 3.2 `silva-agent/android_agent/main.py`

- `print_banner()` → `None`: imprime URL do LLM, status do scheduler e estado de simulação.
- `run_cli_mode()` → `None`: inicializa `scheduler.start_scheduler()`, loop `input()`, aceita calls diretas, consulta o cliente LLM e executa.
- `run_web_mode(host: str, port: int)` → `None`: inicializa `scheduler.start_scheduler()`, banner e `start_server()`.
- `main()` → `None`: parse de flags `--web`, `--cli`, `--host`, `--port`; web é o default.

### 3.3 `silva-agent/android_agent/web_server.py`

- `ReusableThreadingHTTPServer(ThreadingHTTPServer)`: subclasse com `allow_reuse_address = True` (`SO_REUSEADDR`) e `daemon_threads = True`.
- `SilvaHTTPRequestHandler._send_json(data: dict, status: int = HTTPStatus.OK)` → `None`: JSON UTF-8 e CORS `*`.
- `SilvaHTTPRequestHandler._send_file(file_path: Path, mime_type: str)` → `None`: envia arquivo ou 404.
- `SilvaHTTPRequestHandler.do_OPTIONS()` → `None`: preflight 204.
- `SilvaHTTPRequestHandler.do_GET()` → `None`: roteia `/`, `/index.html`, `/captures/*` (com PIN check e anti-traversal), `/api/health`.
- `SilvaHTTPRequestHandler.do_POST()` → `None`: valida PIN no header `X-Access-Pin`, gera call via fallback determinístico ou LLM, executa e propaga status real (`ok`, `partial_error`, `error`).
- `start_server(host: str, port: int)` → `None`: instancia o servidor com fallback dinâmico de portas (`port` até `port + 5`) em caso de `errno.EADDRINUSE`, registra handlers de `SIGINT`/`SIGTERM` e chama `shutdown()`/`server_close()` no encerramento.

### 3.4 `silva-agent/android_agent/llm_client.py`

- `SilvaLLMClient.__init__(base_url, timeout)`: normaliza URL.
- `SilvaLLMClient.check_health()` → `dict`: tenta `/health`, fallback para `/`; retorna status online, URL e erros.
- `SilvaLLMClient.generate_call(user_prompt)` → `Tuple[Optional[str], float, Optional[str]]`: tenta primeiro o roteador de intenções determinístico (`match_intent_fallback`). Caso não reconheça, submete ChatML ao endpoint `POST /completion` do `llama-server`.

### 3.5 `silva-agent/android_agent/intent_fallback.py` e Pacote `android_agent/nlp/`

Arquitetura modular de NLP e intent fallback determinístico dividida em 4 pilares:

- **Normalização Estrutural Única (`_prepare_texts`):**
  - Executa na entrada de `match_intent_fallback()` e nos extratores de intenção.
  - `raw_clean`: unifica quebras de linha (`\n`, `\r`), tabs e espaços duplos em um espaço único, preservando maiúsculas e caracteres especiais técnicos (SSIDs complexos como `HENRIQUE_NET//FERNANDA`, senhas com `@/#`).
  - `norm_clean`: remove acentos e normaliza para minúsculas (`_strip_accents(raw_clean).lower()`).
- **Pilar A: Parser Numérico Composto (`android_agent/nlp/numbers.py`):**
  - Converte números compostos por extenso (`"vinte e cinco"` → `"25"`, `"cento e cinquenta"` → `"150"`).
  - Tratamento contextual de horários: `"meia-noite"` → `"00:00"`, `"meio-dia"` → `"12:00"`, `"meia hora"` → `"30 minutos"`.
  - Proteção de artigos indefinidos (`"um"`/`"uma"` não viram número antes de substantivos de ação).
- **Pilar B: Normalizador de Gírias, Níveis e Typos (`android_agent/nlp/colloquial.py`):**
  - Mapeamento determinístico de níveis (`"no talo"`, `"no máximo"` → `"100%"`; `"no mudo"`, `"zerado"` → `"0%"`).
  - Gírias de apps: `"zap"`, `"wpp"` → `"whatsapp"`; `"yt"` → `"youtube"`; `"spot"` → `"spotify"`.
  - Correção de erros de digitação via `difflib.get_close_matches(cutoff=0.82)`.
- **Pilar C: Roteador por Pontuação de Intenção (`android_agent/nlp/router.py`):**
  - `ScoredIntentRouter`: Extratores por domínio retornam `(score: float, call_str: str)`.
  - Resolução explícita de ambiguidades por peso (Wi-Fi senha → `recall_note`; Wi-Fi listar → `scan_wifi`; Wi-Fi conectar → `connect_wifi`).
  - **Tratamento de Clima e Localização Relativa (`_clean_weather_location`, `extract_weather`):**
    - Identifica variações naturais de intenção: `"temperatura"`, `"quantos graus"`, `"clima"`, `"tempo"`, `"como esta o tempo"`, `"previsao do tempo"`, `"quanto esta fazendo"`.
    - Detecta referências locais/relativas (`"aqui"`, `"onde estou"`, `"por aqui"`, `"minha cidade"`, `"meu bairro"`, `"minha regiao"`, `"local atual"`, `"na minha cidade"`) e **limpa a localização para `location=''`**, forçando o disparo do fallback baseado no dispositivo.
    - Suporta próclises PT-BR (`"se conecte"`, `"me conecta"`, `"me diga"`, `"me mostre"`).
- **Pilar D: Splitter Inteligente de Cláusulas Compostas (`intent_fallback.py`):**
  - Executa a divisão de comandos compostos após a normalização numérica e protege nomes próprios compostos. Concatena `<call>...</call><call>...</call>` para comandos múltiplos.

### 3.6 `silva-agent/android_agent/parser.py`

- `parse_function_calls(model_output: str)` → `List[Tuple[str, Dict[str, Any]]]`: extrai tags `<call>...</call>`, aplica whitelist de 39 ferramentas, faz parsing AST com `ast.parse` literal, binding de assinatura contra a função registrada, aplicação de defaults e validação estrita de tipos.
- `execute_call(model_output: str)` → `Dict[str, Any]`: executa chamadas em sequência, coleta mensagens, dados e mídias geradas, propagando status real consolidado (`"ok"`, `"partial_error"`, `"error"`).

### 3.7 `silva-agent/android_agent/tools/` (Pacote Modular)

Pacote modular desacoplado sob `silva-agent/android_agent/tools/`, 100% auditado contra símbolos não definidos via AST estático:

- **`core.py`:** Paths (`DATA_DIR`, `CAPTURES_DIR`), lock reentrante (`_FILE_LOCK`), escrita atômica segura (`_atomic_write_json`), serialização de eventos, execução segura de comandos do Termux (`_run_termux_cmd`, `_exec_android_intent`), sanitização de telefones, mapa de aplicativos Android e **cache persistente de localização (`save_last_location`, `load_last_location`)**.
- **`hardware.py`:** Bateria (`get_battery`), lanterna (`set_torch`), Não Perturbe (`set_dnd`), vibração (`vibrate`), volume (`set_volume`), brilho (`set_brightness`) e ecossistema Wi-Fi completo (`scan_wifi`, `connect_wifi`, `get_wifi_info`, `set_wifi_state`).
- **`media.py`:** Foto (`take_photo`), vídeo (`record_video`), screenshot com verificação PNG (`take_screenshot`) e controle de sessão de mídia (`media_control`).
- **`comms.py`:** SMS (`get_last_sms`, `send_sms`), discagem nativa (`make_call`), notificações (`get_notifications`) e área de transferência com orientação clara sobre bloqueio em segundo plano (`get_clipboard`, `set_clipboard`).
- **`weather_web.py`:**
  - Localização geográfica (`get_location`, `set_location_state`, `get_last_location`).
  - Reverse geocoding resiliente (`_reverse_geocode_label`) via Nominatim OSM -> BigDataCloud -> coordenadas puras.
  - **Previsão meteorológica em 3 níveis (`get_weather`):**
    - *Nível 1 (Dispositivo Ativo):* Se `location=''` e GPS ativo, obtém coordenadas reais (`_get_current_device_location`), resolve rótulo amigável com reverse geocoding, salva em cache atômico (`save_last_location`) e consulta Open-Meteo.
    - *Nível 2 (Cache Offline):* Se GPS inativo e houver cache válido em `data/last_location.json`, consulta Open-Meteo usando as coordenadas salvas e adiciona aviso transparente: `"Localização atual desativada — usando última localização registrada (<label> em <updated_at>): ..."`.
    - *Nível 3 (Orientação Clara):* Se GPS inativo e sem cache salvo, retorna instrução amigável orientando a ativar a localização do aparelho ou informar o nome da cidade.
    - Filtro anti-chuvisco falso calibrando probabilidades $< 35\%$ e volumes $\le 0.5\text{ mm}$ para tempo firme/parcialmente nublado.
  - **Busca web multi-fonte (`search_google`):**
    - Remoção de artigos iniciais via `_strip_leading_articles(q)`.
    - URLs cruas eliminadas do texto corrido `message`, encapsuladas em Markdown compacto `[Título](url)` e metadados estruturados para o frontend.
    - Cascata: 1ª Wikipédia PT-BR REST API; 2ª Google News RSS PT-BR; 3ª DuckDuckGo HTML Lite sem dependências externas.
- **`apps_mobility.py`:** Abertura de aplicativos (`open_app`), mobilidade urbana no Uber/99 (`request_ride`), delivery no iFood/99Food (`order_food`). Super-app 99 automatizado via `_prepare_99_app(target_tab)` (`'ride'`/`'food'`): pré-ativa GPS via `set_location_state(True)` para corridas, abre `com.taxis99.food` (se instalado via `pm list packages`) ou `com.taxis99`, aguarda splash `3.5s`, exige ADB + `is_screen_unlocked()` sob `_UI_LOCK` e executa `_stabilize_99_ui` (até 3 iterações: diálogo `Precisão de Local` → `Ativar`, modal de cupons `_dismiss_99_promo` → `X`/`50%/81%`, e tela `Habilitar Serviços de Localização` → `set_location_state(True)` + `Inserir localização manualmente`) e alterna abas inferiores (`Corrida` `20%/92%`, `Food` `40%/92%`). `order_food(app='99food')` → `_automate_99_food_search_via_ui` (barra `11%–20%`, fallback `50%/14.5%`, Enter `66`, `method='ui_automator_search'`); `request_ride(app='99')` → `_automate_99_ride_via_ui` (campo `Para onde vamos?` `30%–45%`, fallback `50%/36%`, toca 1ª sugestão que contém todos os termos do destino, `method='ui_automator_destination'`); sem ADB/tela bloqueada cai no deep link/pacote. No NLP, `táxi`/`taxi` sem menção a Uber → `request_ride(app='99')`. Também: instalação na Play Store (`install_app`), piadas sem repetição (`tell_joke`), capacidades do agente (`list_capabilities`) e chamada nula neutra (`none`).
- **`memory_schedule.py`:** Memória persistente SQLite 3 FTS5 (`remember_note`, `recall_note`), interpretação de datas/horas PT-BR (`parse_ptbr_date`, `parse_time_str`), alarmes e eventos (`set_alarm`, `cancel_alarm`, `schedule_event`, `set_timer`) e avaliador matemático científico via AST (`SafeMathEvaluator`, `calculate`).
- **`__init__.py`:** Re-exporta todas as funções públicas e o catálogo `AVAILABLE_TOOLS` (39 ferramentas nativas).

### 3.8 Scripts Operacionais Oficiais

O projeto possui **4 scripts principais** na raiz (`silva-agent/`), garantindo ciclo de vida completo e padronizado:

1. **`./install-silva.sh`:** Instalador completo e idempotente para Termux e Linux desktop. Detecta ambiente, atualiza pacotes essenciais (`python`, `termux-api`, `curl`, `git`, `cmake`, `clang`), localiza ou compila o `llama-server`, estrutura pastas (`models`, `data`, `captures`, `logs`) e cria `.env` seguro.
2. **`./config-silva.sh`:** Assistente CLI interativo com menu para configurar PIN de acesso, porta web, TTS, hardware e cidade padrão, atualizando o `.env` atomicamente.
3. **`./start_silva.sh`:** Inicializador unificado com auto-setup preventivo, wake-lock no Android (`termux-wake-lock`), liberação de portas (5000 e 8080), subida em background do `llama-server` (`-c 1024 -t 4`), monitoramento de healthcheck, gravação de PIDs em `android_agent/data/runtime.pids`, trap de encerramento seguro e inicialização do servidor web.
4. **`./stop-silva.sh`:** Encerramento seguro e completo em 3 etapas: `[1/3]` lê PIDs de `data/runtime.pids` e envia `kill -TERM` com grace period de 2s e `kill -KILL` residual; `[2/3]` varredura de processos órfãos (`llama-server`, `main.py`) e portas 5000/8080; `[3/3]` liberação de wake-lock via `termux-wake-unlock`.
5. **`update_direct.sh` (Raiz do Workspace):** Script de sincronização via ADB push com caminho explícito `/data/data/com.termux/files/home/silva-agent`, tratamento recursivo contra aninhamentos indevidos de diretórios e reinício de serviços dentro da sessão do Termux.

## 4. Fórmulas Reais, Regras de Negócio e Fluxos Críticos

### 4.1 Cadeia de Fallback de Clima em 3 Níveis (`get_weather`)

Quando `location=''` (ou quando o usuário faz perguntas de localização relativa como `"minha cidade"`, `"meu bairro"`, `"aqui"`):

```text
Entrada: get_weather(day, time, location='')

1. Nível 1: Dispositivo Ativo
   -> Tenta ler coordenadas via Termux:API (_get_current_device_location)
   -> Se sucesso (lat, lon):
      - Resolve nome amigável via _reverse_geocode_label(lat, lon)
      - Grava cache atômico: save_last_location(lat, lon, label)
      - Consulta Open-Meteo(lat, lon)
      - Retorna clima formatado para o local atual

2. Nível 2: Cache Offline
   -> Se GPS desativado/inacessível:
      - Consulta cache persistente: cache = load_last_location()
      - Se cache válido (lat, lon):
         - Consulta Open-Meteo(lat, lon)
         - Adiciona aviso transparente no início da resposta:
           "Localização atual desativada — usando última localização registrada ({label} em {updated_at}): {previsao}"

3. Nível 3: Orientação ao Usuário
   -> Se GPS desativado E sem cache em last_location.json:
      - Retorna mensagem orientando:
        "Não foi possível obter sua localização atual (GPS desativado) e não há localização
         anterior salva em cache. Por favor, ative a localização do aparelho ou informe o
         nome da cidade (ex: 'clima em Recife')."
```

### 4.2 Projeção Web Mercator do Mapa

```text
n = 1 << zoom                         # zoom = 16
x_exact = (lon + 180.0) / 360.0 * n
x_tile = int(x_exact)
lat_rad = math.radians(lat)
y_exact = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
y_tile = int(y_exact)
(silva-agent/android_agent/tools/weather_web.py)
```

### 4.3 Busca e Ranqueamento da Memória (SQLite FTS5)

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

### 4.4 Avaliador Matemático e Científico (`SafeMathEvaluator`)

Permite:
- Operações aritméticas: `+`, `-`, `*`, `/`, `//`, `%`, `**`, unário `+`/`-`.
- Funções matemáticas seguras: `sqrt`, `cbrt`, `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `log`, `log10`, `log2`, `exp`, `factorial`, `abs`, `round`, `floor`, `ceil`.
- Constantes: `pi`, `e`.
- Regras de segurança estritas:
  - Rejeita valores booleanos (`isinstance(node.value, bool)` gera erro para impedir casts indevidos).
  - Expoente máximo protegido: rejeita quando `abs(right) > 1000`.
  - Divisão ou módulo por zero rejeitados com mensagem amigável.
  - Formatação fracionária limpa: `f"{result:.6f}".rstrip("0").rstrip(".")`.

### 4.5 Dataset e Métricas de Validação

```text
Total consolidado: 6.381 exemplos (silva_colab_dataset.jsonl)
Aderência ao schema: 100% nas 39 ferramentas e 44 parâmetros formais (0 erros no validador).
Suíte de testes automatizados: 41 testes unitários com 100% de aprovação (test_contracts, test_intent_fallback, test_parser_and_fallback, test_tools_and_memory, test_web_server).
```

### 4.6 Ciclo de Vida de Inicialização e Encerramento

1. `./start_silva.sh` verifica `.env`; se ausente, dispara `./install-silva.sh`.
2. Adquire wake-lock Android (`termux-wake-lock`) e encerra eventuais instâncias residuais em portas 5000 e 8080.
3. Sobe `llama-server` em background, aguarda `/health` por até 15s e grava seu PID em `android_agent/data/runtime.pids`.
4. Sobe `python3 main.py --web`, registra o PID do servidor web em `runtime.pids` e inicia o daemon `scheduler`.
5. `./stop-silva.sh` encerra os processos pelos PIDs salvos com `kill -TERM`, limpa resíduos de portas e libera o wake-lock com `termux-wake-unlock`.

## 5. Catálogo Completo de Rotas, Endpoints e Comandos

### 5.1 API HTTP

| Método + URL | Payload / Parâmetros | Ação e resposta |
|---|---|---|
| `GET /` | nenhum | 200 com `static/index.html`; 404 se ausente. |
| `GET /index.html` | nenhum | Mesmo arquivo da raiz. |
| `GET /captures/<filename>` | filename URL-decoded | 200 com arquivo; 404 ausente; 403 se `safe_path` não iniciar com `CAPTURES_DIR` ou se PIN for inválido. |
| `GET /api/health` | nenhum | 200 `{"status":"ok","agent":"Silva","llm":{"online":bool,"status":str,"url":str}}`. |
| `POST /api/chat` | body `{"message": string}`; header `X-Access-Pin` | 403 para PIN incorreto; 400 para JSON inválido; 200 com retorno de `execute_call()` propagando status real (`ok`, `partial_error`, `error`). |
| `OPTIONS *` | headers de preflight | 204; CORS `*`, métodos `GET, POST, OPTIONS`. |

### 5.2 Formato de Resposta do Parser (`/api/chat`)

```json
{
  "status": "ok | partial_error | error",
  "message": "string",
  "raw_call": "string",
  "func_name": "string | multi_call",
  "calls": [{"func_name": "string", "args": {}, "status": "ok | error", "data": null}],
  "data": [],
  "media_items": [{"type": "image | video", "url": "string"}],
  "image_url": null,
  "video_url": null,
  "latency_ms": 1.5
}
```

## 6. Arquitetura do Frontend / Interface de Usuário

### 6.1 Bootstrap e Estado Cliente

`static/index.html` (2.656 linhas) contém CSS e JavaScript inline, 100% offline (sem CDNs ou bibliotecas externas), adaptado para tema escuro roxo (`#5A189A` / `#7B1FA2`), servido pelo `ReusableThreadingHTTPServer`:

- **Modo de Voz Interativo "Segure para Falar":**
  - Alternância rápida entre Modo Texto e Modo Voz pelo botão de microfone no composer.
  - Barra tátil `#voice-hold-bar` com eventos `pointerdown`, `pointermove`, `pointerup` e `pointercancel`.
  - Captura de áudio nativa via Web Speech API (`webkitSpeechRecognition` / `SpeechRecognition`) com suporte ao ditado nativo do Android.
  - Canvas de ondas sonoras senoidais (`#voice-waves-canvas`) com gradiente roxo e interpolação harmônica suave.
  - Gesto mobile de cancelar deslizando para cima (`dragOffsetY < -60px`), acompanhado de transição visual para vermelho de alerta e cancelamento da requisição.
  - Feedback háptico via `navigator.vibrate([30])` ao iniciar, vibrar de sucesso ou duplo pulso no cancelamento.
- **Histórico Persistido:** Sessões salvas em `localStorage["silva_chats_v2"]` com sidebar retrátil.
- **Renderização Multimídia Segura:** Fotos, vídeos e mapas com appending de `?pin=...` automático via helper `withPin()`.
- **Cards de Busca Otimizados:** Renderização compacta de resultados de pesquisa com links Markdown clicáveis e botão para busca completa no Google.

## 7. Histórico de Melhorias Concluídas e Acoplamentos

### 7.1 Melhorias Recentes Concluídas

1. **Blindagem de Sockets e Idempotência de Boot:** `ReusableThreadingHTTPServer` com `SO_REUSEADDR` e fallback de portas (`5000` a `5005`).
2. **Normalização Matemática e de Linguagem Natural:** Parser numérico por extenso, operadores em linguagem natural e validação AST segura.
3. **Calibração Meteorológica e Resolução Geográfica:** Geocoding priorizando o Brasil e descarte de falsos positivos de chuva fraca.
4. **Redesign da Interface Web:** UI minimalista moderna, responsiva, com histórico persistente e temas escuros refinados.
5. **39 Ferramentas Nativas e Ecossistema Wi-Fi Completo:** Catálogo formal auditado com suporte a scan, conexão em 2 camadas, telemetria detalhada e liga/desliga.
6. **Busca Web Multi-Fonte em Cascata:** Wikipédia PT-BR, Google News RSS e DuckDuckGo Lite com extração limpa e links formatados em Markdown.
7. **Calculadora Científica Robusta via AST:** `SafeMathEvaluator` com 17 funções matemáticas, constantes e bloqueio contra overflow e injeções.
8. **Memória Persistente SQLite FTS5 ACID:** Busca BM25 com fallback LIKE, categorização semântica e migração sem perdas de arquivos legados.
9. **Daemon Scheduler no Boot:** Monitoramento de alarmes e compromissos em thread desacoplada com avisos de proximidade.
10. **Refatoração Modular do Pacote `android_agent/tools/`:** Decomposição do monolito em 8 submódulos coesos auditados via AST estático.
11. **Blindagem de Mídia com PIN e Anti-Traversal:** Proteção contra path traversal e validação de PIN em `/captures/*`.
12. **Pipeline de Treinamento no Colab (`colab_train_silva.py`):** Mascaramento manual de labels, token de parada explícito `<|im_end|>` e auditoria estatística.
13. **Suíte Completa de Testes Automatizados:** Suíte unificada de testes cobrindo contratos, AST, ferramentas, persistência e servidor web.
14. **Motor de Linguagem Natural com 4 Pilares (`android_agent/nlp/`):** Decomposição em `numbers.py`, `colloquial.py`, `router.py` e splitter de cláusulas.
15. **Blindagem de `scan_wifi()` contra Falhas do Android:** Tratamento de erros estruturados (`API_ERROR`) com GPS desativado no Android 10+.
16. **Deploy Automático e Sincronização via ADB:** Scripts operacionais com sincronização via wireless debugging.
17. **Guia Passo a Passo para Usuários:** Documentação com passo a passo para preparação e treino de modelos.
18. **Desambiguação Wi-Fi vs Memória:** Separação estrita entre busca de senhas salvas (`recall_note`), status de conexão (`get_wifi_info`) e varredura (`scan_wifi`).
19. **Busca Web com Links Compactos e Sanitização de Query:** Remoção de artigos iniciais (`o`, `a`, etc.) e eliminação de URLs brutas gigantes no texto da resposta.
20. **Auditoria Estática de Imports via AST:** Análise estática contra símbolos não declarados em todo o pacote `android_agent/tools/`.
21. **Modo de Voz Web Interativo "Segure para Falar":** Implementação 100% offline com Web Speech API, animação de ondas senoidais em canvas e gesto de arrastar para cima para cancelar.
22. **Blindagem Universal de Regex e Argumentos (`nlp/router.py`):** Função `_prepare_texts` normalizando quebras de linha (`\n`) sem perder maiúsculas ou símbolos técnicos, com suporte a próclises PT-BR (`"se conecte"`, `"me conecta"`).
23. **Padronização Operacional Plug & Play em 4 Scripts Raiz:**
    - `./install-silva.sh`: instalador completo e idempotente.
    - `./config-silva.sh`: assistente CLI interativo.
    - `./start_silva.sh`: inicializador unificado com auto-setup e tracking de PIDs.
    - `./stop-silva.sh`: encerramento seguro de instâncias por PID e varredura de processos órfãos.
24. **Gestão de Processos via PIDs (`android_agent/data/runtime.pids`):**
    - Rastreamento confiável de PIDs de segundo plano (`llama_pid` e `web_pid`), permitindo desligamento cirúrgico sem afetar outros processos do usuário.
25. **Clima por Localização Relativa com Fallback em 3 Níveis e Cache Persistente (`last_location.json`):**
    - Tratamento de termos relativos (`minha cidade`, `meu bairro`, `aqui`, etc.) para `location=''`.
    - Cadeia de 3 níveis em `get_weather`: dispositivo ativo (Nível 1) -> cache persistente `data/last_location.json` com aviso transparente de GPS desativado (Nível 2) -> orientação amigável (Nível 3).
    - Reverse geocoding resiliente (`_reverse_geocode_label`) via Nominatim OSM e BigDataCloud.
26. **Documentação Técnica Consolidada (`README.md`):**
    - Manual completo em português com arquitetura, ciclo de vida de processos, catálogo das 39 ferramentas, diagnósticos de falhas e guia de uso.
27. **Expansão da Suíte de Testes (41 Testes 100% Aprovados):**
    - Inclusão de testes unitários para a cadeia de 3 níveis de clima (`test_weather_three_level_fallback_chain`), consultas meteorológicas relativas (`test_relative_weather_queries`) e persistência de cache (`save_last_location`/`load_last_location`).
28. **Refinamento do Script de Sincronização Direta (`update_direct.sh`):**
    - Atualização para caminhos absolutos canônicos `/data/data/com.termux/files/home/silva-agent`, tratamento recursivo de subdiretórios acidentalmente aninhados no push do ADB e execução autônoma via Termux.

### 7.2 Pontos de Atenção e Acoplamentos Restantes

1. **HTTP em texto claro (Plaintext):** A comunicação na rede local ocorre sobre HTTP sem TLS (`0.0.0.0:5000`), protegida pelo PIN estático (`X-Access-Pin`).
2. **Snapshots de release binários legados:** Arquivos `silva_deploy.tar.gz` e `silva_update.tar.gz` são legados e devem ser atualizados quando houver nova versão empacotada.
3. **Dependência de permissões do Termux:API:** Chamadas nativas de hardware (Wi-Fi scan, GPS, SMS, câmera, áudio) exigem concessão prévia de permissões no Android.
