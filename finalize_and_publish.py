"""
finalize_and_publish.py

Chamado pelo check_approval.yml quando telegram_approval.check_approvals()
confirma que TANTO o vídeo do avatar QUANTO a thumbnail foram aprovados
(originais ou substitutos enviados pelo usuário).

1. Lê pending/{video_id}.json (estado + URLs).
2. Baixa: corte da entrevista, vídeo do avatar (override se houver) e
   thumbnail (override se houver).
3. Compõe o vídeo final (ffmpeg, PiP) com compose_video.py.
4. Publica no YouTube com publish_youtube.py.
5. Remove pending/{video_id}.json (processo concluído).
"""

import os
import json

from github_storage import download_file
from compose_video import compose_final_video
from publish_youtube import publish_video

PENDING_DIR = "pending"


def finalize_and_publish(video_id: str) -> None:
    pending_path = os.path.join(PENDING_DIR, f"{video_id}.json")
    with open(pending_path) as f:
        state = json.load(f)

    print(f"Finalizando publicação de {video_id}...")

    download_file(state["interview_url"], "interview_cut.mp4")

    avatar_url = state.get("video_override_url") or state["avatar_video_url"]
    download_file(avatar_url, "output_avatar.mp4")

    thumb_url = state.get("thumb_override_url") or state["thumbnail_url"]
    thumb_ext = ".png" if thumb_url.lower().endswith(".png") else ".jpg"
    thumbnail_path = f"thumbnail_final{thumb_ext}"
    download_file(thumb_url, thumbnail_path)

    compose_final_video(
        interview_path="interview_cut.mp4",
        avatar_path="output_avatar.mp4",
        output_path="final_video.mp4",
    )

    title = f"{state['source_title']} | Análise"
    description = (
        f"{state['script_text']}\n\n"
        f"Fonte: {state['source_channel']}\n\n"
        f"Vídeo gerado com auxílio de IA."
    )

    youtube_video_id = publish_video(
        video_path="final_video.mp4",
        thumbnail_path=thumbnail_path,
        title=title[:100],  # limite do YouTube para títulos
        description=description,
        tags=["notícias", "entrevista", "análise"],
    )

    print(f"Publicado: https://youtube.com/watch?v={youtube_video_id}")

    os.remove(pending_path)


if __name__ == "__main__":
    with open("approved_video_id.txt") as f:
        video_id = f.read().strip()

    finalize_and_publish(video_id)
