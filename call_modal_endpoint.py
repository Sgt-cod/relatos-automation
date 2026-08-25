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

from github_storage import upload_to_github_release

MODAL_ENDPOINT_URL = os.environ["MODAL_ENDPOINT_URL"]


def generate_avatar_via_modal(image_path: str, audio_path: str, output_path: str) -> str:
    image_url = upload_to_github_release(image_path, "avatar_source.png")
    audio_url = upload_to_github_release(audio_path, "audio_source.wav")

    resp = requests.post(
        MODAL_ENDPOINT_URL,
        json={"image_url": image_url, "audio_url": audio_url},
        timeout=750,  # acima do timeout de 700s do endpoint na Modal
    )

    if resp.status_code != 200:
        try:
            error_data = resp.json()
            print("---- Erro retornado pela função Modal ----")
            print(f"Erro: {error_data.get('error')}")
            print("Traceback completo:")
            print(error_data.get("traceback", "(não disponível)"))
            print("-------------------------------------------")
        except ValueError:
            print(f"Resposta não-JSON da Modal (status {resp.status_code}): {resp.text[:2000]}")

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
