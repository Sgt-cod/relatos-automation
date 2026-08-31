"""
create_vertical_short.py

Depois da aprovação no Telegram (quando os clipes de cada intervenção já
existem), escolhe qual das intervenções críticas tem mais potencial de
viralizar sozinha como um corte curto, e converte esse clipe pra formato
vertical (9:16) — pronto pra você postar manualmente no Instagram/TikTok/X,
sem nenhuma automação de publicação (que decidimos não fazer por ora).
"""

import os
import subprocess

from pipeline_config import TARGET_FPS

SHORT_W, SHORT_H = 1080, 1920


def pick_best_intervention_for_short(mid_interventions: list) -> int:
    """
    Pede pro Gemini escolher qual das intervenções críticas tem mais
    potencial de viralizar como corte curto isolado (sem o contexto do
    resto do vídeo). Retorna o índice na lista mid_interventions.
    """
    from gemini_client import call_gemini

    api_key = os.environ["GEMINI_API_KEY"]
    options_text = "\n".join(
        f"{i}: {it['script_text']}" for i, it in enumerate(mid_interventions)
    )
    prompt = (
        "Você vai escolher qual das falas abaixo tem mais potencial de "
        "viralizar como um corte curto isolado em redes sociais "
        "(Reels/Shorts/TikTok) — a mais impactante, engraçada ou "
        "compartilhável sozinha, sem precisar do contexto do resto do "
        "vídeo.\n\n"
        f"{options_text}\n\n"
        "Responda APENAS com o número da opção escolhida, nada mais."
    )
    resp = call_gemini(prompt, api_key).strip()
    try:
        idx = int(resp)
        if 0 <= idx < len(mid_interventions):
            return idx
    except ValueError:
        pass
    return 0  # fallback: primeira intervenção, se a resposta vier fora do esperado


def create_vertical_short(clip_path: str, output_path: str = "short_vertical.mp4") -> str:
    """
    Converte um clipe (tipicamente 16:9 ou a proporção nativa do
    assets/presenter*.mp4) pra vertical 9:16 (1080x1920), mantendo a
    proporção original com barras pretas onde precisar — evita cortar o
    personagem pra fora do quadro.
    """
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", clip_path,
            "-vf",
            f"scale={SHORT_W}:{SHORT_H}:force_original_aspect_ratio=decrease,"
            f"pad={SHORT_W}:{SHORT_H}:(ow-iw)/2:(oh-ih)/2,setsar=1",
            "-r", str(TARGET_FPS),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k",
            output_path,
        ],
        check=True,
    )
    return output_path
