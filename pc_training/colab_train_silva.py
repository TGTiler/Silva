#!/usr/bin/env python3
"""
SILVA AGENT — SCRIPT AUTÔNOMO DE FINE-TUNING E EXPORTAÇÃO GGUF PARA GOOGLE COLAB
Modelo Alvo: HuggingFaceTB/SmolLM2-135M-Instruct
Ambiente de Execução: Google Colab (GPU T4 Gratuita)
Gera e faz download automático de: silva-135m.gguf (Q5_K_M ~105 MB)
"""

# %% [1] SETUP E INSTALAÇÃO DE DEPENDÊNCIAS
import os
import subprocess
import sys
import time

# Otimização anti-fragmentação de VRAM recomendada pelo PyTorch
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

print("=" * 65)
print(" [1/5] INSTALANDO BIBLIOTECAS E COMPILANDO FERRAMENTAS ")
print("=" * 65)

# 1. Remove versão incompatível/legada de torchao pré-instalada no Google Colab
print("[*] Removendo pacote conflitante torchao pré-instalado no Colab...")
subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchao"], check=False)

# Remove módulos em memória caso o kernel já esteja em execução
for mod in list(sys.modules.keys()):
    if "torchao" in mod:
        del sys.modules[mod]

# 2. Instalação de bibliotecas Hugging Face e utilitários
print("[*] Atualizando bibliotecas Hugging Face (transformers, peft, trl, accelerate)...")
subprocess.run([
    sys.executable, "-m", "pip", "install", "-q", "--upgrade",
    "transformers>=4.40.0",
    "datasets>=2.18.0",
    "peft>=0.10.0",
    "trl>=0.8.0",
    "accelerate>=0.28.0",
    "gguf>=0.6.0",
    "sentencepiece"
], check=True)

# 3. Clonar e compilar llama-quantize no llama.cpp
if not os.path.isdir("llama.cpp"):
    print("[*] Clonando repositório llama.cpp...")
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/ggerganov/llama.cpp.git"], check=True)

quantize_bin = "llama.cpp/build/bin/llama-quantize"
if not os.path.isfile(quantize_bin):
    print("[*] Compilando llama-quantize (CMake)...")
    subprocess.run(["cmake", "-B", "llama.cpp/build", "-S", "llama.cpp", "-DBUILD_SHARED_LIBS=OFF"], check=True)
    subprocess.run(["cmake", "--build", "llama.cpp/build", "--target", "llama-quantize", "-j4"], check=True)

print("[OK] Ambiente e ferramentas de compilação prontos!")

# %% [2] CARREGAMENTO DO DATASET E SPLIT DETERMINÍSTICO (95% TREINO / 5% AVALIAÇÃO)
print("\n" + "=" * 65)
print(" [2/5] CARREGAMENTO E DIVISÃO DO DATASET ")
print("=" * 65)

import json
import random

try:
    from google.colab import files
    HAS_COLAB_FILES = True
except ImportError:
    HAS_COLAB_FILES = False

train_clean_file = "train_clean.jsonl"
eval_clean_file = "eval_clean.jsonl"
consolidated_file = "silva_colab_dataset.jsonl"

train_raw = []
eval_raw = []

# Opção 1: Arquivos pré-divididos já existem no ambiente
if os.path.isfile(train_clean_file) and os.path.isfile(eval_clean_file):
    print(f"[*] Detectados arquivos pré-divididos no ambiente:")
    print(f"    - Treino: {train_clean_file}")
    print(f"    - Avaliação: {eval_clean_file}")
    with open(train_clean_file, "r", encoding="utf-8") as f:
        train_raw = [json.loads(line) for line in f if line.strip()]
    with open(eval_clean_file, "r", encoding="utf-8") as f:
        eval_raw = [json.loads(line) for line in f if line.strip()]
