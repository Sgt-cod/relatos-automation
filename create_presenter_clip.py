"""
create_presenter_clip.py

Alternativa ao avatar via Modal/SadTalker: usa um vídeo LONGO já gravado
do apresentador (gesticulando, com nariz e boca mascarados — de modo que
não fique óbvio que ele não está de fato falando o áudio) em
assets/presenter*.mp4, e apenas substitui o áudio original pelo áudio
gerado (roteiro + Fish Audio).

- pick_presenter_video() escolhe aleatoriamente entre todos os vídeos
  disponíveis em assets/ que batam com "presenter*.mp4" (presenter.mp4,
  presenter1.mp4, presenter2.mp4, ...) — dá pra ter vários vídeos-base
  diferentes e cada intervenção do personagem usa um sorteado, pra variar
  visualmente entre as intervenções de um mesmo vídeo publicado.
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
import glob

from pipeline_config import TARGET_FPS


def get_media_duration(path: str) -> float:
    """Duração em segundos de um arquivo de vídeo ou áudio, via ffprobe."""
    cmd = ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(json.loads(result.stdout)["format"]["duration"])


def pick_presenter_video(assets_dir: str = "assets") -> str:
    """
    Escolhe aleatoriamente um vídeo de apresentador entre os disponíveis
    (presenter.mp4, presenter1.mp4, presenter2.mp4, presenter3.mp4, ...).
    Usa todos os arquivos que baterem com o padrão "presenter*.mp4" — não
    precisa ter todos numerados, funciona com só presenter.mp4 também.
    """
    candidates = sorted(glob.glob(f"{assets_dir}/presenter*.mp4"))
    if not candidates:
        raise FileNotFoundError(
            f"Nenhum vídeo de apresentador encontrado em {assets_dir}/presenter*.mp4"
        )
    return random.choice(candidates)


def create_presenter_clip(
    presenter_path: str,
    audio_path: str,
    output_path: str,
) -> str:
    audio_duration = get_media_duration(audio_path)
    video_duration = get_media_duration(presenter_path)

    # IMPORTANTE: "-stream_loop -1" combinado com "-ss" (busca por um ponto
    # aleatório) no MESMO comando tem comportamento instável no ffmpeg —
    # em alguns casos o loop não repete de fato depois do seek, e o clipe
    # sai como se fosse uma imagem estática. Por isso os dois casos abaixo
    # são tratados SEPARADAMENTE, nunca combinando -ss com -stream_loop.
    if video_duration >= audio_duration:
        # Vídeo já cobre a duração do áudio: só corta um trecho (a partir
        # de um ponto aleatório, pra variar), sem precisar de loop.
        max_start = max(0.0, video_duration - audio_duration - 0.5)
        start_offset = random.uniform(0, max_start) if max_start > 0 else 0.0
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_offset),
            "-i", presenter_path,
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", str(audio_duration),
            "-r", str(TARGET_FPS),   # fps fixo — evita descompasso na concatenação final
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-c:a", "aac",
            output_path,
        ]
    else:
        # Vídeo mais curto que o áudio: precisa repetir em loop — SEM
        # ponto de início aleatório nesse caso, pra não combinar com -ss.
        cmd = [
            "ffmpeg", "-y",
            "-stream_loop", "-1",
            "-i", presenter_path,
            "-i", audio_path,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-t", str(audio_duration),
            "-r", str(TARGET_FPS),   # fps fixo — evita descompasso na concatenação final
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-c:a", "aac",
            output_path,
        ]

    subprocess.run(cmd, check=True)
    return output_path


if __name__ == "__main__":
    create_presenter_clip(
        presenter_path=pick_presenter_video(),
        audio_path="audio.wav",
        output_path="output_avatar.mp4",
    )
    print("Vídeo do apresentador (local, sem Modal) gerado: output_avatar.mp4")
