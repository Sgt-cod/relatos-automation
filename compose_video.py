"""
compose_video.py

Monta o vídeo final combinando:
1. Os primeiros N segundos: vídeo da entrevista mudo, com o avatar em PiP
   (canto superior esquerdo) comentando a notícia.
2. O restante: vídeo da entrevista com áudio original, sem PiP.

Usa ffmpeg via subprocess (mais previsível e leve que moviepy para esse tipo
de composição fixa).
"""

import subprocess
import json


def get_video_duration(path: str) -> float:
    """Retorna a duração em segundos de um vídeo, via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def compose_final_video(
    interview_path: str,
    avatar_path: str,
    output_path: str,
    pip_scale: float = 0.35,
    pip_margin: int = 20,
) -> str:
    """
    Args:
        interview_path: caminho do corte da entrevista (6-7 min).
        avatar_path: caminho do vídeo do avatar gerado pelo SadTalker via Modal.
        output_path: caminho do vídeo final.
        pip_scale: proporção do PiP em relação à largura do vídeo principal.
        pip_margin: margem em pixels do PiP até a borda.
    """
    avatar_duration = get_video_duration(avatar_path)

    # Filtro:
    # - [0:v] = entrevista (vídeo principal)
    # - [1:v] = avatar (PiP)
    # Durante os primeiros `avatar_duration` segundos:
    #   - entrevista fica muda (volume=0 nesse trecho) e o avatar é sobreposto
    # Depois disso:
    #   - só a entrevista, com áudio original
    #
    # Estratégia: usar overlay com enable='between(t,0,avatar_duration)'
    # e volume automatizado via filtro 'volume' com expressão de tempo.

    filter_complex = (
        f"[1:v]scale=iw*{pip_scale}:ih*{pip_scale}[pip];"
        f"[0:v][pip]overlay=x={pip_margin}:y={pip_margin}:"
        f"enable='between(t,0,{avatar_duration})'[vout];"
        f"[0:a]volume=enable='between(t,0,{avatar_duration})':volume=0[muted_part];"
        f"[1:a]apad[avatar_audio_padded];"
    )

    # Para simplificar e evitar bugs de sincronismo de áudio com filtros
    # condicionais complexos, a abordagem mais robusta na prática é:
    # 1. Gerar um clipe A = entrevista mudo (0 a avatar_duration) + áudio do avatar
    # 2. Gerar um clipe B = entrevista original a partir de avatar_duration até o fim
    # 3. Concatenar A + B
    # Isso evita edge cases de overlay/volume condicionados por tempo.

    cmd_clip_a_video = [
        "ffmpeg", "-y",
        "-i", interview_path,
        "-i", avatar_path,
        "-filter_complex",
        f"[1:v]scale=iw*{pip_scale}:ih*{pip_scale}[pip];"
        f"[0:v]trim=0:{avatar_duration},setpts=PTS-STARTPTS[base];"
        f"[base][pip]overlay=x={pip_margin}:y={pip_margin}[vout]",
        "-map", "[vout]",
        "-map", "1:a",  # áudio do avatar (Fish Audio) durante essa parte
        "-t", str(avatar_duration),
        "-c:v", "libx264", "-c:a", "aac",
        "clip_a.mp4",
    ]

    cmd_clip_b = [
        "ffmpeg", "-y",
        "-i", interview_path,
        "-ss", str(avatar_duration),
        "-c:v", "libx264", "-c:a", "aac",
        "clip_b.mp4",
    ]

    subprocess.run(cmd_clip_a_video, check=True)
    subprocess.run(cmd_clip_b, check=True)

    # Concatena os dois clipes
    with open("concat_list.txt", "w") as f:
        f.write("file 'clip_a.mp4'\n")
        f.write("file 'clip_b.mp4'\n")

    cmd_concat = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", "concat_list.txt",
        "-c", "copy",
        output_path,
    ]
    subprocess.run(cmd_concat, check=True)

    return output_path


if __name__ == "__main__":
    compose_final_video(
        interview_path="interview_cut.mp4",
        avatar_path="output_avatar.mp4",
        output_path="final_video.mp4",
    )
    print("Vídeo final montado: final_video.mp4")
