"""Smoke tests para a geração de tools a partir do openapi.yaml.

Estes testes existem para pegar regressões silenciosas: alterações no
`openapi.yaml` que continuam sendo YAML válido, mas fazem o FastMCP gerar
tools incompletas (ex.: o uso de `allOf` em requestBody, que o FastMCP não
achata, fazendo os campos do corpo sumirem da tool).
"""

import asyncio
import os

import pytest
import yaml

from mcp_organizze.server import mcp

OPENAPI_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "src",
    "mcp_organizze",
    "openapi.yaml",
)


@pytest.fixture(scope="session")
def tools():
    return asyncio.run(mcp.get_tools())


@pytest.fixture(scope="session")
def spec():
    with open(OPENAPI_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_tools_are_generated(tools):
    assert len(tools) > 0


def test_core_tools_exist(tools):
    expected = {
        "getTransactions",
        "getTransaction",
        "createTransaction",
        "updateTransaction",
        "deleteTransaction",
    }
    missing = expected - set(tools)
    assert not missing, f"Tools ausentes: {missing}"


def test_create_transaction_requires_core_fields(tools):
    schema = tools["createTransaction"].parameters
    assert set(schema.get("required", [])) == {
        "description",
        "date",
        "amount_cents",
        "account_id",
        "category_id",
    }


def test_update_transaction_allows_partial_update(tools):
    """Regressão: o PUT deve exigir apenas `id` e expor os campos do corpo.

    Antes da correção, o requestBody usava `allOf` e o FastMCP só expunha
    `id`/`update_future`/`update_all`, escondendo description, date, etc.
    """
    schema = tools["updateTransaction"].parameters

    assert schema.get("required", []) == ["id"], (
        "updateTransaction deveria exigir apenas o path param `id`"
    )

    props = schema.get("properties", {})
    for field in (
        "description",
        "date",
        "amount_cents",
        "account_id",
        "category_id",
        "update_future",
        "update_all",
    ):
        assert field in props, f"Campo `{field}` sumiu da tool updateTransaction"


def test_no_request_body_uses_allof(spec):
    """Lint na spec: `allOf` em requestBody é achatado incorretamente pelo
    FastMCP e faz os campos do corpo desaparecerem da tool gerada. Prefira
    um schema dedicado referenciado via `$ref` direto."""
    offenders = []
    for path, methods in spec.get("paths", {}).items():
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            body = op.get("requestBody", {})
            content = body.get("content", {}).get("application/json", {})
            schema = content.get("schema", {})
            if "allOf" in schema:
                offenders.append(f"{method.upper()} {path}")
    assert not offenders, (
        "requestBody com allOf (achatado incorretamente pelo FastMCP): "
        + ", ".join(offenders)
    )