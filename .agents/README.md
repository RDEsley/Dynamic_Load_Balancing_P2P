# Superpowers (`.agents`)

Skills de desenvolvimento assistido por IA instaladas neste repositório, baseadas em [obra/superpowers](https://github.com/obra/superpowers).

## Estrutura

```
.agents/
└── skills/
    ├── brainstorming/
    ├── systematic-debugging/
    ├── test-driven-development/
    ├── writing-plans/
    └── ... (14 skills no total)
```

O arquivo `skills-lock.json` na raiz registra versões e hashes de cada skill.

## Atualizar skills

Com [Node.js](https://nodejs.org/) instalado, na raiz do projeto:

```powershell
npx skills update -p -y
```

Isso sincroniza `.agents/skills/` com a versão mais recente do pacote `obra/superpowers`.

## Uso

Agentes compatíveis (Cursor, Claude Code, Copilot CLI, etc.) carregam automaticamente as skills de `.agents/skills/` quando trabalham neste repositório.

Comece pela skill `using-superpowers` para entender o fluxo de trabalho recomendado.
