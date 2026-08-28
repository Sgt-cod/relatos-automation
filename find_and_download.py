"""
find_and_download.py

Passo 1 do generate.yml:
1. Busca vídeos políticos recentes (entrevistas, discursos, debates,
   coletivas etc.) nos canais configurados (YouTube Data API v3).
2. Escolhe o primeiro candidato ainda não processado.
3. Baixa o vídeo (yt-dlp).
4. Transcreve com timestamps (faster-whisper, roda em CPU).
5. Pede pro Gemini apontar a JANELA de destaque (não mais um único
   momento) com o conteúdo político mais denso do vídeo.
6. Corta essa janela com ffmpeg, gerando highlight_cut.mp4 — é dentro
   dela que find_intervention_moments.py depois escolhe os pontos
   específicos de intervenção do personagem.
7. Salva video_id.txt (usado pelos passos seguintes) e marca o vídeo
   como processado em state/processed_videos.json.

Saídas usadas pelos próximos passos do workflow:
    highlight_cut.mp4   -> corte da janela de destaque
    transcript.json      -> transcrição completa com timestamps
    video_id.txt          -> identificador único usado no pipeline inteiro
    source_meta.json      -> título/canal/URL do vídeo original + janela
                             de destaque (para os próximos passos)
"""

import os
import json
import subprocess
import hashlib
from datetime import datetime, timedelta, timezone

import requests

from pipeline_config import (
    CHANNELS,
    SEARCH_KEYWORDS,
    MAX_VIDEO_AGE_DAYS,
    MIN_SOURCE_DURATION_SEC,
    MAX_SOURCE_DURATION_SEC,
    HIGHLIGHT_DURATION_SEC,
    STATE_DIR,
    PROCESSED_VIDEOS_FILE,
)
from gemini_client import call_gemini

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


# ---------------------------------------------------------------------------
# 1-2. Busca e seleção de candidato
# ---------------------------------------------------------------------------

def _load_processed() -> set:
    if os.path.exists(PROCESSED_VIDEOS_FILE):
        with open(PROCESSED_VIDEOS_FILE) as f:
            return set(json.load(f))
    return set()


def _save_processed(processed: set) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(PROCESSED_VIDEOS_FILE, "w") as f:
        json.dump(sorted(processed), f)


def _search_channel(channel_id: str, keyword: str, published_after: str) -> list:
    params = {
        "key": YOUTUBE_API_KEY,
        "channelId": channel_id,
        "q": keyword,
        "type": "video",
        "order": "date",
        "publishedAfter": published_after,
        "maxResults": 10,
        "part": "snippet",
    }
    resp = requests.get(YOUTUBE_SEARCH_URL, params=params, timeout=30)
    resp.raise_for_status()
    items = resp.json().get("items", [])

    # Filtra transmissões AO VIVO ou AGENDADAS — a busca ampliada (discursos,
    # sessões, coletivas etc.) traz bem mais lives do que a busca original
    # só por "entrevista". Baixar uma live em andamento não faz sentido
    # (duração indefinida), e o YouTube reporta a duração dela de um jeito
    # ("P0D") que nem é uma duração normal — melhor já descartar aqui.
    return [
        item for item in items
        if item["snippet"].get("liveBroadcastContent", "none") == "none"
    ]


def _get_video_duration_sec(video_id: str) -> int:
    resp = requests.get(
        YOUTUBE_VIDEOS_URL,
        params={"key": YOUTUBE_API_KEY, "id": video_id, "part": "contentDetails"},
        timeout=15,
    )
    resp.raise_for_status()
    items = resp.json().get("items", [])
    if not items:
        return 0
    iso_duration = items[0]["contentDetails"]["duration"]  # ex.: "PT12M34S"
    return _parse_iso8601_duration(iso_duration)


