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
import os


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


def apply_frame_overlay(
    video_path: str,
    output_path: str,
    moldura_path: str = "assets/moldura.png",
) -> str:
    """
    Sobrepõe a moldura (PNG com centro transparente) por cima do vídeo
    inteiro, do início ao fim — o vídeo aparece através do buraco
    transparente, e a moldura fica fixa por cima como borda/identidade
    visual do canal.

    Usa scale2ref para redimensionar a moldura automaticamente para o
    mesmo tamanho do vídeo, seja qual for a resolução (não fica hardcoded
    numa resolução específica).
    """
    if not os.path.exists(moldura_path):
        print(f"[compose_video] Aviso: moldura não encontrada em {moldura_path} — "
              f"vídeo final ficará sem moldura.")
        import shutil
        shutil.copyfile(video_path, output_path)
        return output_path

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", video_path,
            "-loop", "1", "-i", moldura_path,  # -loop 1: repete essa imagem estática por toda a duração
            "-filter_complex",
            "[1:v][0:v]scale2ref[frame][base];"  # redimensiona a moldura pro tamanho exato do vídeo
            "[base][frame]overlay=0:0:format=auto",
            "-c:v", "libx264",
            "-c:a", "copy",  # áudio já está correto, só recopia
            "-shortest",  # encerra quando o vídeo (mais curto que a imagem em loop) terminar
            output_path,
        ],
        check=True,
    )
    return output_path


def compose_video_with_interventions(
    highlight_path: str,
    interventions_with_clips: list,
    output_path: str,
    clip_start_sec: float,
    pip_scale: float = 1 / 6,
    pip_margin: int = 20,
    moldura_path: str = "assets/moldura.png",
) -> str:
    """
    Monta o vídeo final intercalando o trecho de destaque com N
    intervenções do personagem: base -> intervenção -> base ->
    intervenção -> ... -> base final.

    Em cada intervenção, o vídeo de base CONGELA num frame parado (não
    fica mudo tocando por baixo — a ideia aqui é uma "pausa" pra comentário,
    diferente do desenho anterior de PiP sobre vídeo rodando) e o
    personagem aparece em PiP por cima, falando o áudio daquele trecho.

    Args:
        highlight_path: vídeo de destaque já cortado (highlight_cut.mp4).
        interventions_with_clips: lista de dicts
            {"timestamp_sec": float (relativo ao VÍDEO ORIGINAL),
             "clip_path": str (caminho do intervention_clip_N.mp4)},
            em qualquer ordem — a função ordena por timestamp internamente.
        clip_start_sec: o quanto o highlight_path foi cortado a partir do
            vídeo original (source_meta["clip_start_sec"]) — usado pra
            converter os timestamps das intervenções pra tempo relativo
            ao highlight_path.
    """
    AUDIO_PARAMS = ["-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k"]

    highlight_duration = get_video_duration(highlight_path)

    # Converte timestamps para o tempo relativo ao highlight_path, e
    # ordena cronologicamente (defensivo — já deveria vir ordenado).
    items = sorted(interventions_with_clips, key=lambda x: x["timestamp_sec"])
    rel_points = [
        max(0.0, min(highlight_duration, it["timestamp_sec"] - clip_start_sec))
        for it in items
    ]

    segment_files = []
    cursor = 0.0

    for i, (item, rel_ts) in enumerate(zip(items, rel_points)):
        # --- Segmento de base ANTES desta intervenção ---
        base_duration = max(0.0, rel_ts - cursor)
        if base_duration > 0.3:  # ignora segmentos irrisórios (evita erro do ffmpeg com duração ~0)
            base_seg_path = f"base_seg_{i}.mp4"
            subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(cursor),
                    "-i", highlight_path,
                    "-t", str(base_duration),
                    "-c:v", "libx264",
                    *AUDIO_PARAMS,
                    base_seg_path,
                ],
                check=True,
            )
            segment_files.append(base_seg_path)

        # --- Segmento de intervenção: frame congelado + PiP do personagem ---
        frame_path = f"freeze_frame_{i}.jpg"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(rel_ts),
                "-i", highlight_path,
                "-frames:v", "1",
                "-q:v", "2",
                frame_path,
            ],
            check=True,
        )

        clip_duration = get_video_duration(item["clip_path"])
        intervention_seg_path = f"intervention_seg_{i}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1", "-i", frame_path,       # [0] frame congelado, em loop
                "-i", item["clip_path"],               # [1] clipe do personagem (vídeo + áudio)
                "-filter_complex",
                f"[1:v]scale=iw*{pip_scale}:ih*{pip_scale}[pip];"
                f"[0:v][pip]overlay=x={pip_margin}:y={pip_margin}[vout]",
                "-map", "[vout]",
                "-map", "1:a",
                "-t", str(clip_duration),
                "-c:v", "libx264",
                *AUDIO_PARAMS,
                intervention_seg_path,
            ],
            check=True,
        )
        segment_files.append(intervention_seg_path)

        cursor = rel_ts

    # --- Segmento final de base, depois da última intervenção ---
    final_duration = max(0.0, highlight_duration - cursor)
    if final_duration > 0.3:
        final_seg_path = "base_seg_final.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-ss", str(cursor),
                "-i", highlight_path,
                "-c:v", "libx264",
                *AUDIO_PARAMS,
                final_seg_path,
            ],
            check=True,
        )
        segment_files.append(final_seg_path)

    # --- Concatena todos os segmentos, na ordem ---
    with open("concat_list.txt", "w") as f:
        for seg in segment_files:
            f.write(f"file '{seg}'\n")

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", "concat_list.txt",
            "-c", "copy",
            "concat_no_frame.mp4",
        ],
        check=True,
    )

    # Última etapa: aplica a moldura por cima do vídeo já concatenado
    apply_frame_overlay("concat_no_frame.mp4", output_path, moldura_path=moldura_path)

    return output_path


