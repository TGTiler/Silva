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
# definido em silva-agent/android_agent/config.py.
# ==============================================================================
SILVA_SYSTEM_PROMPT = (
    "Você é o Silva, um micro-agente offline para controle de smartphone Android.\n"
    "Sua única função é traduzir o pedido do usuário para chamadas de função estritas.\n"
    "Ferramentas disponíveis: get_battery(), get_last_sms(limit), send_sms(number, message), "
    "take_photo(camera_id), record_video(duration, camera_id), take_screenshot(), open_app(app_name), make_call(number), get_location(), "
    "get_last_location(), set_location_state(state=bool), get_weather(day, time, location), "
    "set_torch(state), set_dnd(state=bool), vibrate(duration_ms), get_clipboard(), set_clipboard(text), "
    "tell_joke(), set_alarm(time, label, days), cancel_alarm(time, day, label), schedule_event(title, date, time), "
    "remember_note(key, value), recall_note(query), get_notifications(app), set_volume(stream, level), "
    "set_brightness(level), set_timer(minutes, label), calculate(expression), search_google(query, open_browser), "
    "request_ride(destination, app), order_food(query, app), install_app(app_name), media_control(action), "
    "scan_wifi(), list_capabilities(), none().\n"
    "Responda EXCLUSIVAMENTE com uma ou mais tags de chamada no formato:\n"
    "<call>nome_da_funcao(arg1=valor1, arg2=valor2)</call>\n"
    "Quando o usuário solicitar mais de uma ação na mesma frase, emita múltiplas tags em sequência (ex: <call>acao1()</call><call>acao2()</call>).\n"
    "Caso o comando não corresponda a nenhuma ferramenta ou seja uma conversa geral, responda apenas:\n"
    "<call>none()</call>\n"
    "NUNCA adicione saudações, introduções ou explicações fora da tag."
)


def format_chatml(item):
    prompt = item["prompt"]
    completion = item["completion"]
    text = (
        f"<|im_start|>system\n{SILVA_SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n{completion}<|im_end|>"
    )
    return {"text": text}


train_samples = [format_chatml(x) for x in train_raw]
eval_samples = [format_chatml(x) for x in eval_raw]

# %% [3] FINE-TUNING SFT COM LORA NA GPU T4 (CALIBRADO PARA 4 ÉPOCAS)
print("\n" + "=" * 65)
print(" [3/5] INICIANDO FINE-TUNING SFT (SmolLM2-135M) ")
print("=" * 65)

import torch
from datasets import Dataset
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    TrainingArguments
)
from peft import LoraConfig, get_peft_model, TaskType

# Suporte compatível tanto para versões novas de TRL (SFTConfig) quanto legadas
try:
    from trl import SFTTrainer, SFTConfig
    HAS_SFT_CONFIG = True
except ImportError:
    from trl import SFTTrainer
    HAS_SFT_CONFIG = False

train_dataset = Dataset.from_list(train_samples)
eval_dataset = Dataset.from_list(eval_samples)
print(f"[*] Total de exemplos formatados para treino: {len(train_dataset)}")
print(f"[*] Total de exemplos formatados para avaliação: {len(eval_dataset)}")

