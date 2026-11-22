#!/usr/bin/env python3
"""
Entrypoint unificado do Silva:
Suporta modo Servidor Web LAN (--web) e modo Terminal Interativo (--cli).
"""

import argparse
import sys
import os

try:
    from config import WEB_HOST, WEB_PORT, ACCESS_PIN, LLAMA_SERVER_URL, SIMULATE_HARDWARE
    from llm_client import SilvaLLMClient
    from parser import execute_call
    import web_server
    import scheduler
except ImportError:
    from android_agent.config import WEB_HOST, WEB_PORT, ACCESS_PIN, LLAMA_SERVER_URL, SIMULATE_HARDWARE
    from android_agent.llm_client import SilvaLLMClient
    from android_agent.parser import execute_call
    from android_agent import web_server
    from android_agent import scheduler


def print_banner():
    banner = r"""
  ███████╗██╗██╗     ██╗   ██╗ █████╗ 
  ██╔════╝██║██║     ██║   ██║██╔══██╗
  ███████╗██║██║     ██║   ██║███████║
  ╚════██║██║██║     ╚██╗ ██╔╝██╔══██║
  ███████║██║███████╗ ╚████╔╝ ██║  ██║
  ╚══════╝╚═╝╚══════╝  ╚═══╝  ╚═╝  ╚═╝
  Micro-Agente Autônomo Offline para Android
    """
    print(banner)
    print(f" • LLM Local: {LLAMA_SERVER_URL}")
    print(f" • Simulação de Hardware: {'Ativa' if SIMULATE_HARDWARE else 'Desativada (Termux:API Nativo)'}")
    print(" • Agendador de Lembretes: Ativo em segundo plano (verificação a cada 30s)")
    print("-" * 55)


def run_cli_mode():
    scheduler.start_scheduler()
    print_banner()
    print("[*] Modo CLI interativo iniciado. Digite 'sair' ou Ctrl+C para encerrar.")
    print("[*] Dica: Você pode digitar perguntas normais ou chamadas diretas como <call>get_battery()</call>\n")

    client = SilvaLLMClient()
    health = client.check_health()
    if not health.get("online"):
        print(f"[AVISO] llama-server parece offline ({health.get('error', 'desconectado')}).")
        print("        Comandos normais precisarão do servidor, mas você pode testar chamadas diretas com <call>...</call>.\n")

    while True:
        try:
            user_input = input("Você > ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("sair", "exit", "quit"):
                print("\n[*] Encerrando Silva CLI. Até logo!")
                break

            if user_input.startswith("<call>") and user_input.endswith("</call>"):
                raw_call = user_input
                latency = 0.0
                err = None
            else:
                raw_call, latency, err = client.generate_call(user_input)

            if err:
                print(f"\n[Silva Erro]: {err}\n")
                continue

            result = execute_call(raw_call)

            print("\n-------------------------------------------------------")
            print(f"Silva: {result.get('message')}")
            if result.get("image_url"):
                print(f"Arquivo de imagem gerado: {result['image_url']}")
            print(f"[Roteamento]: {result.get('raw_call')} | {latency}ms")
            print("-------------------------------------------------------\n")

        except (KeyboardInterrupt, EOFError):
            print("\n[*] Encerrando Silva CLI...")
            break


def run_web_mode(host: str, port: int):
    print_banner()
    print(f"[*] Iniciando interface web local...")
    print(f"[*] Acesso Local: http://localhost:{port}")
    if ACCESS_PIN:
        print(f"[*] Proteção de Acesso PIN ativada: {ACCESS_PIN}")
    web_server.start_server(host=host, port=port)


def main():
    parser = argparse.ArgumentParser(description="Silva — Micro-Agente Autônomo Offline")
    parser.add_argument("--web", action="store_true", help="Inicia o servidor web com interface de chat")
    parser.add_argument("--cli", action="store_true", help="Inicia modo de linha de comando interativo")
    parser.add_argument("--host", type=str, default=WEB_HOST, help="Host para o servidor web")
    parser.add_argument("--port", type=int, default=WEB_PORT, help="Porta para o servidor web")

    args = parser.parse_args()

    if args.cli:
        run_cli_mode()
    else:
        # Default para modo web se nenhum ou --web for especificado
        run_web_mode(args.host, args.port)


if __name__ == "__main__":
    main()
