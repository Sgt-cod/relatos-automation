# Arquitetura do Pipeline

## Fluxo completo

```
[cron GitHub Actions]
        │
        ▼
1. Buscar vídeo (canal de notícias) — busca por entrevistas recentes
        │
        ▼
2. Baixar corte de 6-7 min (trecho com divergência/tensão)
        │
        ▼
3. Gemini escreve o roteiro do avatar (comentário de abertura)
        │
        ▼
4. Fish Audio gera o áudio (TTS) a partir do roteiro
        │
        ▼
5. Modal (GPU) roda SadTalker → vídeo do avatar com lipsync
        │
        ▼
6. ffmpeg compõe o vídeo final (avatar em PiP + entrevista)
        │
        ▼
7. Agnes AI gera retrato + frame do vídeo + seta + faixa de texto → thumbnail
        │
        ▼
8. Telegram: envia roteiro + thumbnail para aprovação  ◄── CHECKPOINT HUMANO
        │
        ├── Rejeitado → descarta, fim
        │
        └── Aprovado (clique no botão)
                │
                ▼
        [repository_dispatch dispara 2º workflow]
                │
                ▼
        9. Publica no YouTube (API do YouTube Data v3)
```

## Por que dois workflows (não um só)

O GitHub Actions não tem como "pausar" um job esperando aprovação humana de
forma eficiente — ficaria consumindo minutos à toa. Por isso o desenho usa
dois workflows separados, ambos disparados por cron (sem webhook, sem
infra externa — mesmo modelo de polling que suas outras pipelines já usam):

- **Workflow A** (`.github/workflows/generate.yml`): roda no cron principal
  (ex.: 2x/dia), faz os passos 1-8, e termina após mandar a notificação no
  Telegram. Salva o estado "pendente" como arquivo no próprio repositório
  (`pending/{video_id}.json`).
- **Workflow B** (`.github/workflows/check_approval.yml`): roda em cron
  curto (a cada 5 min — intervalo mínimo permitido pelo GitHub Actions),
  consulta o Telegram via `getUpdates` (polling simples, sem webhook),
  cruza com os pendentes salvos no repo, e publica no YouTube se algo foi
  aprovado.

### Por que não precisa de Cloudflare/webhook

Telegram tem dois modos de receber atualizações: **webhook** (o Telegram
te avisa ativamente, precisa de uma URL pública sempre no ar) ou
**polling via `getUpdates`** (você pergunta periodicamente "tem algo
novo?"). Como o workflow B já roda em cron, ele naturalmente encaixa no
modo polling — sem precisar manter nenhum servidor ou função externa no
ar. É uma checagem HTTP simples, igual a qualquer chamada de API que suas
outras pipelines já fazem.

A troca é: com webhook a resposta seria quase instantânea; com polling a
cada 5 min, o atraso entre você clicar "Aprovar" e o vídeo realmente ir ao
ar é de até 5 minutos. Para esse caso de uso (aprovar um vídeo antes de
publicar), esse atraso é irrelevante.

## Arquivos deste pacote

```
.github/workflows/
  generate.yml            # Workflow A: cron principal, gera tudo até o Telegram
  check_approval.yml      # Workflow B: cron a cada 5 min, checa e publica
pipeline_config.py         # canais monitorados, janelas de tempo, etc.
find_and_download.py       # busca, baixa, transcreve e corta a entrevista
generate_script.py         # roteiro do avatar via Gemini (com salvaguardas)
modal_avatar.py            # função Modal (GPU) que roda o SadTalker
call_modal_endpoint.py     # chama o endpoint HTTP da Modal a partir do Actions
generate_audio.py          # TTS via Fish Audio
compose_video.py           # ffmpeg: monta avatar em PiP + entrevista
generate_thumbnail.py      # Agnes (retrato) + frame + seta + faixa de texto
telegram_approval.py       # envio do pedido + checagem por polling (getUpdates)
send_approval_request.py   # wiring do passo 7 do generate.yml
check_approvals_step.py    # wiring do check_approval.yml
publish_youtube.py         # upload final no YouTube, só roda se aprovado
```

## Como find_and_download.py identifica o "trecho de tensão"

1. Busca vídeos recentes (últimos `MAX_VIDEO_AGE_DAYS` dias) nos canais
   configurados, filtrando por palavra-chave ("entrevista") via YouTube
   Data API.
2. Baixa o vídeo com `yt-dlp` e transcreve com `faster-whisper` (roda em
   CPU, modelo "base" — suficiente para identificar o trecho, não precisa
   de precisão de legenda profissional).
3. Manda a transcrição completa (com timestamps) para o Gemini, pedindo
   que aponte o momento de maior tensão/divergência — a resposta vem em
   JSON com o segundo central do trecho.
4. Corta ~6,5 min ao redor desse ponto com `ffmpeg`.

Vídeos já processados ficam registrados em `state/processed_videos.json`
(committado de volta ao repo pelo workflow), para não repetir a mesma
entrevista em execuções futuras.

## Salvaguardas no roteiro do avatar (generate_script.py)

Como o roteiro é escrito por um LLM e vai virar fala de um avatar
realista, o prompt tem restrições explícitas: só descrever o que está
literalmente na transcrição, não atribuir motivação/estado emocional a
ninguém, e não usar rótulos político-ideológicos. Isso reduz o risco de
alucinação chegar até o Telegram — mas a revisão humana antes de aprovar
continua sendo a salvaguarda principal, então vale sempre ler o roteiro
com atenção antes de clicar "Aprovar".

## Pontas soltas para você decidir

1. **`CHANNELS` em `pipeline_config.py`**: preencha os Channel IDs reais
   (não é o @handle) dos 5 canais. O jeito mais fácil é usar a própria
   YouTube Data API (`channels.list?forHandle=@nomedocanal`) ou inspecionar
   o código-fonte da página do canal.
2. **Voz do Fish Audio**: precisa de um `reference_id` de voz — você já tem
   uma escolhida/clonada?
3. **Fonte para a faixa de texto da thumbnail**: usei "Anton" como exemplo
   (fonte grátis, estilo bold, comum em thumbs de YouTube). Baixe o `.ttf` e
   coloque em `assets/fonts/`.
4. **Autorização inicial do YouTube (OAuth2)**: `publish_youtube.py`
   precisa de um `refresh_token` já autorizado. Esse primeiro login é
   manual (tela de consentimento do Google) — não dá pra automatizar; é
   feito uma vez só, fora do pipeline.
5. **Storage temporário imagem/áudio → Modal**: usei uma *release* do
   próprio repositório como forma simples de expor a imagem/áudio por URL
   pública para o endpoint da Modal baixar. Funciona, mas deixa esses
   arquivos temporariamente públicos no GitHub. Se preferir mais
   privacidade, dá pra trocar por URLs pré-assinadas de algum bucket
   gratuito (ex.: Cloudflare R2 tem free tier generoso).
6. **Download do vídeo fonte**: como esses são conteúdos de emissoras com
   direitos reservados, reforço o ponto que já conversamos — vale limitar a
   fontes com licença mais clara (lives oficiais, canais institucionais) para
   reduzir risco de strike no canal.
7. **Tempo de execução do workflow A**: transcrição em CPU (`faster-whisper`)
   de um vídeo de ~15-20 min costuma levar alguns minutos no runner padrão
   do GitHub Actions. Se os vídeos-fonte forem mais longos, pode ser
   necessário aumentar o `timeout-minutes` do job em `generate.yml`.
