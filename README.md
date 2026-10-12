# KBR Karaoke Tool - Automação para Jogo no Roblox

Sistema unificado para automação e sincronização de músicas de karaokê para o seu jogo no Roblox.

## Funcionalidades
1. **Download do Áudio (MP3)**: Extrai o áudio direto do YouTube via `yt-dlp` ou permite carregar qualquer MP3 local.
2. **Busca de Letra Sincronizada (LRC)**: Consulta automática à API do **lrclib.net** ou permite carregar arquivo `.lrc` próprio.
3. **Seleção Visual do Trecho**: Lista interativa com todos os versos da música. Basta clicar em um verso e clicar em "Definir Início" e em outro para "Definir Fim".
4. **Corte Rápido em Segundos**: Recorte com precisão de milissegundos usando `ffmpeg`.
5. **Remoção de Vocais Opcional**: Cancelamento de fase estéreo preservando graves (deixa a faixa instrumental).
6. **Modificação Anti-Copyright / MIDI Opcional**: Converte o áudio para MIDI e sintetiza novos timbres instrumentais para evitar filtros automáticos de copyright do Roblox.
7. **Re-cálculo Automático de Tempos**: O primeiro verso cortado é normalizado para `0.0s`, mantendo todos os intervalos relativos exatos da letra original.
8. **Exportação no Formato do Roblox (`format.txt`)**: Gera a tabela Lua pronta para colar no jogo, salvando tudo em `music/generated_output/` com botão de 1 clique para copiar o código para a área de transferência.

---

## Como Usar

### Pela Interface Gráfica (Recomendado):
Basta dar dois cliques em:
```
iniciar_karaoke.bat
```
Ou executar no terminal:
```bash
python gui.py
```

### Pela Linha de Comando (CLI):
```bash
python kbr_tool.py --url "https://www.youtube.com/watch?v=XXXX" --title "João e Maria" --artist "Chico Buarque" --start "01:15" --end "02:07"
```

---

## Estrutura de Arquivos Gerados
Todos os arquivos são salvos automaticamente na pasta:
`music/generated_output/`

* `<song_id>.mp3`: Áudio cortado pronto para upload no Roblox.
* `<song_id>.lua`: Código da tabela Lua no formato do jogo.
* `<song_id>_adjusted.lrc`: Letra no formato LRC com os tempos ajustados a partir de 00:00.
* `<song_id>.mid`: Arquivo MIDI (caso a opção esteja ativada).
