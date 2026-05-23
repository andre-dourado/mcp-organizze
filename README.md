# MCP Organizze

Servidor MCP para integração com o gestor financeiro Organizze, compatível com qualquer cliente MCP (Claude Desktop, etc).

Este projeto expõe a API v2 do Organizze como ferramentas de IA, permitindo criar transações, consultar saldos, metas e muito mais.

## ✨ Funcionalidades

- **Contas**: Listar, criar e detalhar contas bancárias.
- **Transações**: Criar (despesas/receitas) e listar movimentações.
- **Cartões de Crédito**: Listar e detalhar faturas.
- **Categorias e Metas**: Gerenciamento completo.

## 🚀 Como Usar

### Pré-requisitos

Você precisará das suas credenciais do Organizze:
- `ORGANIZZE_EMAIL`: Seu email de login.
- `ORGANIZZE_API_KEY`: Sua chave de API.

### Opção 1: Via UVX (Recomendado)

Se você tem o `uv` instalado, pode rodar diretamente sem instalar nada:

```bash
# Executa em modo STDIO (padrão para Claude Desktop)
ORGANIZZE_EMAIL=seu@email.com ORGANIZZE_API_KEY=sua_chave uvx mcp-organizze
```

Para integrar ao **Claude Desktop**, adicione ao seu arquivo de configuração:

```json
{
  "mcpServers": {
    "organizze": {
      "command": "uvx",
      "args": ["mcp-organizze"],
      "env": {
        "ORGANIZZE_EMAIL": "seu_email",
        "ORGANIZZE_API_KEY": "sua_chave_api"
      }
    }
  }
}
```

### Opção 2: Via Docker

A imagem Docker roda por padrão em modo **Streamable HTTP (SSE)** na porta 8000, ideal para uso remoto ou em servidores.

**Executar com SSE (Porta 8000):**

```bash
docker run -p 8000:8000 \
  -e ORGANIZZE_EMAIL=seu_email \
  -e ORGANIZZE_API_KEY=sua_chave \
  mcp-organizze
```

**Executar com STDIO (Interativo):**

```bash
docker run -i \
  -e ORGANIZZE_EMAIL=seu_email \
  -e ORGANIZZE_API_KEY=sua_chave \
  mcp-organizze --transport stdio
```

### Opção 3: Instalação Local (Pip/UV)

Clone o repositório e instale:

```bash
uv pip install .
# ou
pip install .
```

Rode o servidor:
```bash
python -m mcp_organizze
```

## 🛠 Desenvolvimento e Publicação

### Estrutura do Projeto

- `src/mcp_organizze`: Código fonte do pacote.
- `src/mcp_organizze/openapi.yaml`: Especificação da API; as ferramentas MCP são geradas automaticamente a partir dela (`FastMCP.from_openapi`).
- `tests/`: Smoke tests da geração de ferramentas.
- `pyproject.toml`: Configuração de build e dependências.
- `Dockerfile`: Configuração para containerização.
- `.github/workflows`: Actions para CI/CD.

### Testes

As ferramentas MCP são geradas a partir do `openapi.yaml` no startup. Como alterações na spec podem continuar sendo YAML válido e ainda assim gerar ferramentas incompletas (ex.: o FastMCP não achata `allOf` em `requestBody`, fazendo os campos do corpo sumirem da ferramenta), há uma suíte de smoke tests para pegar essas regressões silenciosas.

Rode com:

```bash
uv run --group dev pytest -q
```

Os testes verificam que as ferramentas são geradas, que as principais existem, que `updateTransaction` permite atualização parcial (apenas `id` obrigatório, expondo os campos do corpo) e fazem um lint na spec barrando o uso de `allOf` em `requestBody`.

<!-- mcp-name: io.github.SamuelMoraesF/mcp-organizze -->