"""Smoke tests para a geração de tools a partir do openapi.yaml.

Estes testes existem para pegar regressões silenciosas: alterações no
`openapi.yaml` que continuam sendo YAML válido, mas fazem o FastMCP gerar
tools incompletas (ex.: o uso de `allOf` em requestBody, que o FastMCP não
achata, fazendo os campos do corpo sumirem da tool).
"""

import asyncio
import json
import os

import httpx
import pytest
import yaml

from mcp_organizze import server
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
    # account_id/category_id NÃO são obrigatórios: lançamentos em cartão usam
    # credit_card_id no lugar de account_id.
    assert set(schema.get("required", [])) == {
        "description",
        "date",
        "amount_cents",
    }


def test_create_transaction_supports_credit_card(tools):
    """Regressão (bug 1): sem credit_card_id não há como lançar direto no
    cartão, e a API acaba jogando na conta default. account_id e credit_card_id
    devem coexistir como alternativas, nenhum obrigatório."""
    props = tools["createTransaction"].parameters.get("properties", {})
    assert "credit_card_id" in props, "createTransaction não expõe credit_card_id"
    assert "account_id" in props


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


def test_required_fields_have_inline_type(tools):
    """Regressão: campos obrigatórios não podem ser um `$ref` pelado. Um $ref
    sem `type` no nível da propriedade é visto como "any" por clientes que não
    dereferenciam $defs, e "any" aceita null — foi o que fazia o LLM enviar
    `date: null` / `amount_cents: -1`. Devem ter `type` inline."""
    for tool_name in ("createTransaction", "updateTransaction"):
        props = tools[tool_name].parameters.get("properties", {})
        for field in ("date", "amount_cents"):
            prop = props[field]
            assert "type" in prop and "$ref" not in prop, (
                f"{tool_name}.{field} deve ter `type` inline, não um $ref pelado: {prop}"
            )


def test_enum_inputs_are_inline(tools):
    """Regressão: enums de entrada (type da conta, card_network do cartão) não
    podem ser um `$ref` pelado. Como "any", o modelo perde a lista de valores
    válidos e pode mandar 'Visa'/'corrente' em vez de 'visa'/'checking'."""
    cases = {
        "createAccount": "type",
        "createCreditCard": "card_network",
    }
    for tool_name, field in cases.items():
        prop = tools[tool_name].parameters["properties"][field]
        assert "$ref" not in prop, f"{tool_name}.{field} ainda é um $ref pelado"
        assert prop.get("enum"), f"{tool_name}.{field} deve expor a lista de enum inline"


def test_create_transaction_serializes_body(monkeypatch):
    """Regressão (bugs 1 e 2): o corpo enviado à API deve conter exatamente os
    campos informados — `date` como string ISO (não null) e `credit_card_id`
    (não substituído nem descartado). Intercepta a requisição HTTP real.
    """
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json={"id": 1})

    monkeypatch.setattr(server.client, "_transport", httpx.MockTransport(handler))

    tools = asyncio.run(mcp.get_tools())
    args = {
        "description": "Compra cartao",
        "date": "2026-05-23",
        "amount_cents": 15000,
        "credit_card_id": 2157726,
        "paid": False,
        "category_id": 999,
    }
    asyncio.run(tools["createTransaction"].run(args))

    body = captured["body"]
    assert body["date"] == "2026-05-23", "date não chegou como string ISO no corpo"
    assert body["credit_card_id"] == 2157726, "credit_card_id foi perdido/sobrescrito"
    assert "account_id" not in body, "account_id não deveria ser injetado"