else:
    # Opção 2: Arquivo consolidado (upload ou já presente localmente)
    dataset_path = consolidated_file
    if not os.path.isfile(dataset_path):
        if HAS_COLAB_FILES:
            print(">>> Clique em 'Choose Files' e selecione o arquivo 'silva_colab_dataset.jsonl':")
            uploaded = files.upload()
            for fname in uploaded.keys():
                if fname.endswith(".jsonl"):
                    dataset_path = fname
                    break
        else:
            # Fallback para caminhos relativos no workspace
            for candidate in [
                "dataset/silva_colab_dataset.jsonl",
                "../dataset/silva_colab_dataset.jsonl",
                "silva-agent/dataset/silva_colab_dataset.jsonl"
            ]:
                if os.path.isfile(candidate):
                    dataset_path = candidate
                    break

    if not os.path.isfile(dataset_path):
        raise FileNotFoundError(f"Arquivo de dataset não encontrado: {dataset_path}")

    print(f"[*] Carregando dataset consolidado: {dataset_path} ({os.path.getsize(dataset_path)} bytes)")
    with open(dataset_path, "r", encoding="utf-8") as f:
        all_samples = [json.loads(line) for line in f if line.strip()]

    # Split determinístico 95% treino / 5% avaliação com seed=42
    random.seed(42)
    random.shuffle(all_samples)
    eval_count = max(1, int(len(all_samples) * 0.05))
    eval_raw = all_samples[:eval_count]
    train_raw = all_samples[eval_count:]
    print(f"[*] Split determinístico (seed=42): 95% Treino ({len(train_raw)}) | 5% Avaliação ({len(eval_raw)})")

# ==============================================================================
# ATENÇÃO: Esta constante deve permanecer 100% idêntica ao SILVA_SYSTEM_PROMPT
# definido em silva-agent/android_agent/config.py (sem placeholders abstratos).
# ==============================================================================
SILVA_SYSTEM_PROMPT = (
    "Silva, agente Android offline. Traduza pedidos em <call>tool(args)</call>.\n"
    "Tools: get_battery(), get_last_sms(limit), send_sms(number, message), "
    "take_photo(camera_id), record_video(duration, camera_id), take_screenshot(), open_app(app_name), make_call(number), get_location(), "
    "get_last_location(), set_location_state(state=bool), get_weather(day, time, location), "
    "set_torch(state), set_dnd(state=bool), vibrate(duration_ms), get_clipboard(), set_clipboard(text), "
    "tell_joke(), set_alarm(time, label, days), cancel_alarm(time, day, label), schedule_event(title, date, time), "
    "remember_note(key, value, ttl_hours), recall_note(query), forget_note(query), list_memories(category), remind_on_wifi(ssid, reminder), get_notifications(app), set_volume(stream, level), "
    "set_brightness(level), set_timer(minutes, label), calculate(expression), search_google(query, open_browser), "
    "request_ride(destination, app), order_food(query, app), install_app(app_name), media_control(action), "
    "scan_wifi(), connect_wifi(ssid, password), get_wifi_info(), set_wifi_state(state), "
    "get_datetime(), get_system_info(), read_screen(), save_contact(name, phone), get_contact(name), "
    "set_bluetooth_state(state), set_mobile_data_state(state), set_airplane_mode(state), set_hotspot_state(state), "
    "record_audio(duration), save_voice_note(title, duration, text_only), get_voice_notes(query), check_voice_note(query, note_id), convert_units(amount, from_unit, to_unit), send_whatsapp(contact_name, message), summarize_notifications(app_filter), "
    "navigate_to(destination, app), play_media(query, app), add_list_item(item, list_name), get_list(list_name), remove_list_item(item, list_name), list_capabilities(), none().\n"
    "Ex: <call>get_battery()</call> ou <call>none()</call> para conversa geral. Sem texto fora da tag."
)


# %% [3] FINE-TUNING COM MASCARAMENTO MANUAL DE LABELS E TOKEN DE PARADA EXPLÍCITO
print("\n" + "=" * 65)
print(" [3/5] INICIANDO FINE-TUNING COM MASCARAMENTO MANUAL DE LABELS ")
print("=" * 65)

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments,
    Trainer,
    DataCollatorForSeq2Seq
)
from peft import LoraConfig, get_peft_model, TaskType

