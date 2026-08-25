"""
generate_thumbnail.py

Monta a thumbnail no formato combinado:
- Metade esquerda: retrato gerado pela Agnes AI (pessoa fictícia, alternando
  homem/mulher a cada execução) — nunca uma pessoa real da entrevista.
- Metade direita: frame extraído do próprio vídeo (o entrevistado real).
- Seta apontando da imagem gerada para o frame real.
- Faixa horizontal (1/5 inferior da thumb) com texto curto e chamativo,
  desenhado com Pillow (não depende da IA gerar texto, que costuma falhar).
"""

import os
import json
import random
import requests
from PIL import Image, ImageDraw, ImageFont

AGNES_API_URL = "https://apihub.agnes-ai.com/v1/images/generations"
AGNES_MODEL = "agnes-image-2.0-flash"

THUMB_W, THUMB_H = 1280, 720
BANNER_HEIGHT = int(THUMB_H / 5)

# Prompts alternando gênero — a Agnes decide o resto (estilo "retrato realista,
# olhando de forma intrigada/séria para o lado direito da imagem", pra reforçar
# a composição de "reação" olhando para o frame real ao lado).
PROMPTS_HOMEM = [
    "Retrato realista de um homem de meia-idade, expressão de surpresa, "
    "olhando para a direita da imagem, fundo desfocado escuro, estilo still de reação",
]
PROMPTS_MULHER = [
    "Retrato realista de uma mulher de meia-idade, expressão de surpresa, "
    "olhando para a direita da imagem, fundo desfocado escuro, estilo still de reação",
]


def generate_agnes_portrait(api_key: str, out_path: str) -> str:
    """Gera o retrato via Agnes AI, alternando gênero aleatoriamente."""
    prompt = random.choice(PROMPTS_HOMEM if random.random() < 0.5 else PROMPTS_MULHER)

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": AGNES_MODEL,
        "prompt": prompt,
        "size": "1024x1024",
        # response_format vai dentro de extra_body — a API retorna erro 400
        # se for colocado no nível raiz do corpo da requisição.
        "extra_body": {"response_format": "url"},
    }
    resp = requests.post(AGNES_API_URL, headers=headers, json=payload, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    image_url = data["data"][0]["url"]
    img_bytes = requests.get(image_url, timeout=30).content
    with open(out_path, "wb") as f:
        f.write(img_bytes)
    return out_path


def extract_frame(video_path: str, timestamp_sec: float, out_path: str) -> str:
    """Extrai um frame do vídeo da entrevista (idealmente um momento de tensão)."""
    import subprocess
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp_sec),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        out_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return out_path


def draw_arrow(draw: ImageDraw.Draw, start, end, width=8, color="#FFD400"):
    """Desenha uma seta estilizada entre dois pontos."""
    draw.line([start, end], fill=color, width=width)
    # cabeça da seta
    import math
    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    arrow_len = 25
    for da in (0.4, -0.4):
        ax = end[0] - arrow_len * math.cos(angle - da)
        ay = end[1] - arrow_len * math.sin(angle - da)
        draw.line([end, (ax, ay)], fill=color, width=width)


def compose_thumbnail(
    portrait_path: str,
    frame_path: str,
    hook_text: str,
    output_path: str,
    font_path: str = "assets/fonts/Anton-Regular.ttf",
) -> str:
    """
    Monta a thumbnail final: retrato à esquerda, frame real à direita,
    seta conectando os dois, faixa de texto na base.
    """
    canvas = Image.new("RGB", (THUMB_W, THUMB_H), "black")

    half_w = THUMB_W // 2
    content_h = THUMB_H - BANNER_HEIGHT

    portrait = Image.open(portrait_path).convert("RGB").resize((half_w, content_h))
    frame = Image.open(frame_path).convert("RGB").resize((half_w, content_h))

    canvas.paste(portrait, (0, 0))
    canvas.paste(frame, (half_w, 0))

    draw = ImageDraw.Draw(canvas)

    # Seta do centro do retrato até o começo do frame real
    draw_arrow(
        draw,
        start=(half_w - 90, content_h // 2),
        end=(half_w + 15, content_h // 2),
    )

    # Faixa de texto na base (1/5 da altura)
    draw.rectangle(
        [(0, content_h), (THUMB_W, THUMB_H)],
        fill="#E60000",
    )

    try:
        font = ImageFont.truetype(font_path, size=64)
    except OSError:
        font = ImageFont.load_default()

    text = hook_text.upper()
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (THUMB_W - text_w) // 2
    text_y = content_h + (BANNER_HEIGHT - text_h) // 2

    # contorno preto para legibilidade
    for dx, dy in [(-2, -2), (-2, 2), (2, -2), (2, 2)]:
        draw.text((text_x + dx, text_y + dy), text, font=font, fill="black")
    draw.text((text_x, text_y), text, font=font, fill="white")

    canvas.save(output_path, quality=92)
    return output_path


HOOK_TEXTS = [
    "A entrevista pegou fogo",
    "Ele não esperava essa pergunta",
    "Resposta chocou todo mundo",
    "O clima mudou de repente",
    "Ninguém esperava essa reação",
    "A pergunta que ele não queria",
]


if __name__ == "__main__":
    api_key = os.environ["AGNES_API_KEY"]

    with open("source_meta.json") as f:
        source_meta = json.load(f)

    # O corte (interview_cut.mp4) foi centrado no momento de tensão, então
    # o meio do próprio clipe já é um bom ponto para capturar o frame.
    import subprocess as _sub
    duration_result = _sub.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "interview_cut.mp4"],
        capture_output=True, text=True, check=True,
    )
    clip_duration = float(json.loads(duration_result.stdout)["format"]["duration"])

    portrait = generate_agnes_portrait(api_key, "portrait.jpg")
    frame = extract_frame("interview_cut.mp4", timestamp_sec=clip_duration / 2, out_path="frame.jpg")

    hook_text = random.choice(HOOK_TEXTS)

    compose_thumbnail(
        portrait_path=portrait,
        frame_path=frame,
        hook_text=hook_text,
        output_path="thumbnail.jpg",
    )
    print(f"Thumbnail gerada: thumbnail.jpg (gancho: '{hook_text}')")
