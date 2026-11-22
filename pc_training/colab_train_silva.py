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

# 2. Clonar e compilar llama-quantize no llama.cpp
if not os.path.isdir("llama.cpp"):
    print("[*] Clonando repositório llama.cpp...")
    subprocess.run(["git", "clone", "--depth", "1", "https://github.com/ggerganov/llama.cpp.git"], check=True)

quantize_bin = "llama.cpp/build/bin/llama-quantize"
if not os.path.isfile(quantize_bin):
    print("[*] Compilando llama-quantize (CMake)...")
    subprocess.run(["cmake", "-B", "llama.cpp/build", "-S", "llama.cpp", "-DBUILD_SHARED_LIBS=OFF"], check=True)
    subprocess.run(["cmake", "--build", "llama.cpp/build", "--target", "llama-quantize", "-j4"], check=True)

print("[OK] Ambiente e ferramentas de compilação prontos!")

# %% [2] UPLOAD DO DATASET (silva_colab_dataset.jsonl)
print("\n" + "=" * 65)
print(" [2/5] CARREGAMENTO DO DATASET ")
print("=" * 65)

from google.colab import files

dataset_path = "silva_colab_dataset.jsonl"
if not os.path.isfile(dataset_path):
    print(">>> Clique em 'Choose Files' e selecione o arquivo 'silva_colab_dataset.jsonl':")
    uploaded = files.upload()
    for fname in uploaded.keys():
        if fname.endswith(".jsonl"):
            dataset_path = fname
            break
else:
    print(f"[*] Arquivo '{dataset_path}' já detectado no ambiente! Pulando upload.")

print(f"[OK] Dataset carregado: {dataset_path} ({os.path.getsize(dataset_path)} bytes)")

# %% [3] FINE-TUNING SFT RÁPIDO COM LORA NA GPU T4
print("\n" + "=" * 65)
print(" [3/5] INICIANDO FINE-TUNING SFT (SmolLM2-135M) ")
print("=" * 65)

import json
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

# System Prompt estrito idêntico ao runtime de produção do Silva no Android
SILVA_SYSTEM_PROMPT = (
    "Você é o Silva, um micro-agente offline para controle de smartphone Android.\n"
    "Sua única função é traduzir o pedido do usuário para chamadas de função estritas.\n"
    "Ferramentas disponíveis: get_battery(), get_last_sms(limit), send_sms(number, message), "
    "take_photo(camera_id), record_video(duration, camera_id), take_screenshot(), open_app(app_name), "
    "make_call(number), get_location(), get_last_location(), set_location_state(state=bool), "
    "get_weather(day, time, location), set_torch(state), set_dnd(state=bool), vibrate(duration_ms), "
    "get_clipboard(), set_clipboard(text), tell_joke(), set_alarm(time, label, days), cancel_alarm(time, day, label), "
    "schedule_event(title, date, time), remember_note(key, value), recall_note(query), get_notifications(app), "
    "set_volume(stream, level), set_brightness(level), set_timer(minutes, label), calculate(expression), "
    "search_google(query), request_ride(destination, app), order_food(query, app), install_app(app_name), media_control(action), none().\n"
    "Responda EXCLUSIVAMENTE com uma ou mais tags de chamada no formato:\n"
    "<call>nome_da_funcao(arg1=valor1, arg2=valor2)</call>\n"
    "Quando o usuário solicitar mais de uma ação na mesma frase, emita múltiplas tags em sequência (ex: <call>acao1()</call><call>acao2()</call>).\n"
    "Caso o comando não corresponda a nenhuma ferramenta ou seja uma conversa geral, responda apenas:\n"
    "<call>none()</call>\n"
    "NUNCA adicione saudações, introduções ou explicações fora da tag."
)

# Carrega e formata o dataset no padrão ChatML
raw_samples = []
with open(dataset_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        item = json.loads(line)
        prompt = item["prompt"]
        completion = item["completion"]

        # Formato de conversação ChatML
        text = (
            f"<|im_start|>system\n{SILVA_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{prompt}<|im_end|>\n"
            f"<|im_start|>assistant\n{completion}<|im_end|>"
        )
        raw_samples.append({"text": text})

dataset = Dataset.from_list(raw_samples)
print(f"[*] Total de exemplos formatados para treino: {len(dataset)}")

# Modelo base SmolLM2-135M
MODEL_ID = "HuggingFaceTB/SmolLM2-135M-Instruct"
print(f"[*] Baixando modelo base: {MODEL_ID}...")

tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

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

# Configuração LoRA otimizada para micro-modelos
peft_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM,
    r=16,
    lora_alpha=32,
    lora_dropout=0.05,
    target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]
)
model = get_peft_model(base_model, peft_config)
model.print_trainable_parameters()

