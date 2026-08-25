"""
modal_avatar.py

Função serverless na Modal que roda o SadTalker para gerar um vídeo de avatar
com lipsync, a partir de uma imagem estática (assets/avatar.png) e um áudio
(gerado pelo Fish Audio a partir do roteiro do Gemini).

Uso:
    modal deploy modal_avatar.py      # publica o endpoint
    modal run modal_avatar.py         # testa localmente disparando uma vez

O endpoint fica exposto como URL HTTPS, que o GitHub Actions chama via POST.
"""

import modal

app = modal.App("avatar-lipsync")

# Imagem do container: instala SadTalker e dependências.
# SadTalker precisa de torch + ffmpeg + dlib/face-alignment.
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install("ffmpeg", "libgl1", "git", "build-essential", "wget", "unzip")
    # Estágio 1: numpy fixado ANTES do resto — vários pacotes desse ecossistema
    # (face-alignment, gfpgan, resampy) ainda não são compatíveis com numpy 2.x
    # e falham no build se o resolvedor do pip escolher a versão mais nova.
    .pip_install("numpy<2", "setuptools", "wheel")
    # Estágio 2: torch primeiro e sozinho — pacote pesado, isolar reduz
    # chance de conflito de resolução com o restante.
    .pip_install("torch", "torchvision", "torchaudio")
    # Estágio 3: o restante das dependências do SadTalker
    .pip_install(
        "face-alignment",
        "imageio",
        "imageio-ffmpeg",
        "librosa",
        "resampy",
        "pydub",
        "scipy",
        "kornia",
        "yacs",
        "gfpgan",
        "safetensors",
    )
    # Estágio 4: a Modal exige que o FastAPI seja instalado explicitamente
    # na imagem para funções que usam @modal.fastapi_endpoint.
    .pip_install("fastapi[standard]")
    .run_commands(
        # Reforça o pin do numpy<2 como ÚLTIMA palavra, depois de todas as
        # instalações acima. Cada .pip_install() é uma chamada de pip
        # separada, e alguma das etapas anteriores (torch, kornia, gfpgan
        # etc.) pode ter puxado numpy 2.x como dependência transitiva,
        # sobrescrevendo o pin original — o SadTalker usa uma API do numpy
        # (np.VisibleDeprecationWarning) que só existe na série 1.x.
        "pip install 'numpy<2' --force-reinstall --no-deps",
        "git clone https://github.com/OpenTalker/SadTalker.git /sadtalker",
        "cd /sadtalker && bash scripts/download_models.sh || true",
        # Pré-baixa os pesos auxiliares (face-alignment e GFPGAN) durante o
        # BUILD da imagem, não em tempo de execução. Sem isso, a primeira
        # chamada de cada worker novo baixaria ~400MB extras sob demanda,
        # o que é uma causa comum de execuções lentas/instáveis.
        "python -c \"import face_alignment; face_alignment.FaceAlignment(face_alignment.LandmarksType.TWO_D, device='cpu')\" || true",
        "mkdir -p /sadtalker/gfpgan/weights && "
        "wget -q -O /sadtalker/gfpgan/weights/GFPGANv1.4.pth "
        "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.0/GFPGANv1.4.pth || true",
    )
)

# NOTA: removido o Volume que antes era montado em /sadtalker/checkpoints.
# Os checkpoints já são baixados DURANTE O BUILD da imagem (linha acima),
# ficando permanentemente disponíveis nela. Um Volume vazio montado nesse
# mesmo caminho em tempo de execução escondia esses arquivos (Volumes
# sobrepõem o conteúdo da imagem no caminho em que são montados), forçando
# a função a lidar com uma pasta de checkpoints vazia a cada execução —
# provavelmente a causa raiz da lentidão/timeout observado.


@app.function(
    image=image,
    gpu="A10G",  # bom custo-benefício para SadTalker; trocar para "T4" se quiser mais barato ainda
    timeout=600,  # 10 min de margem por geração
    scaledown_window=60,  # libera o worker 60s após ficar ocioso (evita cobrança de idle)
)
def generate_avatar_video(image_bytes: bytes, audio_bytes: bytes) -> bytes:
    """
    Recebe a imagem do avatar (PNG/JPG) e o áudio (WAV/MP3) em bytes,
    roda o SadTalker e devolve o vídeo final (MP4) em bytes.
    """
    import subprocess
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as tmp:
        img_path = os.path.join(tmp, "avatar.png")
        audio_path = os.path.join(tmp, "audio.wav")
        out_dir = os.path.join(tmp, "output")
        os.makedirs(out_dir, exist_ok=True)

        with open(img_path, "wb") as f:
            f.write(image_bytes)
        with open(audio_path, "wb") as f:
            f.write(audio_bytes)

        cmd = [
            "python", "/sadtalker/inference.py",
            "--driven_audio", audio_path,
            "--source_image", img_path,
            "--result_dir", out_dir,
            "--still",  # menos movimento de cabeça, mais estável para avatar "apresentador"
            "--preprocess", "full",
            # --enhancer gfpgan removido por ora: dependência extra que pode
            # baixar peso sob demanda / adicionar tempo de processamento.
            # Reative depois de confirmar que o fluxo básico está estável:
            # "--enhancer", "gfpgan",
        ]
        result = subprocess.run(cmd, cwd="/sadtalker", capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"SadTalker falhou com código {result.returncode}.\n"
                f"---- stdout (últimas 3000 chars) ----\n{result.stdout[-3000:]}\n"
                f"---- stderr (últimas 3000 chars) ----\n{result.stderr[-3000:]}"
            )

        # SadTalker salva com nome baseado em timestamp; pega o mp4 mais recente
        mp4_files = [f for f in os.listdir(out_dir) if f.endswith(".mp4")]
        if not mp4_files:
            raise RuntimeError("SadTalker não gerou nenhum vídeo de saída.")
        result_path = os.path.join(out_dir, sorted(mp4_files)[-1])

        with open(result_path, "rb") as f:
            return f.read()


@app.function(image=image, timeout=700)  # margem acima do timeout de 600s da função interna
@modal.fastapi_endpoint(method="POST")
def generate_endpoint(item: dict):
    """
    Endpoint HTTP chamado pelo GitHub Actions.
    Espera JSON: {"image_url": "...", "audio_url": "..."}
    (URLs pré-assinadas de um storage temporário, ex.: GitHub Release asset,
    S3 presigned, ou similar — evita mandar base64 gigante no corpo do POST).
    Devolve: {"video_base64": "..."} em caso de sucesso, ou
             {"error": "...", "traceback": "..."} com status 500 em caso de falha
             — assim o erro real aparece direto no log do GitHub Actions, sem
             precisar abrir o painel da Modal pra ver o traceback.
    """
    import base64
    import traceback
    import urllib.request
    from fastapi.responses import JSONResponse

    try:
        image_bytes = urllib.request.urlopen(item["image_url"]).read()
        audio_bytes = urllib.request.urlopen(item["audio_url"]).read()

        video_bytes = generate_avatar_video.remote(image_bytes, audio_bytes)

        return {"video_base64": base64.b64encode(video_bytes).decode("utf-8")}

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e), "traceback": traceback.format_exc()},
        )


@app.local_entrypoint()
def main():
    """Teste local: modal run modal_avatar.py"""
    with open("assets/avatar.png", "rb") as f:
        img = f.read()
    with open("test_audio.wav", "rb") as f:
        audio = f.read()

    video = generate_avatar_video.remote(img, audio)
    with open("output_avatar.mp4", "wb") as f:
        f.write(video)
    print("Vídeo gerado: output_avatar.mp4")
