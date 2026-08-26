"""
call_modal_endpoint.py

Chama o endpoint HTTP publicado pela Modal (modal_avatar.py, função
generate_endpoint) para gerar o vídeo do avatar via GPU externa.

Manda a imagem e o áudio como base64 direto no corpo da requisição —
como ambos são pequenos (uma foto e um áudio de ~20s), não é necessário
hospedar em storage intermediário só para a Modal buscar por URL.
"""

import os
import base64
import requests

MODAL_ENDPOINT_URL = os.environ["MODAL_ENDPOINT_URL"]


def generate_avatar_via_modal(image_path: str, audio_path: str, output_path: str) -> str:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    resp = requests.post(
        MODAL_ENDPOINT_URL,
        json={"image_base64": image_b64, "audio_base64": audio_b64},
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
