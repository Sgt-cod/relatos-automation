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
    """Gera o retrato via Agnes AI, alternando gênero aleatoriamente.
    Faz retry automático em caso de erro transitório do servidor
    (503/502/500/429), do mesmo jeito que já fazemos com Gemini e Fish Audio."""
    import time

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

    retryable_status_codes = {429, 500, 502, 503, 504}
    max_retries = 4
    initial_backoff_sec = 5

    resp = None
    for attempt in range(1, max_retries + 1):
        resp = requests.post(AGNES_API_URL, headers=headers, json=payload, timeout=120)
        if resp.status_code not in retryable_status_codes:
            break
        if attempt == max_retries:
            break
        wait = initial_backoff_sec * (2 ** (attempt - 1))
        print(f"[generate_thumbnail] Agnes retornou {resp.status_code} (tentativa "
              f"{attempt}/{max_retries}). Tentando de novo em {wait}s...")
        time.sleep(wait)

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


def paste_arrow(canvas: Image.Image, center_x: int, center_y: int, arrow_path: str, width: int = 160) -> None:
    """
    Cola a imagem da seta (PNG com fundo transparente) centralizada em
    (center_x, center_y), redimensionada para a largura desejada mantendo
    a proporção original.
    """
    arrow = Image.open(arrow_path).convert("RGBA")
    ratio = width / arrow.width
    height = int(arrow.height * ratio)
    arrow = arrow.resize((width, height))

    paste_x = center_x - width // 2
    paste_y = center_y - height // 2
    canvas.paste(arrow, (paste_x, paste_y), mask=arrow)  # usa o canal alfa como máscara


def generate_hook_text(source_meta: dict, transcript_excerpt: str) -> str:
    """
    Pede pro Gemini um gancho curto e específico para a faixa de texto da
    thumbnail — baseado no conteúdo real da entrevista, não numa lista
    fixa de frases genéricas.
    """
    from gemini_client import call_gemini

    api_key = os.environ["GEMINI_API_KEY"]
    prompt = (
        "Escreva UM gancho curto para a faixa de texto de uma thumbnail de "
        "YouTube, sobre o trecho de entrevista abaixo. Regras:\n"
        "- Entre 3 e 6 palavras. Vai em CAIXA ALTA na thumbnail (não precisa "
        "escrever em maiúsculas, só responda o texto normal).\n"
        "- Específico ao conteúdo real da transcrição — não genérico "
        "(nunca algo como 'entrevista pega fogo' se isso não refletir o "
        "que de fato foi dito).\n"
        "- Não invente fatos que não estejam na transcrição, e não use "
        "rótulos político-ideológicos.\n"
        "- Pode usar um ângulo de curiosidade/impacto, mas sem sensacionalismo "
        "vazio — precisa ser sustentável pelo conteúdo.\n\n"
        f"Trecho da transcrição:\n{transcript_excerpt}\n\n"
        "Responda APENAS com o texto do gancho, sem aspas, sem pontuação final."
    )
    return call_gemini(prompt, api_key).strip().strip('"').strip("'")


