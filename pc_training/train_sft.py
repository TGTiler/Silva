#!/usr/bin/env python3
"""
Pipeline de Fine-Tuning SFT (Supervised Fine-Tuning) para o micro-modelo Silva.
Projetado para rodar com estabilidade em CPU (Intel Xeon Ivy Bridge FP32) ou DirectML (AMD Radeon RX 580).
Zero dependência de CUDA ou Unsloth.
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Carrega o System Prompt padronizado do agente
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT / "android_agent"))
try:
    from config import SILVA_SYSTEM_PROMPT
except ImportError:
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
        "search_google(query), request_ride(destination, app), order_food(query, app), install_app(app_name), media_control(action), list_capabilities(), none().\n"
        "Responda EXCLUSIVAMENTE com uma ou mais tags de chamada no formato:\n"
        "<call>nome_da_funcao(arg1=valor1, arg2=valor2)</call>\n"
        "Quando o usuário solicitar mais de uma ação na mesma frase, emita múltiplas tags em sequência (ex: <call>acao1()</call><call>acao2()</call>).\n"
        "Caso o comando não corresponda a nenhuma ferramenta ou seja uma conversa geral, responda apenas:\n"
        "<call>none()</call>\n"
        "NUNCA adicione saudações, introduções ou explicações fora da tag."
    )


def detect_device():
    """Detecta se há DirectML ou fallback para CPU."""
    try:
        import torch_directml
        if torch_directml.is_available():
            print("[*] Acelerador AMD DirectML detectado!")
            return torch_directml.device()
    except ImportError:
        pass

    import torch
    if torch.cuda.is_available():
        print("[*] Acelerador CUDA detectado!")
        return torch.device("cuda")

    print("[*] Executando em CPU FP32 (Compatibilidade Intel Xeon Ivy Bridge / AVX).")
    return torch.device("cpu")


def format_dataset_samples(jsonl_path: Path):
    """Carrega o dataset e formata em conversação ChatML para o micro-modelo."""
    from datasets import Dataset

    samples = []
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = json.loads(line)
            prompt = item["prompt"]
            completion = item["completion"]

            # Estrutura padrão de instrução ChatML
            text = (
                f"<|im_start|>system\n{SILVA_SYSTEM_PROMPT}<|im_end|>\n"
                f"<|im_start|>user\n{prompt}<|im_end|>\n"
                f"<|im_start|>assistant\n{completion}<|im_end|>"
            )
            samples.append({"text": text})

    return Dataset.from_list(samples)


def train(
    base_model_id: str = "HuggingFaceTB/SmolLM2-135M-Instruct",
    dataset_path: str = "../dataset/seed_examples.jsonl",
    output_dir: str = "./output_silva_lora",
    epochs: int = 5,
    batch_size: int = 2,
    learning_rate: float = 3e-4,
    use_lora: bool = True
):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer

    device = detect_device()
    dataset_file = Path(dataset_path).resolve()
    if not dataset_file.is_file():
        raise FileNotFoundError(f"Dataset não encontrado em: {dataset_file}")

    print(f"[*] Carregando tokenizer e modelo base: {base_model_id}")
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    print(f"[*] Carregando dataset: {dataset_file}")
    dataset = format_dataset_samples(dataset_file)
    print(f"[*] Total de exemplos formatados: {len(dataset)}")

    print(f"[*] Instanciando modelo base em float32 (CPU/DirectML safe)...")
    model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float32,
        trust_remote_code=True
    )

    if use_lora:
        print("[*] Configurando LoRA (Low-Rank Adaptation)...")
        peft_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=8,
            lora_alpha=16,
            lora_dropout=0.05,
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj"]
        )
        model = get_peft_model(model, peft_config)
        model.print_trainable_parameters()

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        gradient_accumulation_steps=2,
        learning_rate=learning_rate,
        weight_decay=0.01,
        warmup_ratio=0.1,
        logging_steps=5,
        save_strategy="epoch",
        fp16=False,
        bf16=False,
        use_cpu=(device.type == "cpu"),
        report_to="none"
    )

    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=256,
        tokenizer=tokenizer,
        args=training_args,
    )

    print("\n" + "=" * 55)
    print(" [AVISO] Fine-Tuning pronto para execução.")
    print(" Execute quando solicitado para iniciar o loop de treino.")
    print("=" * 55 + "\n")

    trainer.train()
    print(f"[*] Salvando modelo ajustado em: {output_dir}")
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print("[*] Treinamento concluído com sucesso!")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Silva Agent — Fine-Tuning SFT em CPU / DirectML")
    parser.add_argument("--model", type=str, default="HuggingFaceTB/SmolLM2-135M-Instruct")
    parser.add_argument("--dataset", type=str, default=str(PROJECT_ROOT / "dataset" / "seed_examples.jsonl"))
    parser.add_argument("--output", type=str, default="./output_silva_lora")
    parser.add_argument("--epochs", type=int, default=5)
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--no_lora", action="store_true", help="Desativa LoRA e treina modelo completo")

    args = parser.parse_args()

    # O script está pronto, mas conforme instrução não executa o treino agora
    print("[*] Script de treinamento train_sft.py configurado e pronto para a Fase 2.")
