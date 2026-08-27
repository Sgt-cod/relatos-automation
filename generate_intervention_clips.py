"""
generate_intervention_clips.py

Gera um clipe de vídeo do personagem mascarado para CADA parte do
roteiro (abertura, cada intervenção crítica, despedida), usando
create_presenter_clip.create_presenter_clip. Cada clipe sorteia
independentemente um vídeo-base entre os disponíveis em
assets/presenter*.mp4 (pick_presenter_video), pra variar visualmente
entre as partes de um mesmo vídeo publicado.

Saída:
    opening_clip.mp4
    intervention_clip_0.mp4, intervention_clip_1.mp4, ...
    closing_clip.mp4
"""

from create_presenter_clip import create_presenter_clip, pick_presenter_video


def generate_all_clips(audios: dict) -> dict:
    print("  Gerando clipe da abertura...")
    opening_clip = create_presenter_clip(
        pick_presenter_video(), audios["opening_audio"], "opening_clip.mp4"
    )

    mid_clips = []
    for i, audio_path in enumerate(audios["mid_audios"]):
        clip_path = f"intervention_clip_{i}.mp4"
        create_presenter_clip(pick_presenter_video(), audio_path, clip_path)
        mid_clips.append(clip_path)

    print("  Gerando clipe da despedida...")
    closing_clip = create_presenter_clip(
        pick_presenter_video(), audios["closing_audio"], "closing_clip.mp4"
    )

    return {
        "opening_clip": opening_clip,
        "mid_clips": mid_clips,
        "closing_clip": closing_clip,
    }


if __name__ == "__main__":
    import json

    with open("interventions.json") as f:
        interventions = json.load(f)

    audios = {
        "opening_audio": "opening_audio.wav",
        "mid_audios": [f"intervention_audio_{i}.wav" for i in range(len(interventions["mid"]))],
        "closing_audio": "closing_audio.wav",
    }
    result = generate_all_clips(audios)
    print(f"Clipes gerados: {result}")