def compose_thumbnail(
    portrait_path: str,
    frame_path: str,
    hook_text: str,
    output_path: str,
    font_path: str | None = None,
    arrow_path: str = "assets/arrow_right.png",
) -> str:
    """
    Monta a thumbnail final: retrato à esquerda, frame real à direita,
    seta (imagem PNG) conectando os dois, faixa de texto na base.
    """
    canvas = Image.new("RGB", (THUMB_W, THUMB_H), "black")

    half_w = THUMB_W // 2
    content_h = THUMB_H - BANNER_HEIGHT

    portrait = Image.open(portrait_path).convert("RGB").resize((half_w, content_h))
    frame = Image.open(frame_path).convert("RGB").resize((half_w, content_h))

    canvas.paste(portrait, (0, 0))
    canvas.paste(frame, (half_w, 0))

    # Seta do centro do retrato até o começo do frame real
    try:
        paste_arrow(canvas, center_x=half_w, center_y=content_h // 2, arrow_path=arrow_path)
    except (FileNotFoundError, OSError):
        print(f"[generate_thumbnail] Aviso: seta não encontrada em {arrow_path} — thumbnail sem seta.")

    draw = ImageDraw.Draw(canvas)

    # Faixa de texto na base (1/5 da altura)
    draw.rectangle(
        [(0, content_h), (THUMB_W, THUMB_H)],
        fill="#E60000",
    )

    text = hook_text.upper()

    # Fontes candidatas, em ordem de preferência (as duas indicadas pelo
    # usuário, com fallback pra fonte padrão do sistema se nenhuma
    # estiver disponível em assets/fonts/).
    font_candidates = (
        [font_path] if font_path else [
            "assets/fonts/Bangers-Regular.ttf",
            "assets/fonts/RoadRage-Regular.ttf",
        ]
    )

    # Tamanho grande por padrão, com auto-shrink se o texto não couber
    # na largura da faixa (evita estourar a thumbnail com ganchos longos).
    font_size = 110
    min_font_size = 60
    font = None
    chosen_font_path = None

    for candidate_path in font_candidates:
        try:
            for size in range(font_size, min_font_size - 1, -6):
                test_font = ImageFont.truetype(candidate_path, size=size)
                bbox = draw.textbbox((0, 0), text, font=test_font)
                text_w = bbox[2] - bbox[0]
                if text_w <= THUMB_W - 60:  # margem de 30px de cada lado
                    font = test_font
                    chosen_font_path = candidate_path
                    break
            if font:
                break
        except OSError:
            continue  # fonte não encontrada, tenta a próxima candidata

    if font is None:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_x = (THUMB_W - text_w) // 2
    text_y = content_h + (BANNER_HEIGHT - text_h) // 2

    # contorno preto para legibilidade
    outline_width = 4
    for dx in range(-outline_width, outline_width + 1, 2):
        for dy in range(-outline_width, outline_width + 1, 2):
            if dx == 0 and dy == 0:
                continue
            draw.text((text_x + dx, text_y + dy), text, font=font, fill="black")
    draw.text((text_x, text_y), text, font=font, fill="white")

    canvas.save(output_path, quality=92)
    return output_path





if __name__ == "__main__":
    api_key = os.environ["AGNES_API_KEY"]

    with open("source_meta.json") as f:
        source_meta = json.load(f)

    clip_start_sec = source_meta["clip_start_sec"]

    # Dois pipelines diferentes chamam este script:
    # - variante do personagem mascarado: gera interventions.json (N mini-roteiros)
    # - pipeline original: gera script.txt (um único roteiro de abertura)
    # Detecta qual dos dois existe e adapta o "gancho" da thumbnail a partir daí.
    if os.path.exists("interventions.json"):
        with open("interventions.json") as f:
            interventions = json.load(f)

        mid = interventions["mid"]
        # Escolhe uma das intervenções críticas pra estampar na thumbnail
        # (a mais "central" da lista costuma ser um bom equilíbrio entre
        # já ter contexto acumulado e ainda não ser o fecho do vídeo).
        featured = mid[len(mid) // 2]
        timestamp_sec = featured["timestamp_sec"]
        hook_source_text = featured["script_text"]
    else:
        with open("script.txt") as f:
            hook_source_text = f.read().strip()
        # Sem uma lista de momentos específicos, usa o início da janela
        # de destaque como ponto de referência pro frame da thumbnail.
        timestamp_sec = source_meta["highlight_window"]["start_sec"]

    # Timestamp do frame RELATIVO ao clipe já cortado (highlight_cut.mp4),
    # não ao vídeo original.
    frame_timestamp_in_clip = max(0.0, timestamp_sec - clip_start_sec)

    portrait = generate_agnes_portrait(api_key, "portrait.jpg")
    frame = extract_frame("highlight_cut.mp4", timestamp_sec=frame_timestamp_in_clip, out_path="frame.jpg")

    hook_text = generate_hook_text(source_meta, hook_source_text)

    compose_thumbnail(
        portrait_path=portrait,
        frame_path=frame,
        hook_text=hook_text,
        output_path="thumbnail.jpg",
    )
    print(f"Thumbnail gerada: thumbnail.jpg (gancho: '{hook_text}')")