import inspect

if HAS_SFT_CONFIG:
    sft_kwargs = {
        "output_dir": "./silva_checkpoints",
        "num_train_epochs": 3,
        "per_device_train_batch_size": 16,
        "gradient_accumulation_steps": 2,
        "learning_rate": 3e-4,
        "weight_decay": 0.01,
        "warmup_steps": 20,
        "logging_steps": 15,
        "save_strategy": "no",
        "fp16": (device == "cuda"),
        "bf16": False,
        "optim": "adamw_torch",
        "report_to": "none",
        "dataset_text_field": "text"
    }

    # TRL >= 0.20 usa 'max_length'; versões anteriores usavam 'max_seq_length'
    sft_sig = inspect.signature(SFTConfig.__init__).parameters
    if "max_length" in sft_sig:
        sft_kwargs["max_length"] = 256
    elif "max_seq_length" in sft_sig:
        sft_kwargs["max_seq_length"] = 256

    training_args = SFTConfig(**sft_kwargs)

    trainer_kwargs = {
        "model": model,
        "train_dataset": dataset,
        "args": training_args
    }
    trainer_sig = inspect.signature(SFTTrainer.__init__).parameters
    if "processing_class" in trainer_sig:
        trainer_kwargs["processing_class"] = tokenizer
    else:
        trainer_kwargs["tokenizer"] = tokenizer

    trainer = SFTTrainer(**trainer_kwargs)
else:
    training_args = TrainingArguments(
        output_dir="./silva_checkpoints",
        num_train_epochs=3,
        per_device_train_batch_size=16,
        gradient_accumulation_steps=2,
        learning_rate=3e-4,
        weight_decay=0.01,
        warmup_steps=20,
        logging_steps=15,
        save_strategy="no",
        fp16=(device == "cuda"),
        bf16=False,
        optim="adamw_torch",
        report_to="none"
    )
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=256,
        tokenizer=tokenizer,
        args=training_args
    )

print("[*] Iniciando treinamento por 3 épocas...")
start_time = time.time()
trainer.train()
print(f"[OK] Treinamento concluído em {round(time.time() - start_time, 1)} segundos!")

# Fusão dos pesos LoRA no modelo base
print("[*] Mesclando pesos LoRA (merge_and_unload)...")
merged_model = model.merge_and_unload()
merged_dir = "./silva_merged_hf"
merged_model.save_pretrained(merged_dir)
tokenizer.save_pretrained(merged_dir)
print(f"[OK] Modelo fundido salvo em: {merged_dir}")

# %% [4] TESTE RÁPIDO PÓS-TREINO (VALIDAÇÃO VISUAL)
print("\n" + "=" * 65)
print(" [4/5] TESTE RÁPIDO DE INFERÊNCIA PÓS-TREINO ")
print("=" * 65)

test_prompts = [
    "Silva, liga para a minha mãe",
    "Disca para 11987654321",
    "Coloca um alarme para amanhã às 07:00",
    "Silva, lembra que a chave reserva tá na gaveta",
    "Quanto é 250 dividido por 5?",
    "Coloca o celular no silencioso",
    "Silva, tira um print da tela",
    "Silva, pesquisa no google previsão do tempo em Paulista",
    "peça um uber para mim ir ao Shopping Recife",
    "silva pede uma pizza de calabresa no ifood pfv",
    "busca acai na 99",
    "baixa o aplicativo do whatsapp",
    "pausa a música agora",
    "pula para a próxima música",
    "Qual é a capital da França?",
    "Silva, ativa o não perturbe e coloca o brilho da tela em 20%"
]

merged_model.eval()
print(f"{'Prompt do Usuário':<55} | Saída do Silva")
print("-" * 105)

for p in test_prompts:
    prompt_input = (
        f"<|im_start|>system\n{SILVA_SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{p}<|im_end|>\n"
        f"<|im_start|>assistant\n<call>"
    )
    inputs = tokenizer(prompt_input, return_tensors="pt").to(merged_model.device)
    with torch.no_grad():
        outputs = merged_model.generate(
            **inputs,
            max_new_tokens=48,
            temperature=0.1,
            do_sample=False,
            eos_token_id=tokenizer.encode("<|im_end|>")[0],
            pad_token_id=tokenizer.eos_token_id
        )
    gen_text = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
    full_call = f"<call>{gen_text}" if not gen_text.startswith("<call>") else gen_text
    if "</call>" in full_call:
        full_call = full_call[:full_call.rfind("</call>") + 7]
    print(f"{p:<55} | {full_call}")

print("=" * 105)

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
