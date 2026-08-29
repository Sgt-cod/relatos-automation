"""
gemini_client.py

Centraliza a chamada à API do Gemini, usada por find_and_download.py
(identificar trecho de tensão) e generate_script.py (roteiro do avatar).

Inclui retry automático com backoff exponencial para erros transitórios
(503 Service Unavailable, 429 Too Many Requests, 500 Internal Server
Error) — comuns na API do Gemini em horários de pico, e que costumam se
resolver sozinhos numa segunda tentativa alguns segundos depois. Como a
pipeline roda sem supervisão humana, não faz sentido deixar o workflow
inteiro falhar por causa de uma instabilidade momentânea do lado do
Google.

Manter o nome do modelo num único lugar também facilita a manutenção:
modelos do Gemini são desativados com alguma frequência (ex.: o
gemini-2.0-flash foi desligado em jun/2026) — se isso acontecer de novo,
basta trocar o valor de GEMINI_MODEL aqui, em vez de em vários arquivos.
"""

import time
import requests

GEMINI_MODEL = "gemini-3.1-flash-lite"
GEMINI_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# Códigos de erro considerados transitórios — vale tentar de novo.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

MAX_RETRIES = 4
INITIAL_BACKOFF_SEC = 5  # dobra a cada tentativa: 5s, 10s, 20s, 40s


def call_gemini(prompt: str, api_key: str) -> str:
    """
    Chama a API do Gemini com o prompt fornecido e retorna o texto da
    resposta. Faz retry automático em caso de erro transitório.
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(
                f"{GEMINI_URL}?key={api_key}",
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=60,
            )

            if resp.status_code in RETRYABLE_STATUS_CODES:
                raise requests.exceptions.HTTPError(
                    f"{resp.status_code} (transitório)", response=resp
                )

            resp.raise_for_status()
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]

        except (requests.exceptions.HTTPError, requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            last_error = e
            is_retryable = (
                isinstance(e, (requests.exceptions.ConnectionError, requests.exceptions.Timeout))
                or (e.response is not None and e.response.status_code in RETRYABLE_STATUS_CODES)
            )

            if not is_retryable or attempt == MAX_RETRIES:
                raise

            wait = INITIAL_BACKOFF_SEC * (2 ** (attempt - 1))
            print(f"[gemini_client] Tentativa {attempt}/{MAX_RETRIES} falhou "
                  f"({e}). Tentando de novo em {wait}s...")
            time.sleep(wait)

    raise last_error  # pragma: no cover — inalcançável na prática
