"""
generate_script.py

Passo 3 do generate.yml: gera o roteiro que o avatar vai falar, com base
no trecho de tensão identificado por find_and_download.py.

Ponto importante do prompt: o roteiro é revisado por você no Telegram
antes de publicar, mas o objetivo é que já chegue correto — então o
prompt instrui o Gemini a:
- descrever o que vai acontecer no vídeo (função de "chamada", não de
  análise/opinião),
- se ater ao que está de fato na transcrição (não inferir motivação,
  intenção ou estado mental de quem fala),
- não usar rótulos político-ideológicos para os participantes,
- não fazer afirmações factuais que não estejam na transcrição.

Isso reduz o risco de o roteiro sair com alucinação ou enquadramento
tendencioso — mas o checkpoint humano no Telegram continua sendo a
salvaguarda principal antes de qualquer coisa ir ao ar.
"""

import os
import json
from gemini_client import call_gemini

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]


def build_prompt(source_meta: dict, transcript_excerpt: str) -> str:
    return (
        "Escreva um roteiro curto (3 a 4 frases, ~15-20 segundos falados) "
        "para um apresentador de vídeo anunciar o trecho de entrevista que "
        "vai aparecer em seguida. Regras obrigatórias:\n"
        "- Descreva APENAS o que está de fato na transcrição abaixo — não "
        "invente falas, dados ou eventos que não estejam nela.\n"
        "- Não atribua motivação, intenção ou estado emocional a nenhum "
        "participante (ex.: não diga 'ficou sem reação' ou 'tentou fugir "
        "da pergunta') a menos que isso esteja explicitamente na "
        "transcrição.\n"
        "- Não use rótulos político-ideológicos para descrever os "
        "participantes (ex.: 'jornalista de esquerda/direita').\n"
        "- Tom: instigante e direto, tipo chamada de telejornal, mas sem "
        "alegações que a transcrição não sustenta.\n"
        "- Gancho de curiosidade permitido (ex.: 'o que ele respondeu a "
        "seguir gerou repercussão'), desde que não seja uma afirmação "
        "factual não verificável.\n\n"
        f"Veículo: {source_meta['channel']}\n"
        f"Título original: {source_meta['title']}\n\n"
        f"Trecho da transcrição (momento de maior tensão):\n{transcript_excerpt}\n\n"
        "Responda apenas com o texto do roteiro, sem aspas, sem markdown, "
        "sem explicações adicionais."
    )


def get_transcript_excerpt(transcript_path: str, center_sec: float, window_sec: float = 60) -> str:
    with open(transcript_path) as f:
        transcript = json.load(f)

    excerpt_segments = [
        seg for seg in transcript
        if center_sec - window_sec <= seg["start"] <= center_sec + window_sec
    ]
    return "\n".join(seg["text"] for seg in excerpt_segments)


def generate_script(source_meta: dict, transcript_excerpt: str) -> str:
    prompt = build_prompt(source_meta, transcript_excerpt)
    return call_gemini(prompt, GEMINI_API_KEY).strip()


def main():
    with open("source_meta.json") as f:
        source_meta = json.load(f)

    transcript_excerpt = get_transcript_excerpt(
        "transcript.json",
        center_sec=source_meta["tense_moment"]["center_sec"],
    )

    script_text = generate_script(source_meta, transcript_excerpt)

    with open("script.txt", "w") as f:
        f.write(script_text)

    print("Roteiro gerado:\n" + script_text)


if __name__ == "__main__":
    main()