# Modelo base SmolLM2-135M
MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
print(f"[*] Baixando tokenizer do modelo base: {MODEL_ID}...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)

# ==============================================================================
# 1. SEPARAR pad_token_id DE eos_token_id (CRÍTICO)
# SmolLM2 / Llama usa <|im_end|> como fim de turno no ChatML.
# O pad_token DEVE ser <|endoftext|> (id 0) para que o collator nunca mascare <|im_end|>.
# ==============================================================================
eos_id = tokenizer.convert_tokens_to_ids("<|im_end|>")
if eos_id is None or eos_id < 0:
    eos_id = tokenizer.eos_token_id

tokenizer.eos_token = "<|im_end|>"
tokenizer.eos_token_id = eos_id

tokenizer.pad_token = "<|endoftext|>"
pad_id = tokenizer.convert_tokens_to_ids("<|endoftext|>")
if pad_id is None or pad_id < 0:
    pad_id = 0
tokenizer.pad_token_id = pad_id

print(f"[*] Configuração dos tokens especiais:")
print(f"  - eos_token: '{tokenizer.eos_token}' (ID: {tokenizer.eos_token_id})")
print(f"  - pad_token: '{tokenizer.pad_token}' (ID: {tokenizer.pad_token_id})")
assert tokenizer.eos_token_id != tokenizer.pad_token_id, "pad_token_id e eos_token_id devem ser estritamente distintos!"

# ==============================================================================
# 2. TOKENIZAÇÃO MANUAL COM labels = -100 NO PROMPT (SEM DEPENDER DE completion_only_loss)
# ==============================================================================
print("\n[*] Construindo datasets com mascaramento manual de labels (-100 no prompt)...")
MAX_TRAIN_LENGTH = 1024

def tokenize_chatml_example(item):
    """
    Constrói cada exemplo manualmente em duas partes:
    - Parte 1 (Prompt mascarado): System Prompt + Pergunta do usuário com generation prompt (labels = -100)
    - Parte 2 (Resposta treinável): Resposta <call>...</call> com token de parada explícito <|im_end|>
    Garante que a completion NUNCA seja truncada se a sequência total atingir MAX_TRAIN_LENGTH.
    """
    prompt_str = tokenizer.apply_chat_template(
        [
            {"role": "system", "content": SILVA_SYSTEM_PROMPT},
            {"role": "user", "content": item["prompt"]},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )
    prompt_ids = tokenizer.encode(prompt_str, add_special_tokens=False)
    completion_ids = tokenizer.encode(item["completion"].strip(), add_special_tokens=False) + [eos_id]

    total_len = len(prompt_ids) + len(completion_ids)
    if total_len > MAX_TRAIN_LENGTH:
        # Se ultrapassar a janela máxima, preserva 100% da completion e trunca o início do prompt
        max_prompt_len = max(0, MAX_TRAIN_LENGTH - len(completion_ids))
        prompt_ids = prompt_ids[-max_prompt_len:]

    input_ids = prompt_ids + completion_ids
    labels = [-100] * len(prompt_ids) + completion_ids
    attention_mask = [1] * len(input_ids)

    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels
    }

train_samples = [tokenize_chatml_example(x) for x in train_raw]
eval_samples = [tokenize_chatml_example(x) for x in eval_raw]

train_dataset = Dataset.from_list(train_samples)
eval_dataset = Dataset.from_list(eval_samples)
print(f"[*] Total de exemplos tokenizados para treino: {len(train_dataset)}")
print(f"[*] Total de exemplos tokenizados para avaliação: {len(eval_dataset)}")

# ==============================================================================
# AUDITORIA PRÉ-TREINO DE COMPRIMENTO DE TOKENS (JANELA: 1024 TOKENS)
# ==============================================================================
print("\n[*] Executando auditoria pré-treino de comprimento de tokens...")
all_formatted_samples = train_samples + eval_samples
token_lengths = [len(s["input_ids"]) for s in all_formatted_samples]

total_count = len(token_lengths)
mean_len = sum(token_lengths) / total_count if total_count > 0 else 0
sorted_lens = sorted(token_lengths)
p99_idx = min(int(0.99 * total_count), total_count - 1)
p99_len = sorted_lens[p99_idx]
max_tokens_found = max(token_lengths) if token_lengths else 0
truncated_samples = [(i, l) for i, l in enumerate(token_lengths) if l >= MAX_TRAIN_LENGTH]

print(f"[*] Estatísticas de Comprimento de Tokens:")
print(f"  - Total de amostras auditadas: {total_count}")
print(f"  - Média de tokens por amostra: {mean_len:.1f}")
print(f"  - Percentil 99 (P99): {p99_len} tokens")
print(f"  - Tamanho máximo encontrado: {max_tokens_found} tokens (janela: {MAX_TRAIN_LENGTH})")

if truncated_samples:
    print(f"\n[ALERTA DE TRUNCAMENTO] {len(truncated_samples)} amostra(s) ({len(truncated_samples) / total_count * 100:.2f}%) atingiram a janela de {MAX_TRAIN_LENGTH} tokens!")
else:
    print(f"[OK] 100% das {total_count} amostras cabem com folga dentro da janela de {MAX_TRAIN_LENGTH} tokens! Zero truncamento.\n")

device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if torch.cuda.is_available() else torch.float32

import gc
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()

print(f"[*] Carregando pesos do modelo base ({device})...")
try:
    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        dtype=dtype,
        device_map="auto" if device == "cuda" else None,
        trust_remote_code=True
    )
