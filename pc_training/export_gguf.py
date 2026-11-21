#!/usr/bin/env python3
"""
Pipeline de exportação do modelo Silva para GGUF e quantização móvel.
1. Fusão (merge) dos pesos LoRA com o modelo base (HuggingFaceTB/SmolLM2-135M-Instruct).
2. Conversão para GGUF (FP16).
3. Quantização para Q5_K_M (~105 MB, padrão de máxima precisão) ou Q4_K_M (~90 MB)
   gerando o arquivo final 'silva-135m.gguf' para inferência no Termux (ARM64).
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path


def merge_lora_weights(base_model_id: str, lora_adapter_path: Path, output_merged_dir: Path):
    """Funde adaptadores LoRA no modelo base gerando pesos completos."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    print(f"[*] Carregando modelo base: {base_model_id}")
    base_model = AutoModelForCausalLM.from_pretrained(
        base_model_id,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
        trust_remote_code=True
    )
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, trust_remote_code=True)

    print(f"[*] Aplicando adaptadores LoRA de: {lora_adapter_path}")
    lora_model = PeftModel.from_pretrained(base_model, str(lora_adapter_path))
    print("[*] Fundindo pesos (merge_and_unload)...")
    merged_model = lora_model.merge_and_unload()

    print(f"[*] Salvando modelo fundido em: {output_merged_dir}")
    merged_model.save_pretrained(str(output_merged_dir))
    tokenizer.save_pretrained(str(output_merged_dir))
    print("[*] Merge concluído com sucesso!")


def convert_to_gguf(merged_model_dir: Path, output_gguf_f16: Path, llama_cpp_dir: Path):
    """Executa script convert_hf_to_gguf.py do llama.cpp."""
    convert_script = llama_cpp_dir / "convert_hf_to_gguf.py"
    if not convert_script.is_file():
        # Tenta em formato legatário convert.py
        convert_script = llama_cpp_dir / "convert.py"

    if not convert_script.is_file():
        raise FileNotFoundError(
            f"Script de conversão não encontrado em {llama_cpp_dir}. "
            "Clone o llama.cpp com: git clone https://github.com/ggerganov/llama.cpp"
        )

    cmd = [
        sys.executable,
        str(convert_script),
        str(merged_model_dir),
        "--outfile", str(output_gguf_f16),
        "--outtype", "f16"
    ]
    print(f"[*] Convertendo modelo HF para GGUF FP16...")
    print(f"    Comando: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def quantize_gguf(llama_cpp_dir: Path, input_gguf: Path, output_gguf: Path, method: str = "q5_k_m"):
    """Quantiza o arquivo GGUF para o método especificado (Q5_K_M ou Q4_K_M)."""
    quantize_bin = llama_cpp_dir / "llama-quantize"
    if not quantize_bin.is_file():
        quantize_bin = llama_cpp_dir / "build" / "bin" / "llama-quantize"

    if not quantize_bin.is_file():
        # No Windows, verifica .exe
        quantize_bin = llama_cpp_dir / "build" / "bin" / "llama-quantize.exe"

    if not quantize_bin.is_file():
        print(f"[AVISO] Binário llama-quantize não encontrado em {llama_cpp_dir}.")
        print(f"        Você pode compilar o llama.cpp ou executar a quantização diretamente no Termux.")
        return False

    cmd = [str(quantize_bin), str(input_gguf), str(output_gguf), method.upper()]
    print(f"[*] Quantizando modelo para {method.upper()}...")
    print(f"    Comando: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    print(f"[OK] Modelo quantizado salvo em: {output_gguf}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Silva Agent — Exportação e Quantização GGUF")
    parser.add_argument("--base_model", type=str, default="HuggingFaceTB/SmolLM2-135M-Instruct")
    parser.add_argument("--adapter", type=str, default="./output_silva_lora")
    parser.add_argument("--merged_out", type=str, default="./silva_merged_hf")
    parser.add_argument("--llama_cpp", type=str, default="./llama.cpp")
    parser.add_argument("--output_dir", type=str, default="../android_agent/models")
    parser.add_argument("--method", type=str, default="q5_k_m", choices=["q5_k_m", "q4_k_m", "q8_0"], help="Método de quantização (padrão: q5_k_m ~105 MB)")
    parser.add_argument("--output_name", type=str, default="silva-135m.gguf", help="Nome do arquivo final GGUF")

    args = parser.parse_args()
    print(f"[*] Script de exportação export_gguf.py configurado: SmolLM2-135M -> {args.method.upper()} ({args.output_name})")
