"""
generate_thumbnail.py

Monta a thumbnail escolhendo aleatoriamente uma imagem pronta (16:9) da
pasta assets/thumb/, e desenhando por cima a faixa de texto na base
(1/5 inferior), com o gancho gerado pelo Gemini a partir do conteúdo
real do vídeo — igual antes, só que sem Agnes e sem extrair frame do
vídeo pra compor a imagem.
"""

import os
import json
import random
import glob
from PIL import Image, ImageDraw, ImageFont

THUMB_W, THUMB_H = 1280, 720
BANNER_HEIGHT = int(THUMB_H / 5)


def pick_random_thumb_image(thumb_dir: str = "assets/thumb") -> str:
    """Escolhe aleatoriamente uma imagem entre as disponíveis em assets/thumb/."""
    candidates = []
    for ext in ("*.jpg", "*.jpeg", "*.png"):
        candidates.extend(glob.glob(os.path.join(thumb_dir, ext)))

    if not candidates:
        raise FileNotFoundError(
            f"Nenhuma imagem encontrada em {thumb_dir}/ — coloque pelo menos "
            f"uma imagem 16:9 (.jpg/.jpeg/.png) nessa pasta."
        )
    return random.choice(candidates)


def generate_hook_text(source_meta: dict, transcript_excerpt: str) -> str:
    """
    Pede pro Gemini um gancho curto e específico para a faixa de texto da
    thumbnail — baseado no conteúdo real do vídeo, não numa lista fixa
    de frases genéricas.
    """
    from gemini_client import call_gemini

    api_key = os.environ["GEMINI_API_KEY"]
    prompt = (
        "Escreva UM gancho curto para a faixa de texto de uma thumbnail de "
        "YouTube, sobre o trecho de conteúdo abaixo. Regras:\n"
        "- Entre 3 e 6 palavras. Vai em CAIXA ALTA na thumbnail (não precisa "
        "escrever em maiúsculas, só responda o texto normal).\n"
        "- Específico ao conteúdo real do trecho — não genérico.\n"
        "- Não invente fatos que não estejam no trecho, e não use "
        "rótulos político-ideológicos.\n"
        "- Pode usar um ângulo de curiosidade/impacto, mas sem sensacionalismo "
        "vazio — precisa ser sustentável pelo conteúdo.\n\n"
        f"Trecho:\n{transcript_excerpt}\n\n"
        "Responda APENAS com o texto do gancho, sem aspas, sem pontuação final."
    )
    return call_gemini(prompt, api_key).strip().strip('"').strip("'")


def compose_thumbnail(
    image_path: str,
    hook_text: str,
    output_path: str,
    font_path: str | None = None,
) -> str:
    """
    Redimensiona a imagem escolhida pra 1280x720 e desenha a faixa de
    texto na base (1/5 inferior da altura).
    """
    canvas = Image.open(image_path).convert("RGB").resize((THUMB_W, THUMB_H))
    draw = ImageDraw.Draw(canvas)

    content_h = THUMB_H - BANNER_HEIGHT

    # Faixa de texto na base
    draw.rectangle(
        [(0, content_h), (THUMB_W, THUMB_H)],
        fill="#E60000",
    )

    text = hook_text.upper()

    # Fontes candidatas, em ordem de preferência (com fallback pra fonte
    # padrão do sistema se nenhuma estiver disponível em assets/fonts/).
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

    for candidate_path in font_candidates:
        try:
            for size in range(font_size, min_font_size - 1, -6):
                test_font = ImageFont.truetype(candidate_path, size=size)
                bbox = draw.textbbox((0, 0), text, font=test_font)
                text_w = bbox[2] - bbox[0]
                if text_w <= THUMB_W - 60:  # margem de 30px de cada lado
                    font = test_font
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
    with open("source_meta.json") as f:
        source_meta = json.load(f)

    # Dois pipelines diferentes chamam este script:
    # - variante do personagem mascarado: gera interventions.json (N mini-roteiros)
    # - pipeline original: gera script.txt (um único roteiro de abertura)
    # Detecta qual dos dois existe e adapta o "gancho" da thumbnail a partir daí.
    if os.path.exists("interventions.json"):
        with open("interventions.json") as f:
            interventions = json.load(f)

        mid = interventions["mid"]
        # Escolhe uma das intervenções críticas como base do gancho (a
        # mais "central" da lista costuma ser um bom equilíbrio entre já
        # ter contexto acumulado e ainda não ser o fecho do vídeo).
        featured = mid[len(mid) // 2]
        hook_source_text = featured["script_text"]
    else:
        with open("script.txt") as f:
            hook_source_text = f.read().strip()

    image_path = pick_random_thumb_image()
    hook_text = generate_hook_text(source_meta, hook_source_text)

    compose_thumbnail(
        image_path=image_path,
        hook_text=hook_text,
        output_path="thumbnail.jpg",
    )
    print(f"Thumbnail gerada: thumbnail.jpg (imagem: '{image_path}', gancho: '{hook_text}')")