def compose_final_video(
    interview_path: str,
    avatar_path: str,
    output_path: str,
    pip_scale: float = 1 / 6,
    pip_margin: int = 20,
    moldura_path: str = "assets/moldura.png",
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

    # Estratégia: gerar dois clipes separados e concatenar, em vez de um
    # único filtro condicional por tempo (mais simples e evita edge cases
    # de sincronismo):
    # 1. Clipe A = entrevista muda (0 a avatar_duration) + áudio do avatar, com o avatar em PiP
    # 2. Clipe B = entrevista original a partir de avatar_duration até o fim
    # 3. Concatena A + B
    #
    # IMPORTANTE: o concat demuxer do ffmpeg com "-c copy" exige que os
    # dois clipes tenham exatamente os MESMOS parâmetros de áudio (taxa de
    # amostragem, canais, codec) — como o áudio do clipe A vem do Fish
    # Audio/SadTalker e o do clipe B vem da entrevista original, eles
    # costumam ter parâmetros diferentes por padrão. Sem forçar os dois a
    # usarem os mesmos parâmetros aqui, um dos trechos pode sair mudo na
    # concatenação final. Por isso ambos os comandos abaixo fixam
    # explicitamente -ar/-ac/-c:a.
    AUDIO_PARAMS = ["-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k"]

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
        "-c:v", "libx264",
        *AUDIO_PARAMS,
        "clip_a.mp4",
    ]

    cmd_clip_b = [
        "ffmpeg", "-y",
        "-i", interview_path,
        "-ss", str(avatar_duration),
        "-c:v", "libx264",
        *AUDIO_PARAMS,
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
        "concat_no_frame.mp4",
    ]
    subprocess.run(cmd_concat, check=True)

    # Última etapa: aplica a moldura por cima do vídeo já concatenado
    apply_frame_overlay("concat_no_frame.mp4", output_path, moldura_path=moldura_path)

    return output_path


if __name__ == "__main__":
    compose_final_video(
        interview_path="highlight_cut.mp4",
        avatar_path="output_avatar.mp4",
        output_path="final_video.mp4",
    )
    print("Vídeo final montado: final_video.mp4")
