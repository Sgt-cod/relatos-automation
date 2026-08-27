"""
generate_intervention_audios.py

Gera um arquivo de áudio para CADA parte do roteiro (abertura, cada
intervenção crítica, despedida), usando o Fish Audio (reaproveita
generate_audio.generate_audio). Roda só DEPOIS da aprovação no Telegram,
pra não gastar chamadas de API à toa em roteiros que podem ser rejeitados.

Saída:
    opening_audio.wav
    intervention_audio_0.wav, intervention_audio_1.wav, ... (uma por item de interventions["mid"])
    closing_audio.wav
"""

import os
import json

from generate_audio import generate_audio


def generate_all_audios(interventions: dict) -> dict:
    voice_id = os.environ["FISH_AUDIO_VOICE_ID"]

    print("  Gerando áudio da abertura...")
    generate_audio(
        script_text=interventions["opening"]["script_text"],
        voice_id=voice_id,
        output_path="opening_audio.wav",
    )

    mid_audio_paths = []
    for i, intervention in enumerate(interventions["mid"]):
        audio_path = f"intervention_audio_{i}.wav"
        print(f"  Gerando áudio {i + 1}/{len(interventions['mid'])}: "
              f"\"{intervention['script_text'][:60]}...\"")
        generate_audio(
            script_text=intervention["script_text"],
            voice_id=voice_id,
            output_path=audio_path,
        )
        mid_audio_paths.append(audio_path)

    print("  Gerando áudio da despedida...")
    generate_audio(
        script_text=interventions["closing"]["script_text"],
        voice_id=voice_id,
        output_path="closing_audio.wav",
    )

    return {
        "opening_audio": "opening_audio.wav",
        "mid_audios": mid_audio_paths,
        "closing_audio": "closing_audio.wav",
    }


if __name__ == "__main__":
    with open("interventions.json") as f:
        interventions = json.load(f)

    result = generate_all_audios(interventions)
    print(f"Áudios gerados: {result}")
