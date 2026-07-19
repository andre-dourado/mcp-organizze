import yaml
import httpx
import os
import logging
from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from dotenv import load_dotenv

load_dotenv()

# Configuração de Logs
log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("mcp_organizze")

# Carregar especificação OpenAPI usando caminho relativo
try:
    current_dir = os.path.dirname(os.path.abspath(__file__))
    openapi_path = os.path.join(current_dir, "openapi.yaml")
    with open(openapi_path, "r") as f:
        openapi_spec = yaml.safe_load(f)
except FileNotFoundError:
    # Fallback para execução local de teste onde openapi.yaml pode estar no CWD
    try:
        with open("openapi.yaml", "r") as f:
            openapi_spec = yaml.safe_load(f)
    except FileNotFoundError:
        import sys
        print(f"Erro: openapi.yaml não encontrado em {openapi_path} ou no diretório atual.", file=sys.stderr)
        sys.exit(1)

# Configurar credenciais
email = os.environ.get("ORGANIZZE_EMAIL")
api_key = os.environ.get("ORGANIZZE_API_KEY")
user_agent_custom = os.environ.get("USER_AGENT", f"MCP-Organizze ({email or 'unknown'})")

if not email or not api_key:
    import sys
    print("AVISO: Variáveis de ambiente ORGANIZZE_EMAIL e ORGANIZZE_API_KEY não encontradas.", file=sys.stderr)


# Headers de entrada que o FastMCP repassa e que quebram a chamada de saída.
# `cdn-loop` é o crítico: a API do Organizze fica atrás de Cloudflare e
# responde 403 (corpo vazio) ao receber um request que já traz esse header.
_FORWARD_BLOCKLIST = {
    "cdn-loop", "cf-connecting-ip", "cf-ipcountry", "cf-ray", "cf-visitor",
    "x-forwarded-for", "x-forwarded-host", "x-forwarded-proto",
    "x-anthropic-client", "x-cloud-trace-context", "traceparent", "via",
    "mcp-protocol-version", "mcp-session-id",
}


async def sanitize_request(request: httpx.Request):
    for h in _FORWARD_BLOCKLIST:
        request.headers.pop(h, None)
    request.headers["User-Agent"] = user_agent_custom
    if logger.isEnabledFor(logging.DEBUG):
        safe = {
            k: ("***" if k.lower() == "authorization" else v)
            for k, v in request.headers.items()
        }
        logger.debug("[req] %s %s | headers=%s", request.method, request.url, safe)


async def log_response(response: httpx.Response):
    if logger.isEnabledFor(logging.DEBUG) or os.environ.get("DEBUG_RESPONSE") == "true":
        await response.aread()
        logger.info(f"Response from {response.url}: {response.text}")

client = httpx.AsyncClient(
    base_url="https://api.organizze.com.br/rest/v2",
    auth=(email, api_key) if email and api_key else None,
    headers={
        "User-Agent": user_agent_custom,
        "Content-Type": "application/json"
    },
    timeout=30.0,
    event_hooks={
        'request': [sanitize_request],
        'response': [log_response]
    }
)

mcp = FastMCP.from_openapi(
    openapi_spec=openapi_spec,
    client=client,
    name="Organizze API"
)


class ClientCallLoggingMiddleware(Middleware):
    """Loga a tool chamada e os argumentos crus enviados pelo client, antes da
    validação do FastMCP/pydantic."""

    async def on_call_tool(self, context: MiddlewareContext, call_next):
        logger.info(
            "[tool-call] %s | args=%s",
            context.message.name,
            context.message.arguments,
        )
        try:
            return await call_next(context)
        except Exception as e:
            logger.error(
                "[tool-error] %s falhou: %r | args=%s",
                context.message.name,
                e,
                context.message.arguments,
            )
            raise


mcp.add_middleware(ClientCallLoggingMiddleware())