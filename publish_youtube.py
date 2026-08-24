"""
publish_youtube.py

Publica o vídeo aprovado no YouTube via YouTube Data API v3.
Chamado apenas pelo workflow "check_approval.yml", depois que
telegram_approval.check_approvals() confirma um "approved: True".

Requer:
- Credenciais OAuth2 já autorizadas previamente (client_id, client_secret,
  refresh_token) salvas como Secrets do GitHub. A autorização inicial (tela
  de consentimento do Google) precisa ser feita manualmente uma vez, fora
  do pipeline — não dá pra automatizar o primeiro login.
"""

import os
import pickle
import google.oauth2.credentials
import googleapiclient.discovery
from googleapiclient.http import MediaFileUpload


def get_youtube_client():
    creds = google.oauth2.credentials.Credentials(
        token=None,
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"],
        client_id=os.environ["YOUTUBE_CLIENT_ID"],
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    return googleapiclient.discovery.build("youtube", "v3", credentials=creds)


def publish_video(
    video_path: str,
    thumbnail_path: str,
    title: str,
    description: str,
    tags: list,
    category_id: str = "25",  # 25 = "News & Politics"
    privacy_status: str = "public",
) -> str:
    """
    Faz upload do vídeo + thumbnail e retorna o video_id do YouTube.
    """
    youtube = get_youtube_client()

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    response = None
    while response is None:
        status, response = request.next_chunk()

    video_id = response["id"]

    youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path, mimetype="image/jpeg"),
    ).execute()

    return video_id


if __name__ == "__main__":
    vid = publish_video(
        video_path="final_video.mp4",
        thumbnail_path="thumbnail.jpg",
        title="Título de teste",
        description="Descrição de teste.",
        tags=["notícias", "entrevista"],
    )
    print(f"Publicado: https://youtube.com/watch?v={vid}")
