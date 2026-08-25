"""
send_approval_request.py

Passo de wiring chamado pelo generate.yml: sobe o vídeo do avatar, a
thumbnail e o corte da entrevista como release assets (URLs
permanentes, para o Workflow B conseguir baixar depois de aprovado), e
então envia os dois itens (vídeo + thumbnail) para aprovação individual
no Telegram.
"""

import json

from github_storage import upload_to_github_release
from telegram_approval import send_for_approval

if __name__ == "__main__":
    with open("script.txt") as f:
        script_text = f.read().strip()

    with open("video_id.txt") as f:
        video_id = f.read().strip()

    with open("source_meta.json") as f:
        source_meta = json.load(f)

    avatar_video_url = upload_to_github_release(
        "output_avatar.mp4", f"{video_id}_avatar.mp4"
    )
    thumbnail_url = upload_to_github_release(
        "thumbnail.jpg", f"{video_id}_thumbnail.jpg"
    )
    interview_url = upload_to_github_release(
        "interview_cut.mp4", f"{video_id}_interview.mp4"
    )

    send_for_approval(
        video_id=video_id,
        script_text=script_text,
        avatar_video_path="output_avatar.mp4",
        thumbnail_path="thumbnail.jpg",
        avatar_video_url=avatar_video_url,
        thumbnail_url=thumbnail_url,
        interview_url=interview_url,
        source_title=source_meta["title"],
        source_channel=source_meta["channel"],
    )

    print(f"Pedido de aprovação (vídeo + thumbnail) enviado para {video_id}.")
