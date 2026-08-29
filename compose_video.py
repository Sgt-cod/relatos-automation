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

from pipeline_config import TARGET_FPS


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
            "-r", str(TARGET_FPS),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            "-c:a", "copy",  # áudio já está correto, só recopia
            "-shortest",  # encerra quando o vídeo (mais curto que a imagem em loop) terminar
            output_path,
        ],
        check=True,
    )
    return output_path


def get_video_resolution(path: str) -> tuple:
    """Retorna (largura, altura) do vídeo, via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-select_streams", "v:0",
        path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    stream = json.loads(result.stdout)["streams"][0]
    return int(stream["width"]), int(stream["height"])


def compose_video_with_interventions(
    highlight_path: str,
    opening_clip_path: str,
    mid_interventions_with_clips: list,
    closing_clip_path: str,
    output_path: str,
    clip_start_sec: float,
    moldura_path: str = "assets/moldura.png",
) -> str:
    """
    Monta o vídeo final: abertura -> trecho de destaque intercalado com
    as intervenções críticas -> despedida -> moldura por cima de tudo.

    TODAS as aparições do personagem (abertura, intervenções críticas,
    despedida) vão em TELA CHEIA — sem PiP, sem congelar frame do vídeo
    de base. O vídeo de destaque só aparece "puro" (tocando normalmente)
    nos intervalos ENTRE as aparições do personagem.

    Args:
        highlight_path: vídeo de destaque já cortado (highlight_cut.mp4).
        opening_clip_path: clipe do personagem se apresentando/cumprimentando.
        mid_interventions_with_clips: lista de dicts
            {"timestamp_sec": float (relativo ao VÍDEO ORIGINAL),
             "clip_path": str} — os pontos onde o vídeo de destaque corta
            pra uma intervenção em tela cheia do personagem, e depois
            volta a tocar normalmente de onde parou.
        closing_clip_path: clipe do personagem se despedindo.
        clip_start_sec: o quanto o highlight_path foi cortado a partir do
            vídeo original (source_meta["clip_start_sec"]) — usado pra
            converter os timestamps das intervenções pra tempo relativo
            ao highlight_path.
    """
    AUDIO_PARAMS = ["-ar", "48000", "-ac", "2", "-c:a", "aac", "-b:a", "192k"]

    target_w, target_h = get_video_resolution(highlight_path)

    def make_fullscreen_segment(clip_path: str, out_path: str) -> None:
        """Redimensiona o clipe do personagem pra ocupar a tela toda,
        mantendo a proporção original (letterbox se necessário) e
        casando com a resolução do vídeo de destaque."""
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", clip_path,
                "-vf",
                f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
                f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2,setsar=1",
                "-r", str(TARGET_FPS),
                "-pix_fmt", "yuv420p",
                "-c:v", "libx264",
                *AUDIO_PARAMS,
                out_path,
            ],
            check=True,
        )

    def make_base_segment(start_sec: float, out_path: str, duration_sec: float | None = None) -> None:
        """Corta um trecho do vídeo de destaque tocando normalmente."""
        cmd = ["ffmpeg", "-y", "-ss", str(start_sec), "-i", highlight_path]
        if duration_sec is not None:
            cmd += ["-t", str(duration_sec)]
        cmd += [
            "-r", str(TARGET_FPS),
            "-pix_fmt", "yuv420p",
            "-c:v", "libx264",
            *AUDIO_PARAMS,
            out_path,
        ]
        subprocess.run(cmd, check=True)

    highlight_duration = get_video_duration(highlight_path)

    # Converte timestamps para o tempo relativo ao highlight_path, e
    # ordena cronologicamente (defensivo — já deveria vir ordenado).
    items = sorted(mid_interventions_with_clips, key=lambda x: x["timestamp_sec"])
    rel_points = [
        max(0.0, min(highlight_duration, it["timestamp_sec"] - clip_start_sec))
        for it in items
    ]

    segment_files = []

    # --- Abertura em tela cheia ---
    opening_seg_path = "opening_seg.mp4"
    make_fullscreen_segment(opening_clip_path, opening_seg_path)
    segment_files.append(opening_seg_path)

    cursor = 0.0
    for i, (item, rel_ts) in enumerate(zip(items, rel_points)):
        # --- Trecho de base ANTES desta intervenção (vídeo tocando normal) ---
        base_duration = max(0.0, rel_ts - cursor)
        if base_duration > 0.3:  # ignora segmentos irrisórios (evita erro do ffmpeg com duração ~0)
            base_seg_path = f"base_seg_{i}.mp4"
            make_base_segment(cursor, base_seg_path, duration_sec=base_duration)
            segment_files.append(base_seg_path)

        # --- Intervenção em tela cheia ---
        intervention_seg_path = f"intervention_seg_{i}.mp4"
        make_fullscreen_segment(item["clip_path"], intervention_seg_path)
        segment_files.append(intervention_seg_path)

        cursor = rel_ts

    # --- Trecho de base final, depois da última intervenção ---
    final_duration = max(0.0, highlight_duration - cursor)
    if final_duration > 0.3:
        final_seg_path = "base_seg_final.mp4"
        make_base_segment(cursor, final_seg_path)
        segment_files.append(final_seg_path)

    # --- Despedida em tela cheia ---
    closing_seg_path = "closing_seg.mp4"
    make_fullscreen_segment(closing_clip_path, closing_seg_path)
    segment_files.append(closing_seg_path)

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
        "-r", str(TARGET_FPS),   # fps fixo — evita descompasso na concatenação final
        "-pix_fmt", "yuv420p",
        "-c:v", "libx264",
        *AUDIO_PARAMS,
        "clip_a.mp4",
    ]

    cmd_clip_b = [
        "ffmpeg", "-y",
        "-i", interview_path,
        "-ss", str(avatar_duration),
        "-r", str(TARGET_FPS),
        "-pix_fmt", "yuv420p",
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