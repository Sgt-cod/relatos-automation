"""
call_modal_endpoint.py

Chama o endpoint HTTP publicado pela Modal (modal_avatar.py, função
generate_endpoint) para gerar o vídeo do avatar via GPU externa,
sem precisar do SDK da Modal instalado no runner do GitHub Actions
(só uma requisição HTTP simples).

Pressupõe que a imagem (assets/avatar.png) e o áudio (gerado no passo
anterior por generate_audio.py) já estejam acessíveis por URL pública
temporária. Aqui usamos um release do próprio repositório como storage
simples — dá pra trocar por outro esquema se preferir.
"""

import os
import base64
import requests

MODAL_ENDPOINT_URL = os.environ["MODAL_ENDPOINT_URL"]


def upload_to_github_release(local_path: str, asset_name: str) -> str:
    """
    Sobe um arquivo como asset de uma release "scratch" do repositório e
    devolve a URL pública de download. Forma simples de expor um arquivo
    por URL sem precisar de outro serviço de storage.
    Requer GITHUB_TOKEN com permissão de contents:write.
    """
    import subprocess
    repo = os.environ["GITHUB_REPOSITORY"]
    token = os.environ["GITHUB_TOKEN"]
    tag = "pipeline-scratch"

    # Garante que a release "scratch" existe (idempotente)
    subprocess.run(
        ["gh", "release", "create", tag, "--notes", "storage temporário do pipeline"],
        env={**os.environ, "GH_TOKEN": token},
        check=False,  # ignora erro se já existir
    )
    subprocess.run(
        ["gh", "release", "upload", tag, local_path, f"--clobber"],
        env={**os.environ, "GH_TOKEN": token},
        check=True,
    )
    return f"https://github.com/{repo}/releases/download/{tag}/{os.path.basename(local_path)}"


def generate_avatar_via_modal(image_path: str, audio_path: str, output_path: str) -> str:
    image_url = upload_to_github_release(image_path, "avatar.png")
    audio_url = upload_to_github_release(audio_path, "audio.wav")

    resp = requests.post(
        MODAL_ENDPOINT_URL,
        json={"image_url": image_url, "audio_url": audio_url},
        timeout=300,  # geração de vídeo pode levar alguns minutos
    )
    resp.raise_for_status()
    video_b64 = resp.json()["video_base64"]

    with open(output_path, "wb") as f:
        f.write(base64.b64decode(video_b64))

    return output_path


if __name__ == "__main__":
    generate_avatar_via_modal(
        image_path="assets/avatar.png",
        audio_path="test_audio.wav",
        output_path="output_avatar.mp4",
    )
    print("Vídeo do avatar gerado: output_avatar.mp4")
