### Passo a passo para fazer você mesmo

Abra o seu terminal na pasta do projeto e siga os passos abaixo:

#### 1. Entrar na pasta do dataset
```bash
cd /home/fernanda/Downloads/Silva/silva-agent/dataset
```
*(ou se você estiver na pasta raiz `silva-agent`, basta usar os caminhos relativos)*.

#### 2. Gerar o dataset do Colab (O comando principal)
Execute o script preparador:
```bash
python3 prepare_final_dataset.py
```

**O que esse comando faz automaticamente por você:**
1. Lê o seu [`train.jsonl`](file:///home/fernanda/Downloads/Silva/silva-agent/dataset/train.jsonl) e o [`seed_examples.jsonl`](file:///home/fernanda/Downloads/Silva/silva-agent/dataset/seed_examples.jsonl).
2. Valida todas as chamadas contra o [`schema.json`](file:///home/fernanda/Downloads/Silva/silva-agent/dataset/schema.json).
3. Adiciona os contatos com nomes em português (`"Mãe"`, `"Aline"`, etc.).
4. Remove frases duplicadas.
5. Gera automaticamente:
   - [`silva_colab_dataset.jsonl`](file:///home/fernanda/Downloads/Silva/silva-agent/dataset/silva_colab_dataset.jsonl) (100% dos dados para o Google Colab).
   - [`train_clean.jsonl`](file:///home/fernanda/Downloads/Silva/silva-agent/dataset/train_clean.jsonl) (95% para treino local).
   - [`eval_clean.jsonl`](file:///home/fernanda/Downloads/Silva/silva-agent/dataset/eval_clean.jsonl) (5% para teste).


#### 3. (Opcional) Validar se o arquivo gerado está 100% íntegro
Se quiser conferir se não há nenhum erro de sintaxe antes de subir para o Colab, rode:
```bash
python3 validate_dataset.py silva_colab_dataset.jsonl schema.json
```
Se tudo estiver certo, ele imprimirá no final:
```text
[SUCESSO] Todos os exemplos estão sintaticamente válidos e em conformidade com o schema!
```

---

### Dica para o futuro:
Sempre que você quiser **adicionar novos exemplos de comandos e respostas**, basta abrir o [`train.jsonl`](file:///home/fernanda/Downloads/Silva/silva-agent/dataset/train.jsonl), adicionar suas linhas no final e rodar novamente:
```bash
python3 prepare_final_dataset.py
```
O arquivo `silva_colab_dataset.jsonl` será recriado atualizado na hora para você levar ao Google Colab.