except TypeError:
    base_model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=dtype,
        device_map="auto" if device == "cuda" else None,
        trust_remote_code=True
    )

# Desativa use_cache para compatibilidade com gradient checkpointing
if hasattr(base_model.config, "use_cache"):
    base_model.config.use_cache = False

# Configuração LoRA calibrada para micro-modelos com 4 épocas (dropout 0.08)
peft_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.08,
    bias="none",
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
)
model = get_peft_model(base_model, peft_config)
model.print_trainable_parameters()

# ==============================================================================
# CONFIGURAÇÃO DO TRAINER COM DataCollatorForSeq2Seq E CONTROLE ESTREITO DE VRAM
# ==============================================================================
import inspect

t_sig = inspect.signature(TrainingArguments.__init__).parameters
t_kwargs = {
    "output_dir": "./silva_checkpoints",
    "num_train_epochs": 4,
    "per_device_train_batch_size": 4,
    "per_device_eval_batch_size": 4,
    "gradient_accumulation_steps": 8,
    "learning_rate": 3e-4,
    "lr_scheduler_type": "cosine",
    "weight_decay": 0.01,
    "logging_steps": 25,
    "save_strategy": "epoch",
    "save_total_limit": 2,
    "metric_for_best_model": "eval_loss",
    "greater_is_better": False,
    "load_best_model_at_end": True,
    "fp16": (device == "cuda"),
    "bf16": False,
    "optim": "adamw_torch",
    "report_to": "none",
    "dataloader_pin_memory": False
}

# Ativa Gradient Checkpointing para reduzir drasticamente o consumo de VRAM
if "gradient_checkpointing" in t_sig:
    t_kwargs["gradient_checkpointing"] = True
if "gradient_checkpointing_kwargs" in t_sig:
    t_kwargs["gradient_checkpointing_kwargs"] = {"use_reentrant": False}

if "eval_accumulation_steps" in t_sig:
    t_kwargs["eval_accumulation_steps"] = 2

if "eval_strategy" in t_sig:
    t_kwargs["eval_strategy"] = "epoch"
elif "evaluation_strategy" in t_sig:
    t_kwargs["evaluation_strategy"] = "epoch"

if "warmup_ratio" in t_sig:
    t_kwargs["warmup_ratio"] = 0.05
else:
    t_kwargs["warmup_steps"] = 25

training_args = TrainingArguments(**t_kwargs)

data_collator = DataCollatorForSeq2Seq(
    tokenizer=tokenizer,
    padding=True,
    label_pad_token_id=-100
)

trainer_kwargs = {
    "model": model,
    "args": training_args,
    "train_dataset": train_dataset,
    "eval_dataset": eval_dataset,
    "data_collator": data_collator,
}
trainer_sig = inspect.signature(Trainer.__init__).parameters
if "processing_class" in trainer_sig:
    trainer_kwargs["processing_class"] = tokenizer
else:
    trainer_kwargs["tokenizer"] = tokenizer

trainer = Trainer(**trainer_kwargs)

# ==============================================================================
# 3. AUDITORIA VISUAL OBRIGATÓRIA ANTES DE INICIAR O TREINO
# ==============================================================================
print("\n" + "=" * 65)
print(" AUDITORIA VISUAL OBRIGATÓRIA DE LABELS (LABELS -100 vs COMPLETION) ")
print("=" * 65)

first_item = train_dataset[0]
lbls = first_item["labels"]
in_ids = first_item["input_ids"]

masked_count = sum(1 for x in lbls if x == -100)
unmasked_count = sum(1 for x in lbls if x != -100)
active_tokens = [tid for tid in lbls if tid != -100]

