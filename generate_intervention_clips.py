"""
generate_intervention_clips.py

Gera um clipe de vídeo do personagem mascarado por áudio de intervenção,
usando create_presenter_clip.create_presenter_clip (mesmo vídeo-base
assets/presenter.mp4 já usado no resto do pipeline).

Saída: intervention_clip_0.mp4, intervention_clip_1.mp4, ...
"""

from create_presenter_clip import create_presenter_clip


def generate_intervention_clips(audio_paths: list, presenter_path: str = "assets/presenter.mp4") -> list:
    clip_paths = []
    for i, audio_path in enumerate(audio_paths):
        clip_path = f"intervention_clip_{i}.mp4"
        create_presenter_clip(presenter_path, audio_path, clip_path)
        clip_paths.append(clip_path)
    return clip_paths


if __name__ == "__main__":
    import json

    with open("interventions.json") as f:
        interventions = json.load(f)

    audio_paths = [f"intervention_audio_{i}.wav" for i in range(len(interventions))]
    clip_paths = generate_intervention_clips(audio_paths)
    print(f"{len(clip_paths)} clipes de intervenção gerados: {clip_paths}")
