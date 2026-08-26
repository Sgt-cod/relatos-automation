# Arquitetura do Pipeline

## Fluxo completo

Tudo roda num **workflow único** (`.github/workflows/generate.yml`), num
único job do GitHub Actions, do início ao fim — incluindo a espera pela
sua aprovação no Telegram.

```
[cron ou disparo manual]
        │
        ▼
1. Buscar vídeo de entrevista nos canais configurados, baixar, transcrever
   e cortar o trecho de maior tensão (~6,5 min)
        │
        ▼
2. Gemini escreve o roteiro do avatar (com salvaguardas contra alucinação)
        │
        ▼
3. Fish Audio gera o áudio (TTS) a partir do roteiro
        │
        ▼
4. Modal (GPU externa) roda o SadTalker → vídeo do avatar com lipsync
        │
        ▼
5. Agnes AI gera o retrato + frame do vídeo + seta + faixa de texto → thumbnail
        │
        ▼
6. Telegram: envia vídeo do avatar E thumbnail, cada um com botões
   próprios de aprovação        ◄── CHECKPOINT HUMANO
        │
        ├── Rejeitado sem substituto + botão "Cancelar" → encerra, nada é publicado
        ├── Rejeitado + substituto enviado (vídeo/imagem) → usa o substituto
        ├── Sem resposta dentro do timeout (padrão 60 min) → CANCELA (não publica)
        │
        └── Ambos os itens aprovados
                │
                ▼
        7. Compõe o vídeo final (ffmpeg, avatar em PiP + entrevista)
                │
                ▼
        8. Publica no YouTube (API do YouTube Data v3)
```

## Por que um workflow só (não dois)

Uma versão anterior deste pipeline usava dois workflows separados: um para
gerar o conteúdo, outro rodando em cron a cada 5 min para checar respostas
no Telegram. Essa abordagem tinha um problema real: **workflows agendados
(`schedule`) no GitHub Actions não têm garantia de disparar no horário
exato** — o próprio GitHub documenta que execuções podem atrasar ou até ser
puladas em períodos de carga alta, especialmente em repositórios com pouca
atividade. Na prática, isso fazia cliques de aprovação no Telegram ficarem
sem resposta.

A solução foi seguir o mesmo padrão de uma pipeline mais madura do próprio
usuário: um **loop de espera bloqueante dentro do mesmo job** (consultando
o Telegram a cada poucos segundos via `getUpdates`), em vez de depender de
um segundo workflow agendado. Isso elimina a dependência do cron de 5 em 5
min e também simplifica bastante o resto do sistema:

- Não precisa mais de storage intermediário (releases do GitHub) para
  passar arquivos entre workflows — tudo fica no mesmo runner, do início
  ao fim.
- A chamada à Modal manda a imagem/áudio como base64 direto no corpo da
  requisição, em vez de hospedar por URL.
- Não precisa mais de `git commit`/`git push` de estado intermediário
  (`pending/*.json`) — o estado da aprovação vive só na memória do
  processo Python durante a execução do job.

**Trade-off aceito**: o job do GitHub Actions fica com timeout mais alto
(padrão 100 min, pra caber até 60 min de espera pela aprovação + geração +
composição/publicação). Isso consome minutos do seu plano do GitHub Actions
de forma mais concentrada, mas dentro do limite gratuito mensal isso não
costuma ser um problema para um pipeline de baixo volume.

## Avatar: Modal (opcional) vs. vídeo local do apresentador (padrão)

Por padrão (execuções automáticas via cron), o pipeline **não usa a
Modal**. Em vez disso, `create_presenter_clip.py` pega um vídeo longo já
gravado do apresentador (`assets/presenter.mp4` — ele gesticulando, com
nariz e boca mascarados) e só troca o áudio original pelo áudio gerado
(roteiro + Fish Audio):
- Se o vídeo for mais curto que o áudio, repete em loop até cobrir a
  duração inteira.
