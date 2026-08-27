"""
generate_intervention_audios.py

Gera um arquivo de áudio por intervenção em interventions.json, usando o
Fish Audio (reaproveita generate_audio.generate_audio). Roda só DEPOIS
da aprovação no Telegram, pra não gastar chamadas de API à toa em
roteiros que podem ser rejeitados.

Saída: intervention_audio_0.wav, intervention_audio_1.wav, ...
(uma pra cada item de interventions.json, na mesma ordem).
"""

import os
import json

from generate_audio import generate_audio


def generate_intervention_audios(interventions: list) -> list:
    voice_id = os.environ["FISH_AUDIO_VOICE_ID"]
    audio_paths = []

    for i, intervention in enumerate(interventions):
        audio_path = f"intervention_audio_{i}.wav"
        print(f"  Gerando áudio {i + 1}/{len(interventions)}: \"{intervention['script_text'][:60]}...\"")
        generate_audio(
            script_text=intervention["script_text"],
            voice_id=voice_id,
            output_path=audio_path,
        )
        audio_paths.append(audio_path)

    return audio_paths


if __name__ == "__main__":
    with open("interventions.json") as f:
        interventions = json.load(f)

    paths = generate_intervention_audios(interventions)
    print(f"{len(paths)} áudios de intervenção gerados: {paths}")
