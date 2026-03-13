# Ghost Writer MCP

An MCP server that scans your Git repositories, identifies interesting engineering work, and generates LinkedIn post drafts — with built-in confidentiality sanitisation.

## What it does

```
Your repos → scan activity → classify by content potential → generate draft → sanitise → review
```

1. **Scan** — reads `git log` from local repo clones (zero API calls, instant)
2. **Aggregate** — groups commits by conventional-commit prefix and clusters related work
3. **Classify** — LLM ranks groups by content potential, assigns pillars and angles
4. **Generate** — LLM writes a LinkedIn draft in your chosen format (war story, hot take, tactical howto, TIL, deep dive)
5. **Sanitise** — three-gate safety: regex blocklist → LLM review → human review

## Quick start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- An LLM provider: [Ollama](https://ollama.com/) (free, local) or an [Anthropic API key](https://console.anthropic.com/)
- Local clones of the repos you want to scan

### Install

**Option A — clone and run (recommended for customisation):**

```bash
git clone https://github.com/fabdendev/ghost-writer-mcp.git
cd ghost-writer-mcp
uv sync
```

**Option B — run directly with uvx (no clone needed):**

```bash
uvx ghost-writer-mcp
```

### Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your repos, blocklist, and LLM settings. See [config.example.yaml](config.example.yaml) for a fully documented template.

**For Ollama (free, local):**

```yaml
llm:
  provider: ollama
  base_url: "http://localhost:11434/v1"
  classifier_model: qwen3:8b
  generator_model: qwen3:8b
  api_key: "ollama"
```

```bash
ollama pull qwen3:8b
ollama serve
```

**For Anthropic (cloud):**

```yaml
llm:
  provider: anthropic
  classifier_model: claude-haiku-4-5-20251001
  generator_model: claude-haiku-4-5-20251001
  api_key: "${ANTHROPIC_API_KEY}"
```

```bash
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
```

### Add to Claude Code

Add to your Claude Code MCP settings (`~/.claude/settings.json`):

**If installed from clone:**

```json
{
  "mcpServers": {
    "ghost-writer": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ghost-writer-mcp", "fastmcp", "run", "src/server.py"]
    }
  }
}
```

**If using uvx:**

```json
{
  "mcpServers": {
    "ghost-writer": {
      "command": "uvx",
      "args": ["ghost-writer-mcp"]
    }
  }
}
```

### Use via MCP

From Claude Code (or any MCP client):

```
scan_activity                          # scan all configured repos (last 7 days)
scan_activity(repo="my-project")       # scan a single repo
scan_activity(days=30)                 # look back 30 days
generate_draft(activity_index=1)       # generate from top candidate
generate_draft(3, format="hot_take")   # override format
edit_draft(1, "make it shorter")       # refine with natural language
list_drafts(status="pending")          # see saved drafts
```

### Use via CLI

You can also test without an MCP client:

```bash
uv run python -m src scan --days 14                    # scan all repos
uv run python -m src scan --repo my-project            # scan one repo
uv run python -m src generate 1                        # draft from top result
uv run python -m src generate 3 --format hot_take      # override format
uv run python -m src list                              # list saved drafts
```

## Tools

| Tool | Description |
|------|-------------|
| `scan_activity` | Scan repos, aggregate commits, classify and rank by content potential |
| `generate_draft` | Generate a LinkedIn draft from a classified activity |
| `edit_draft` | Refine a draft with natural language instructions |
| `list_drafts` | List saved drafts, optionally filtered by status |

## Scanning modes

Ghost Writer supports two scanning backends:

- **Local git** (default) — reads `git log` from local clones. Zero API calls, instant results. Set `local_path` on each repo in your config.
- **GitHub API** (fallback) — used automatically for repos without `local_path`. Requires a GitHub token (`github.token` in config). Fetches up to 30 commits and 20 merged PRs per repo.

You can mix both: some repos with local clones, others via API.

## Confidentiality

Ghost Writer uses three safety gates to prevent leaking sensitive information:

- **Gate 1 — Blocklist**: regex-based detection and replacement of company names, client names, product names, infrastructure details, and people names
- **Gate 2 — LLM Review**: the LLM scans generated text for anything that looks confidential and flags it
- **Gate 3 — Human Review**: drafts are saved as `pending` — you always get the final say

Configure your blocklist and abstractions in `config.yaml`:

```yaml
sanitisation:
  blocklist:
    company_names: ["Acme Corp"]
    client_names: ["Big Client"]
    product_names: ["internal-tool"]
    infrastructure: ["prod-db-01.internal"]
    people: ["John Doe"]
  abstractions:
    "Acme Corp": "a mid-size tech company"
    "internal-tool": "an internal platform"
```

## Content pillars

Define what topics you want to post about. The classifier maps activities to pillars:

```yaml
content:
  pillars:
    - name: ai_engineering
      description: "Building AI agents, LLM integration, prompt engineering"
      repo_signals: ["agent", "llm", "prompt"]
      weight: 1.0
    - name: data_architecture
      description: "Data pipelines, ETL, event-driven systems"
      repo_signals: ["pipeline", "etl", "kafka"]
      weight: 0.8
```

## Post formats

| Format | Description |
|--------|-------------|
| `tactical_howto` | Problem → 3-5 concrete steps → takeaway |
| `hot_take` | Contrarian claim backed by one specific thing you built |
| `war_story` | What broke, what you tried, what worked, the lesson |
| `til` | One surprising thing you learned, under 500 chars |
| `deep_dive` | 3-4 sections with trade-offs and alternatives |

## Architecture

```
src/
├── server.py              # FastMCP server (4 tools)
├── cli.py                 # Standalone CLI for testing without MCP
├── config.py              # Pydantic config with env/shell resolution
├── llm_client.py          # Unified Anthropic + OpenAI-compatible client
├── scanner/
│   ├── local_git.py       # Git CLI scanner (primary)
│   ├── github_client.py   # GitHub API scanner (alternative)
│   ├── aggregator.py      # Commit grouping and clustering
│   └── activity.py        # ActivityItem dataclass
├── content/
│   ├── classifier.py      # LLM-based content scoring
│   ├── generator.py       # Draft generation with sanitisation
│   ├── abstractor.py      # Two-gate confidentiality layer
│   └── prompts/           # System prompts (classifier, generator, reviewer)
└── store/
    ├── database.py         # SQLite persistence
    └── blocklist.py        # Regex-based blocklist
```

## Development

```bash
uv sync --extra dev
uv run pytest                 # run tests
uv run ruff check src/ tests/ # lint
```

## License

MIT
