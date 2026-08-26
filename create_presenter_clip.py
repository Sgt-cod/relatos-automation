"""
create_presenter_clip.py

Alternativa ao avatar via Modal/SadTalker: usa um vídeo LONGO já gravado
do apresentador (gesticulando, com nariz e boca mascarados — de modo que
não fique óbvio que ele não está de fato falando o áudio) em
assets/presenter.mp4, e apenas substitui o áudio original pelo áudio
gerado (roteiro + Fish Audio).

- Se o vídeo for mais curto que o áudio, repete em loop até cobrir a
  duração inteira.
- Se for mais longo, corta um trecho do tamanho exato do áudio, a partir
  de um ponto aleatório (pra não usar sempre o mesmo trecho do vídeo em
  toda execução).

Produz o mesmo nome de arquivo de saída que a rota via Modal
(output_avatar.mp4), então os passos seguintes do pipeline (composição
do vídeo final, thumbnail, etc.) funcionam sem precisar saber qual das
duas rotas gerou o clipe.
"""

import subprocess
import random
import json


def get_media_duration(path: str) -> float:
    """Duração em segundos de um arquivo de vídeo ou áudio, via ffprobe."""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def create_presenter_clip(
    presenter_path: str,
    audio_path: str,
    output_path: str,
) -> str:
    audio_duration = get_media_duration(audio_path)
    video_duration = get_media_duration(presenter_path)

    # Ponto de início aleatório no vídeo do apresentador — varia o trecho
    # usado a cada execução, mesmo sendo sempre o mesmo arquivo de origem.
    # "-stream_loop -1" cobre o caso do áudio ser mais longo que o vídeo
    # (repete em loop automaticamente até bater a duração do áudio); se o
    # vídeo já for mais longo, o loop nunca chega a ser necessário e o
    # resultado é só um corte simples a partir do ponto aleatório.
    max_start = max(0.0, video_duration - 1.0)  # margem de 1s pra não começar bem no fim
    start_offset = random.uniform(0, max_start) if max_start > 0 else 0.0

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-ss", str(start_offset),
            "-i", presenter_path,
            "-i", audio_path,
            "-map", "0:v:0",  # vídeo do apresentador
            "-map", "1:a:0",  # áudio gerado (substitui o áudio original do vídeo)
            "-t", str(audio_duration),  # corta exatamente na duração do áudio
            "-c:v", "libx264",
            "-c:a", "aac",
            output_path,
        ],
        check=True,
    )
    return output_path


if __name__ == "__main__":
    create_presenter_clip(
        presenter_path="assets/presenter.mp4",
        audio_path="audio.wav",
        output_path="output_avatar.mp4",
    )
    print("Vídeo do apresentador (local, sem Modal) gerado: output_avatar.mp4")
