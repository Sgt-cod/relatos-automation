"""
generate_audio.py

Gera o áudio da narração do avatar usando a API do Fish Audio,
a partir de um roteiro de texto (produzido pelo Gemini).

Requer variável de ambiente FISH_AUDIO_API_KEY.
"""

import os
import time
import requests

FISH_AUDIO_API_URL = "https://api.fish.audio/v1/tts"

# "s2.1-pro-free" é o modelo gratuito da Fish Audio (mesma qualidade do
# s2.1-pro pago). Sem esse header, a API cai por padrão no modelo pago
# e retorna 402 Payment Required.
FISH_AUDIO_MODEL = os.environ.get("FISH_AUDIO_MODEL", "s2.1-pro-free")

MAX_RETRIES = 3
INITIAL_BACKOFF_SEC = 5


def generate_audio(script_text: str, voice_id: str, output_path: str) -> str:
    """
    Chama a API do Fish Audio (TTS) e salva o áudio resultante em output_path.
    Faz retry automático em caso de timeout (o tier gratuito pode ser mais
    lento em horários de pico).

    Args:
        script_text: o roteiro que o avatar vai "falar".
        voice_id: ID da voz de referência (você escolhe uma voz no Fish Audio
                   e usa o reference_id dela, ou treina uma custom voice).
        output_path: caminho local onde salvar o .mp3/.wav resultante.
    """
    api_key = os.environ["FISH_AUDIO_API_KEY"]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": FISH_AUDIO_MODEL,  # vai no header, não no body
    }
    payload = {
        "text": script_text,
        "reference_id": voice_id,
        "format": "wav",  # wav facilita o SadTalker processar depois
        "normalize": True,
    }

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = requests.post(
                FISH_AUDIO_API_URL, headers=headers, json=payload, timeout=180
            )
            response.raise_for_status()

            with open(output_path, "wb") as f:
                f.write(response.content)

            return output_path

        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as e:
            last_error = e
            if attempt == MAX_RETRIES:
                raise
            wait = INITIAL_BACKOFF_SEC * (2 ** (attempt - 1))
            print(f"[generate_audio] Tentativa {attempt}/{MAX_RETRIES} falhou "
                  f"({e}). Tentando de novo em {wait}s...")
            time.sleep(wait)

    raise last_error  # pragma: no cover — inalcançável na prática


if __name__ == "__main__":
    # Exemplo de uso isolado, para teste manual
    roteiro = (
        "Nessa entrevista, o convidado respondeu a uma pergunta direta "
        "sobre o tema mais debatido da semana. Vamos ver como foi."
    )
    generate_audio(
        script_text=roteiro,
        voice_id=os.environ.get("FISH_AUDIO_VOICE_ID", "default-voice-id"),
        output_path="test_audio.wav",
    )
    print("Áudio gerado: test_audio.wav")