# Modelo base SmolLM2-135M
MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
print(f"[*] Baixando modelo base: {MODEL_ID}...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

# ==============================================================================
# AUDITORIA PRÉ-TREINO DE COMPRIMENTO DE TOKENS (JANELA: 512 TOKENS)
# ==============================================================================
print("\n[*] Executando auditoria pré-treino de tokens...")
MAX_TRAIN_LENGTH = 512

all_formatted_samples = train_samples + eval_samples
token_lengths = [
    len(tokenizer(s["text"], truncation=False)["input_ids"])
    for s in all_formatted_samples
]

total_count = len(token_lengths)
mean_len = sum(token_lengths) / total_count if total_count > 0 else 0
sorted_lens = sorted(token_lengths)
p99_idx = min(int(0.99 * total_count), total_count - 1)
p99_len = sorted_lens[p99_idx]
max_tokens_found = max(token_lengths) if token_lengths else 0
truncated_samples = [(i, l) for i, l in enumerate(token_lengths) if l > MAX_TRAIN_LENGTH]

print(f"[*] Estatísticas de Comprimento de Tokens:")
print(f"  - Total de amostras auditadas: {total_count}")
print(f"  - Média de tokens por amostra: {mean_len:.1f}")
print(f"  - Percentil 99 (P99): {p99_len} tokens")
print(f"  - Tamanho máximo encontrado (max_tokens): {max_tokens_found} tokens (janela: {MAX_TRAIN_LENGTH})")

if truncated_samples:
    print(f"\n[ALERTA DE TRUNCAMENTO] {len(truncated_samples)} amostra(s) ({len(truncated_samples) / total_count * 100:.2f}%) ultrapassam o limite de {MAX_TRAIN_LENGTH} tokens e serão truncadas pelo SFTTrainer!")
    for idx, tok_len in truncated_samples[:5]:
        sample_preview = all_formatted_samples[idx]["text"][:120].replace("\n", " ")
        print(f"    - Amostra #{idx}: {tok_len} tokens -> {sample_preview}...")
else:
    print(f"[OK] 100% das {total_count} amostras cabem com folga dentro da janela de {MAX_TRAIN_LENGTH} tokens! Zero truncamento.\n")

device = "cuda" if torch.cuda.is_available() else "cpu"
dtype = torch.float16 if torch.cuda.is_available() else torch.float32

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

import inspect

if HAS_SFT_CONFIG:
    sft_sig = inspect.signature(SFTConfig.__init__).parameters

    sft_kwargs = {
        "output_dir": "./silva_checkpoints",
        "num_train_epochs": 4,
        "per_device_train_batch_size": 16,
        "per_device_eval_batch_size": 16,
        "gradient_accumulation_steps": 2,
        "learning_rate": 2.5e-4,
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
        "dataset_text_field": "text"
    }

    # Compatibilidade eval_strategy vs evaluation_strategy
    if "eval_strategy" in sft_sig:
        sft_kwargs["eval_strategy"] = "epoch"
    elif "evaluation_strategy" in sft_sig:
        sft_kwargs["evaluation_strategy"] = "epoch"

    # Compatibilidade warmup_ratio vs warmup_steps
    if "warmup_ratio" in sft_sig:
        sft_kwargs["warmup_ratio"] = 0.05
    else:
        sft_kwargs["warmup_steps"] = 25

    # TRL >= 0.20 usa 'max_length'; versões anteriores usavam 'max_seq_length'
    if "max_length" in sft_sig:
        sft_kwargs["max_length"] = 512
    elif "max_seq_length" in sft_sig:
        sft_kwargs["max_seq_length"] = 512

    training_args = SFTConfig(**sft_kwargs)

    trainer_kwargs = {
        "model": model,
        "train_dataset": train_dataset,
        "eval_dataset": eval_dataset,
        "args": training_args
    }
    trainer_sig = inspect.signature(SFTTrainer.__init__).parameters
    if "processing_class" in trainer_sig:
        trainer_kwargs["processing_class"] = tokenizer
    else:
        trainer_kwargs["tokenizer"] = tokenizer

    trainer = SFTTrainer(**trainer_kwargs)
else:
    t_sig = inspect.signature(TrainingArguments.__init__).parameters
    t_kwargs = {
        "output_dir": "./silva_checkpoints",
        "num_train_epochs": 4,
        "per_device_train_batch_size": 16,
        "per_device_eval_batch_size": 16,
        "gradient_accumulation_steps": 2,
        "learning_rate": 2.5e-4,
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
        "report_to": "none"
    }
    if "eval_strategy" in t_sig:
        t_kwargs["eval_strategy"] = "epoch"
    elif "evaluation_strategy" in t_sig:
        t_kwargs["evaluation_strategy"] = "epoch"

    if "warmup_ratio" in t_sig:
        t_kwargs["warmup_ratio"] = 0.05
    else:
        t_kwargs["warmup_steps"] = 25

    training_args = TrainingArguments(**t_kwargs)

    trainer = SFTTrainer(
        model=model,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        dataset_text_field="text",
        max_seq_length=512,
        tokenizer=tokenizer,
        args=training_args
    )

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
    prompt_input = (
        f"<|im_start|>system\n{SILVA_SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{prompt}<|im_end|>\n"
        f"<|im_start|>assistant\n<call>"
    )
    inputs = tokenizer(prompt_input, return_tensors="pt").to(merged_model.device)
    with torch.no_grad():
        outputs = merged_model.generate(
            **inputs,
            max_new_tokens=48,
            temperature=0.0,
            do_sample=False,
            eos_token_id=tokenizer.encode("<|im_end|>")[0],
            pad_token_id=tokenizer.eos_token_id
        )
    gen_text = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    full_call = f"<call>{gen_text}" if not gen_text.startswith("<call>") else gen_text
    if "</call>" in full_call:
        full_call = full_call[:full_call.rfind("</call>") + 7]
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
