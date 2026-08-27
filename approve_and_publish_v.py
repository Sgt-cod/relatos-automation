"""
approve_and_publish_v.py

Orquestração do pipeline do personagem mascarado (múltiplas
intervenções). Roda no mesmo job, do início ao fim:

1. Envia os N mini-roteiros (texto) + thumbnail pro Telegram, aprovação
   única (tudo ou nada) — os roteiros só fazem sentido como conjunto.
2. Se aprovado: gera o áudio de cada intervenção (Fish Audio), gera o
   clipe do personagem pra cada uma (vídeo local + áudio), compõe o
   vídeo final (trecho de destaque + intervenções intercaladas +
   moldura), publica no YouTube.
3. Se cancelado ou em timeout: encerra sem publicar nada (nem gera
   áudio/vídeo das intervenções — só roda depois de aprovado, pra não
   gastar chamadas de API à toa em roteiros rejeitados).
"""

import os
import sys
import json

from telegram_approval import TelegramApproval, send_scripts_for_approval, wait_for_scripts_approval
from generate_intervention_audios import generate_intervention_audios
from generate_intervention_clips import generate_intervention_clips
from compose_video import compose_video_with_interventions
from publish_youtube import publish_video

APPROVAL_TIMEOUT_SEC = int(os.environ.get("APPROVAL_TIMEOUT_MIN", "60")) * 60


def main():
    with open("video_id.txt") as f:
        video_id = f.read().strip()

    with open("source_meta.json") as f:
        source_meta = json.load(f)

    with open("interventions.json") as f:
        interventions = json.load(f)

    bot = TelegramApproval()

    send_scripts_for_approval(
        bot=bot,
        video_id=video_id,
        interventions=interventions,
        thumbnail_path="thumbnail.jpg",
    )

    result = wait_for_scripts_approval(bot=bot, video_id=video_id, timeout=APPROVAL_TIMEOUT_SEC)

    if result["decision"] != "approved":
        print(f"Publicação não realizada (decisão: {result['decision']}).")
        sys.exit(0)  # não é falha do workflow — é uma decisão válida do usuário

    print("✅ Aprovado! Gerando áudio de cada intervenção...")
    audio_paths = generate_intervention_audios(interventions)

    print("🎭 Gerando clipes do personagem...")
    clip_paths = generate_intervention_clips(audio_paths)

    interventions_with_clips = [
        {"timestamp_sec": it["timestamp_sec"], "clip_path": clip_path}
        for it, clip_path in zip(interventions, clip_paths)
    ]

    print("🎬 Compondo vídeo final...")
    compose_video_with_interventions(
        highlight_path="highlight_cut.mp4",
        interventions_with_clips=interventions_with_clips,
        output_path="final_video.mp4",
        clip_start_sec=source_meta["clip_start_sec"],
    )

    title = f"{source_meta['title']} | Análise"[:100]  # limite do YouTube
    topics = "; ".join(it["topic"] for it in interventions)
    description = (
        f"Comentários sobre: {topics}\n\n"
        f"Fonte: {source_meta['channel']}\n\n"
        f"Conteúdo com personagem de sátira gerado por IA."
    )

    print("📤 Publicando no YouTube...")
    youtube_video_id = publish_video(
        video_path="final_video.mp4",
        thumbnail_path="thumbnail.jpg",
        title=title,
        description=description,
        tags=["política", "sátira", "análise"],
    )

    video_url = f"https://youtube.com/watch?v={youtube_video_id}"
    print(f"Publicado: {video_url}")
    bot.send_message(f"🎉 Vídeo publicado!\n\n{video_url}")


if __name__ == "__main__":
    main()