decoded_target = tokenizer.decode(active_tokens, skip_special_tokens=False).strip()

print(f"[*] Total de tokens do primeiro exemplo: {len(lbls)}")
print(f"[*] Tokens mascarados (-100, prompt de sistema + usuário): {masked_count}")
print(f"[*] Tokens sob cálculo de perda (completion + eos): {unmasked_count}")
print(f"[*] Trecho sob cálculo de gradiente decodificado:\n    {repr(decoded_target)}")

# Validações estritas por assertion antes de iniciar o treinamento
assert unmasked_count > 0, (
    f"ERRO CRÍTICO: Nenhum token ativo encontrado nas labels (unmasked_count = 0)! "
    f"O prompt_ids excedeu MAX_TRAIN_LENGTH ({MAX_TRAIN_LENGTH})."
)
assert decoded_target.startswith("<call>"), (
    f"ERRO CRÍTICO: Labels ativas devem começar exatamente com '<call>', mas obtido: {repr(decoded_target[:30])}"
)
assert decoded_target.endswith("<|im_end|>"), (
    f"ERRO CRÍTICO: Labels ativas devem terminar com o token de parada '<|im_end|>', mas obtido: {repr(decoded_target[-20:])}"
)
assert "Você é o Silva" not in decoded_target, (
    "ERRO CRÍTICO: Vazamento de tokens do System Prompt para as labels ativas de treino!"
)
assert train_raw[0]["prompt"] not in decoded_target, (
    "ERRO CRÍTICO: Pergunta do usuário vazou para as labels ativas de treino!"
)
assert tokenizer.pad_token_id != tokenizer.eos_token_id, (
    "ERRO CRÍTICO: pad_token_id deve ser estritamente diferente de eos_token_id!"
)

print("\n[ASSERTION PASS] Auditoria confirmada com sucesso!")
print(" -> Perda será calculada EXCLUSIVAMENTE nos tokens da resposta <call>...</call><|im_end|>.")
print(" -> System prompt e pergunta do usuário 100% mascarados (-100).")
print(" -> Token de parada <|im_end|> devidamente incluído para evitar geração infinita.")
print("=" * 65 + "\n")

# Libera cache CUDA antes de iniciar o loop de treino
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()

print("[*] Iniciando treinamento calibrado por 4 épocas com avaliação e checkpoint seguro...")
start_time = time.time()
trainer.train()
print(f"[OK] Treinamento concluído em {round(time.time() - start_time, 1)} segundos!")

# Auditoria do melhor checkpoint selecionado (load_best_model_at_end=True)
print("\n" + "=" * 65)
print(" AUDITORIA DO MELHOR CHECKPOINT (ANTI-OVERFITTING) ")
print("=" * 65)
best_metric = getattr(trainer.state, "best_metric", None)
best_checkpoint = getattr(trainer.state, "best_model_checkpoint", None)
print(f"[*] Menor eval_loss obtido (best_metric): {best_metric}")
print(f"[*] Checkpoint selecionado para exportação (best_model_checkpoint): {best_checkpoint}")
print("=" * 65 + "\n")

# Fusão dos pesos LoRA no modelo base
print("[*] Mesclando pesos LoRA (merge_and_unload)...")
merged_model = model.merge_and_unload()

# Libera memória dos modelos intermediários para a inferência e conversão
del model
del base_model
gc.collect()
if torch.cuda.is_available():
    torch.cuda.empty_cache()

merged_dir = "./silva_merged_hf"
merged_model.save_pretrained(merged_dir)
tokenizer.save_pretrained(merged_dir)
print(f"[OK] Modelo fundido salvo em: {merged_dir}")

# %% [4] TESTE RÁPIDO DE INFERÊNCIA PÓS-TREINO (10 CENÁRIOS ESSENCIAIS)
print("\n" + "=" * 65)
print(" [4/5] TESTE RÁPIDO DE INFERÊNCIA PÓS-TREINO ")
print("=" * 65)

