"""
github_storage.py

Helper compartilhado para expor arquivos por URL pública temporária,
usando releases do próprio repositório como storage — sem precisar de
outro serviço externo.

Usado por:
- call_modal_endpoint.py (sobe imagem/áudio para a Modal buscar)
- send_approval_request.py (sobe vídeo do avatar + thumbnail para o
  Telegram exibir, e para o Workflow B conseguir baixar depois)
- telegram_approval.py (sobe arquivos de substituição enviados pelo
  usuário no Telegram)

Cada arquivo é nomeado com prefixo do video_id para não colidir entre
execuções diferentes, mesmo todos vivendo na mesma release "scratch".
"""

import os
import subprocess

RELEASE_TAG = "pipeline-scratch"


def upload_to_github_release(local_path: str, asset_name: str) -> str:
    """
    Sobe um arquivo como asset da release "scratch" do repositório e
    devolve a URL pública de download.
    Requer GITHUB_TOKEN (env var) com permissão de contents:write, e o
    GitHub CLI (gh) disponível no runner (já vem instalado por padrão
    nos runners ubuntu-latest).
    """
    import shutil

    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]

    # Garante que a release "scratch" existe (idempotente — ignora erro
    # se já existir).
    subprocess.run(
        ["gh", "release", "create", RELEASE_TAG, "--notes", "storage temporário do pipeline"],
        env={**os.environ, "GH_TOKEN": token},
        check=False,
    )

    # gh release upload usa o nome do arquivo local como nome do asset;
    # para controlar o nome final do asset, copiamos para um arquivo
    # temporário já com o nome desejado antes de subir.
    tmp_named_path = os.path.join(os.path.dirname(local_path) or ".", asset_name)
    if os.path.abspath(tmp_named_path) != os.path.abspath(local_path):
        shutil.copyfile(local_path, tmp_named_path)

    subprocess.run(
        ["gh", "release", "upload", RELEASE_TAG, tmp_named_path, "--clobber"],
        env={**os.environ, "GH_TOKEN": token},
        check=True,
    )

    return f"https://github.com/{repo}/releases/download/{RELEASE_TAG}/{asset_name}"


def download_file(url: str, output_path: str) -> str:
    """Baixa um arquivo de uma URL pública para output_path."""
    import requests
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    with open(output_path, "wb") as f:
        f.write(resp.content)
    return output_path