def _parse_iso8601_duration(iso_duration: str) -> int:
    import re
    match = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration)
    if not match or not any(match.groups()):
        # Formatos fora do padrão "PTxxHxxMxxS" (ex.: "P0D", usado pelo
        # YouTube pra transmissões ao vivo/agendadas) não são uma duração
        # de verdade — trata como 0, que o filtro de duração mínima já
        # descarta naturalmente, em vez de derrubar o script inteiro.
        return 0
    h, m, s = (int(g) if g else 0 for g in match.groups())
    return h * 3600 + m * 60 + s


def find_candidate_video() -> dict:
    """Percorre os canais configurados e devolve o primeiro candidato novo."""
    processed = _load_processed()
    published_after = (
        datetime.now(timezone.utc) - timedelta(days=MAX_VIDEO_AGE_DAYS)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")

    for channel_name, channel_id in CHANNELS.items():
        if channel_id == "CHANNEL_ID_AQUI":
            continue  # canal ainda não configurado

        for keyword in SEARCH_KEYWORDS:
            items = _search_channel(channel_id, keyword, published_after)
            for item in items:
                video_id = item["id"]["videoId"]
                if video_id in processed:
                    continue

                duration = _get_video_duration_sec(video_id)
                if not (MIN_SOURCE_DURATION_SEC <= duration <= MAX_SOURCE_DURATION_SEC):
                    continue

                return {
                    "video_id": video_id,
                    "channel": channel_name,
                    "title": item["snippet"]["title"],
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "duration_sec": duration,
                }

    raise RuntimeError("Nenhum vídeo novo encontrado nos canais configurados.")


# ---------------------------------------------------------------------------
# 3. Download
# ---------------------------------------------------------------------------

def download_video(youtube_url: str, output_path: str = "source_video.mp4") -> str:
    cmd = ["yt-dlp"]

    # Se houver cookies exportados de uma sessão logada, usa — necessário
    # porque o YouTube costuma bloquear downloads vindos de IPs de
    # datacenter (como os runners do GitHub Actions) com a mensagem
    # "Sign in to confirm you're not a bot".
    if os.path.exists("cookies.txt"):
        cmd += ["--cookies", "cookies.txt"]

    cmd += [
        "--remote-components", "ejs:github",  # autoriza o yt-dlp a baixar o script auxiliar (do próprio GitHub) que resolve o desafio de JS do YouTube
        "-f", "b[ext=mp4]/bv[ext=mp4]+ba[ext=m4a]/mp4",  # evita o aviso de formato e cobre mais casos
        "-o", output_path,
        youtube_url,
    ]
    subprocess.run(cmd, check=True)
    return output_path


# ---------------------------------------------------------------------------
# 4. Transcrição com timestamps
# ---------------------------------------------------------------------------

def transcribe(video_path: str) -> list:
    """
    Transcreve o vídeo com faster-whisper (modelo "base", CPU).
    Retorna lista de segmentos: [{"start": float, "end": float, "text": str}, ...]
    """
    from faster_whisper import WhisperModel

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(video_path, language="pt")

    result = [
        {"start": seg.start, "end": seg.end, "text": seg.text.strip()}
        for seg in segments
    ]
    with open("transcript.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return result


# ---------------------------------------------------------------------------
# 5. Identificar a melhor janela de destaque via Gemini
# ---------------------------------------------------------------------------

def find_highlight_window(transcript: list, target_duration_sec: float) -> dict:
    """
    Envia a transcrição completa (com timestamps) para o Gemini e pede a
    janela CONTÍNUA de ~target_duration_sec com o conteúdo político mais
    denso/relevante do vídeo (declarações fortes, contradições, embates,
    pontos que rendem boa análise) — não precisa ser um único confronto,
    é a "melhor parte" do vídeo como um todo, de onde depois vamos tirar
    vários momentos específicos para o personagem comentar.
    Retorna {"start_sec": float, "end_sec": float, "reason": str}.
    """
    transcript_text = "\n".join(
        f"[{seg['start']:.0f}s] {seg['text']}" for seg in transcript
    )

    prompt = (
        "Você vai analisar a transcrição de um vídeo político (entrevista, "
        "discurso, debate, coletiva, sessão legislativa etc.), com "
        "marcações de tempo em segundos. Identifique a janela CONTÍNUA de "
        f"aproximadamente {target_duration_sec:.0f} segundos com o "
        "conteúdo mais denso e relevante do vídeo — declarações fortes, "
        "contradições, embates, promessas, dados citados, pontos "
        "polêmicos ou que renderiam boa análise crítica. Não precisa ser "
        "um único confronto isolado; pode ser o trecho com mais MOMENTOS "
        "interessantes juntos.\n\n"
        "Responda APENAS em JSON, no formato exato:\n"
        '{"start_sec": <número>, "end_sec": <número>, '
        '"reason": "<explicação breve, 1-2 frases>"}\n\n'
        "Transcrição:\n" + transcript_text
    )

    resp_text = call_gemini(prompt, GEMINI_API_KEY)

    # Remove possíveis cercas de código (```json ... ```) antes de parsear
    cleaned = resp_text.strip().strip("`").replace("json\n", "", 1)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# 6. Corte com ffmpeg
# ---------------------------------------------------------------------------

def cut_highlight(
    video_path: str,
    start_sec: float,
    end_sec: float,
    total_duration_sec: float,
    output_path: str = "highlight_cut.mp4",
    target_duration_sec: float = HIGHLIGHT_DURATION_SEC,
) -> dict:
    """
    Corta a janela de destaque identificada pelo Gemini. Se a janela
    devolvida for menor que target_duration_sec, estica um pouco pros dois
    lados (sem passar dos limites do vídeo original) pra aproveitar melhor
    o tempo de transcrição já feito.

    Retorna {"output_path", "start_sec", "end_sec"} — o start_sec é usado
    depois (generate_thumbnail.py, find_intervention_moments.py) para
    converter timestamps do vídeo original para timestamps relativos ao
    CLIPE JÁ CORTADO.
    """
    start = max(0, start_sec)
    end = min(total_duration_sec, end_sec)

    if end - start < target_duration_sec:
        missing = target_duration_sec - (end - start)
        start = max(0, start - missing / 2)
        end = min(total_duration_sec, end + missing / 2)

    subprocess.run(
        [
            "ffmpeg", "-y",
            "-ss", str(start),
            "-i", video_path,
            "-t", str(end - start),
            "-c:v", "libx264", "-c:a", "aac",
            output_path,
        ],
        check=True,
    )
    return {"output_path": output_path, "start_sec": start, "end_sec": end}


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def main():
    candidate = find_candidate_video()
    print(f"Candidato selecionado: {candidate['title']} ({candidate['channel']})")

    download_video(candidate["url"])
    transcript = transcribe("source_video.mp4")

    highlight_window = find_highlight_window(transcript, HIGHLIGHT_DURATION_SEC)
    print(f"Janela de destaque identificada: {highlight_window}")

    cut_result = cut_highlight(
        video_path="source_video.mp4",
        start_sec=highlight_window["start_sec"],
        end_sec=highlight_window["end_sec"],
        total_duration_sec=candidate["duration_sec"],
    )

    # video_id interno do pipeline (não confundir com o ID do YouTube fonte)
    internal_id = "video_" + hashlib.sha1(
        candidate["video_id"].encode() + datetime.now().isoformat().encode()
    ).hexdigest()[:10]

    with open("video_id.txt", "w") as f:
        f.write(internal_id)

    with open("source_meta.json", "w") as f:
        json.dump(
            {
                **candidate,
                "highlight_window": highlight_window,
                "clip_start_sec": cut_result["start_sec"],
            },
            f, ensure_ascii=False, indent=2,
        )

    processed = _load_processed()
    processed.add(candidate["video_id"])
    _save_processed(processed)

    print(f"Corte pronto: highlight_cut.mp4 (id interno: {internal_id})")


if __name__ == "__main__":
    main()
