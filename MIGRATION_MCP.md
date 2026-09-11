# Migração de MCP servers — Claude Code → Codex CLI

## Resultado da auditoria

Procurei nos locais onde o Claude Code guarda config de MCP por projeto:

- `.mcp.json` na raiz — **não existe**
- `.claude/settings.json` — **não existe**
- `.claude/` (existe, mas só contém `skills/`, sem nenhum arquivo de config
  de MCP)

**Não há nenhum MCP server configurado no nível do projeto.** Não há nada
pra converter em bloco `[mcp_servers.nome]` — não vou inventar entradas.

## Sobre os MCP servers vistos durante as sessões

Ao longo do desenvolvimento apareceram ferramentas de servidores MCP como
Canva, Gamma, Indeed, Figma, Gmail, Google Calendar e Google Drive. Esses
**não são configuração deste projeto** — são conectores de conta
(claude.ai / IDE extension) configurados no nível da conta ou da instalação
do Claude Code, não no repositório. Eles nunca foram usados pra nada
específico deste pipeline (nenhuma automação do projeto depende deles).

Não há, portanto, nada específico deste projeto para migrar nessa frente.

## Se você quiser algo equivalente no Codex

Isso é uma decisão sua, não uma consequência da migração deste repo. Se
quiser que o Codex tenha acesso a serviços parecidos, configure diretamente
no seu `~/.codex/config.toml` (fora do escopo deste repositório), algo como:

```toml
[mcp_servers.exemplo]
command = "npx"
args = ["-y", "@exemplo/mcp-server"]
env = { API_KEY = "..." }
```

O formato exato depende de qual servidor MCP você escolher para cada
serviço (Canva/Gamma/etc não têm um servidor MCP "oficial" único — precisa
escolher uma implementação). Como pediu, não mexi no seu
`~/.codex/config.toml` — isso fica pra você revisar e colar se decidir que
quer isso.
