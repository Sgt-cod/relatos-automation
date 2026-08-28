"""
approve_compose_publish.py

Último passo do workflow (roda no MESMO job de tudo o resto, sem
depender de um segundo workflow agendado):

1. Envia vídeo do avatar + thumbnail pro Telegram, com botões de
   aprovação individuais.
2. Espera (bloqueante, dentro deste mesmo processo) até 1h por padrão
   — configurável via env var APPROVAL_TIMEOUT_SEC.
3. Se APROVADO (ambos os itens, originais ou substitutos enviados pelo
   usuário): compõe o vídeo final (ffmpeg) e publica no YouTube.
4. Se CANCELADO ou em TIMEOUT: encerra sem publicar nada. Timeout aqui
   significa cancelar, não publicar automaticamente — dado que o
   conteúdo é sensível (entrevista/notícia política), publicar sem
   revisão humana não é o comportamento desejado.
"""

import os
import sys
import json

from telegram_approval import TelegramApproval, send_for_approval, wait_for_approval
from compose_video import compose_final_video
from publish_youtube import publish_video

APPROVAL_TIMEOUT_SEC = int(os.environ.get("APPROVAL_TIMEOUT_MIN", "60")) * 60


def main():
    with open("script.txt") as f:
        script_text = f.read().strip()

    with open("video_id.txt") as f:
        video_id = f.read().strip()

    with open("source_meta.json") as f:
        source_meta = json.load(f)

    bot = TelegramApproval()

    send_for_approval(
        bot=bot,
        video_id=video_id,
        script_text=script_text,
        avatar_video_path="output_avatar.mp4",
        thumbnail_path="thumbnail.jpg",
    )

    result = wait_for_approval(
        bot=bot,
        video_id=video_id,
        avatar_video_path="output_avatar.mp4",
        thumbnail_path="thumbnail.jpg",
        timeout=APPROVAL_TIMEOUT_SEC,
    )

    if result["decision"] != "approved":
        print(f"Publicação não realizada (decisão: {result['decision']}).")
        sys.exit(0)  # não é uma falha do workflow — é uma decisão válida do usuário

    print("✅ Aprovado! Compondo vídeo final...")
    compose_final_video(
        interview_path="highlight_cut.mp4",
        avatar_path=result["video_path"],
        output_path="final_video.mp4",
    )

    title = f"{source_meta['title']} | Análise"[:100]  # limite do YouTube
    description = (
        f"{script_text}\n\n"
        f"Fonte: {source_meta['channel']}\n\n"
        f"Vídeo gerado com auxílio de IA."
    )

    print("📤 Publicando no YouTube...")
    youtube_video_id = publish_video(
        video_path="final_video.mp4",
        thumbnail_path=result["thumbnail_path"],
        title=title,
        description=description,
        tags=["notícias", "entrevista", "análise"],
    )

    video_url = f"https://youtube.com/watch?v={youtube_video_id}"
    print(f"Publicado: {video_url}")
    bot.send_message(f"🎉 Vídeo publicado!\n\n{video_url}")


if __name__ == "__main__":
    main()