test_scenarios = [
    ("silva quanto ta a bateria agr?", "get_battery()"),
    ("quais wifis tem disponiveis aqui perto?", "scan_wifi()"),
    ("conecta no wifi Casa_5G senha 1234565", "connect_wifi(ssid='Casa_5G', password='1234565')"),
    ("qual rede wifi estou conectado agr?", "get_wifi_info()"),
    ("desativa o wifi do celular", "set_wifi_state(state=False)"),
    ("chama um uber p/ o shopping recife", "request_ride(destination='shopping recife', app='uber')"),
    ("pede um hamburguer no ifood pfv", "order_food(query='hamburguer', app='ifood')"),
    ("baixa o telegram na play store", "install_app(app_name='telegram')"),
    ("pausa a musica q ta tocando", "media_control(action='pause')"),
    ("como vai ficar o clima de paulista, pernambuco amn?", "get_weather(day='amanhã', time='', location='Paulista, Pernambuco')"),
    ("quanto e a raiz quadrada de 144?", "calculate(expression='sqrt(144)')"),
    ("guarda q a senha do wifi e Silva2026", "remember_note(...)"),
    ("oi silva tudo bem com vc?", "none()")
]

merged_model.eval()
print(f"{'Prompt do Usuário':<50} | {'Saída Gerada':<45} | Esperado")
print("-" * 125)

for prompt, expected in test_scenarios:
    messages = [
        {"role": "system", "content": SILVA_SYSTEM_PROMPT},
        {"role": "user", "content": prompt}
    ]
    prompt_input = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True
    )
    inputs = tokenizer(prompt_input, return_tensors="pt").to(merged_model.device)
    with torch.no_grad():
        outputs = merged_model.generate(
            **inputs,
            max_new_tokens=48,
            temperature=0.0,
            do_sample=False,
            eos_token_id=eos_id,
            pad_token_id=tokenizer.pad_token_id
        )
    raw_gen = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=False).strip()

    # Corta a saída gerada no primeiro <|im_end|> ou </call>
    gen_clean = raw_gen
    if "<|im_end|>" in gen_clean:
        gen_clean = gen_clean[:gen_clean.find("<|im_end|>")].strip()
    if "</call>" in gen_clean:
        gen_clean = gen_clean[:gen_clean.find("</call>") + 7].strip()

    gen_clean = gen_clean.replace("<|endoftext|>", "").strip()
    full_call = f"<call>{gen_clean}" if not gen_clean.startswith("<call>") else gen_clean
    print(f"{prompt:<50} | {full_call:<45} | {expected}")

print("=" * 125)

# %% [5] CONVERSÃO GGUF, QUANTIZAÇÃO Q5_K_M E DOWNLOAD AUTOMÁTICO
print("\n" + "=" * 65)
print(" [5/5] CONVERSÃO PARA GGUF E DOWNLOAD AUTOMÁTICO ")
print("=" * 65)

f16_gguf = "./silva-135m-f16.gguf"
final_gguf = "./silva-135m.gguf"

# 1. Conversão HF -> GGUF FP16
print("[*] Convertendo modelo Hugging Face para GGUF F16...")
convert_script = "llama.cpp/convert_hf_to_gguf.py"
if not os.path.isfile(convert_script) and os.path.isfile("llama.cpp/convert.py"):
    convert_script = "llama.cpp/convert.py"
subprocess.run([sys.executable, convert_script, merged_dir, "--outfile", f16_gguf, "--outtype", "f16"], check=True)

# 2. Quantização para Q5_K_M
print("[*] Quantizando para Q5_K_M (máxima precisão ~105 MB)...")
subprocess.run([quantize_bin, f16_gguf, final_gguf, "Q5_K_M"], check=True)

size_mb = os.path.getsize(final_gguf) / (1024 * 1024)
print(f"[OK] Modelo quantizado gerado: {final_gguf} ({size_mb:.2f} MB)")

# Remove arquivo temporário F16 para poupar espaço
if os.path.isfile(f16_gguf):
    os.remove(f16_gguf)

# 3. Disparo do download automático no navegador
print("\n[*] Disparando download do silva-135m.gguf no seu navegador...")
try:
    files.download(final_gguf)
    print("=================================================================")
    print(" [SUCESSO TOTAL] O modelo silva-135m.gguf foi baixado!")
    print(" Próximo passo: Copie o arquivo para o seu celular Android em:")
    print("   silva-agent/android_agent/models/silva-135m.gguf")
    print(" E execute: ./start_silva.sh")
    print("=================================================================")
except Exception as e:
    print(f"[!] Não foi possível acionar o download automático: {e}")
    print(f"    Você pode baixar manualmente o arquivo na aba lateral de arquivos do Colab: {final_gguf}")
