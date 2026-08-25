"""
find_and_download.py

Passo 1 do generate.yml:
1. Busca vídeos recentes de entrevista nos canais configurados
   (YouTube Data API v3 — search.list).
2. Escolhe o primeiro candidato ainda não processado.
3. Baixa o vídeo (yt-dlp).
4. Transcreve com timestamps (faster-whisper, roda em CPU).
5. Pede pro Gemini apontar o trecho de maior tensão/divergência na
   transcrição (retorna start/end em segundos).
6. Corta esse trecho com ffmpeg, gerando ~6-7 min de clipe
   (interview_cut.mp4), com padding ao redor do ponto identificado.
7. Salva video_id.txt (usado pelos passos seguintes) e marca o vídeo
   como processado em state/processed_videos.json.

Saídas usadas pelos próximos passos do workflow:
    interview_cut.mp4   -> corte final da entrevista
    transcript.json      -> transcrição completa com timestamps
    video_id.txt          -> identificador único usado no pipeline inteiro
    source_meta.json      -> título/canal/URL do vídeo original (para
                             descrição do YouTube e contexto do roteiro)
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
    CLIP_DURATION_SEC,
    STATE_DIR,
    PROCESSED_VIDEOS_FILE,
)

YOUTUBE_API_KEY = os.environ["YOUTUBE_API_KEY"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "gemini-2.0-flash:generateContent"
)


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
    return resp.json().get("items", [])


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
# 5. Identificar trecho de tensão via Gemini
# ---------------------------------------------------------------------------

def find_tense_moment(transcript: list) -> dict:
    """
    Envia a transcrição (com timestamps) para o Gemini e pede o ponto
    central do trecho mais tenso/de maior divergência entre os
    participantes. Retorna {"center_sec": float, "reason": str}.
    """
    transcript_text = "\n".join(
        f"[{seg['start']:.0f}s] {seg['text']}" for seg in transcript
    )

    prompt = (
        "Você vai analisar a transcrição de uma entrevista, com marcações "
        "de tempo em segundos. Identifique o momento de MAIOR tensão, "
        "divergência ou confronto entre os participantes (ex.: pergunta "
        "difícil, resposta evasiva, discordância explícita, interrupção). "
        "Responda APENAS em JSON, no formato exato:\n"
        '{"center_sec": <número>, "reason": "<explicação breve, 1 frase>"}\n\n'
        "Transcrição:\n" + transcript_text
    )

    resp = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    resp.raise_for_status()
    raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]

    # Remove possíveis cercas de código (```json ... ```) antes de parsear
    cleaned = raw_text.strip().strip("`").replace("json\n", "", 1)
    return json.loads(cleaned)


# ---------------------------------------------------------------------------
# 6. Corte com ffmpeg
# ---------------------------------------------------------------------------

def cut_clip(
    video_path: str,
    center_sec: float,
    total_duration_sec: float,
    output_path: str = "interview_cut.mp4",
    clip_duration_sec: float = CLIP_DURATION_SEC,
) -> str:
    half = clip_duration_sec / 2
    start = max(0, center_sec - half)
    end = min(total_duration_sec, center_sec + half)

    # Se bateu numa borda, estica pro outro lado para manter a duração alvo
    if end - start < clip_duration_sec:
        if start == 0:
            end = min(total_duration_sec, clip_duration_sec)
        elif end == total_duration_sec:
            start = max(0, total_duration_sec - clip_duration_sec)

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
    return output_path


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------

def main():
    candidate = find_candidate_video()
    print(f"Candidato selecionado: {candidate['title']} ({candidate['channel']})")

    download_video(candidate["url"])
    transcript = transcribe("source_video.mp4")

    tense_moment = find_tense_moment(transcript)
    print(f"Trecho de tensão identificado: {tense_moment}")

    cut_clip(
        video_path="source_video.mp4",
        center_sec=tense_moment["center_sec"],
        total_duration_sec=candidate["duration_sec"],
    )

    # video_id interno do pipeline (não confundir com o ID do YouTube fonte)
    internal_id = "video_" + hashlib.sha1(
        candidate["video_id"].encode() + datetime.now().isoformat().encode()
    ).hexdigest()[:10]

    with open("video_id.txt", "w") as f:
        f.write(internal_id)

    with open("source_meta.json", "w") as f:
        json.dump({**candidate, "tense_moment": tense_moment}, f, ensure_ascii=False, indent=2)

    processed = _load_processed()
    processed.add(candidate["video_id"])
    _save_processed(processed)

    print(f"Corte pronto: interview_cut.mp4 (id interno: {internal_id})")


if __name__ == "__main__":
    main()