- Se for mais longo, corta um trecho do tamanho exato do áudio, a partir
  de um ponto aleatório (varia o trecho usado a cada execução).

A rota via Modal (SadTalker, lipsync realista) continua disponível, mas
só quando você dispara o workflow manualmente (aba Actions > "Run
workflow") e marca a opção `use_modal`. Nesse caso, o campo
`approval_timeout_min` do mesmo disparo também vale, então dá pra
ajustar os dois de uma vez ao rodar manualmente.

Os dois caminhos produzem o mesmo arquivo de saída (`output_avatar.mp4`),
então o resto do pipeline (composição do vídeo final, thumbnail, etc.)
funciona igual independente de qual dos dois gerou o clipe.

## Comportamento em caso de timeout

Diferente de outra pipeline do usuário (que publica automaticamente após 1h
sem resposta), aqui o padrão é **cancelar** se o timeout for atingido sem
aprovação completa dos dois itens. A justificativa: o conteúdo é sensível
(entrevista/notícia política com avatar realista comentando), então
publicar sem revisão humana confirmada não é o comportamento desejado —
mesmo que isso signifique perder a janela de um dia sem publicar nada.

O tempo de espera é configurável: ao disparar manualmente o workflow (aba
Actions > "Run workflow"), há um campo para ajustar os minutos de espera.
Rodando via cron, usa o padrão de 60 min.

## Arquivos deste pacote

```
.github/workflows/
  generate.yml              # workflow único: geração → aprovação → publicação
  deploy_modal.yml           # deploy da função Modal (roda quando modal_avatar.py muda)
pipeline_config.py            # canais monitorados, janelas de tempo, etc.
find_and_download.py          # busca, baixa, transcreve e corta a entrevista
gemini_client.py               # chamada ao Gemini com retry automático
generate_script.py             # roteiro do avatar via Gemini (com salvaguardas)
create_presenter_clip.py       # PADRÃO: vídeo local do apresentador + áudio (sem Modal)
modal_avatar.py                # função Modal (GPU) que roda o SadTalker — OPCIONAL, só via disparo manual
call_modal_endpoint.py         # chama o endpoint da Modal (imagem/áudio em base64) — OPCIONAL
generate_audio.py              # TTS via Fish Audio (com retry automático)
compose_video.py               # ffmpeg: monta avatar em PiP + entrevista
generate_thumbnail.py          # Agnes (retrato) + frame + seta (PNG) + faixa de texto
telegram_approval.py           # envio + loop de espera por aprovação individual
approve_compose_publish.py     # junta aprovação + composição + publicação
publish_youtube.py             # upload final no YouTube
```

## Pontas soltas para você decidir

1. **`CHANNELS` em `pipeline_config.py`**: preencha os Channel IDs reais
   dos 5 canais (veja o `GUIA_APIS.md`, seção 5).
2. **Voz do Fish Audio** (`FISH_AUDIO_VOICE_ID`).
3. **Fontes da thumbnail**: coloque `Bangers-Regular.ttf` e/ou
   `RoadRage-Regular.ttf` em `assets/fonts/`.
4. **Seta da thumbnail**: coloque uma imagem PNG com fundo transparente,
   apontando para a direita, em `assets/arrow_right.png`.
5. **Avatar**: imagem em `assets/avatar.png` (usada só se rodar com Modal)
   e vídeo em `assets/presenter.mp4` (usado por padrão — o apresentador
   gesticulando, com nariz e boca mascarados).
6. **Autorização OAuth2 do YouTube** (veja `GUIA_APIS.md`, seção 4).
7. **`YOUTUBE_COOKIES`** (veja `GUIA_APIS.md`, seção 6) — necessário para o
   `yt-dlp` não ser bloqueado pelo YouTube.
8. **Download do vídeo fonte**: como esses são conteúdos de emissoras com
   direitos reservados, vale considerar priorizar fontes com licença mais
   clara (lives oficiais, canais institucionais) para reduzir risco de
   problema com os veículos de imprensa.
