"""Verificação da Fatia 3: carrinho, migração e envio da seleção.

Cada passo imprime o estado antes e depois, para a saída se sustentar sozinha
sem quem lê ter que confiar no código.

    python scripts/verificar_fatia3.py <passo>
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

BASE = "http://localhost:8000/api/v1"


class Cliente:
    """Uma sessão de cliente com seu cookie próprio."""

    def __init__(self, email: str):
        self.email = email
        self.cookie = ""
        corpo, cabecalhos, _ = self._pedir(
            "POST", "/clientes/identificar", {"email": email}, cookie=""
        )
        for chave, valor in cabecalhos:
            if chave.lower() == "set-cookie":
                self.cookie = valor.split(";")[0]
        self.id = corpo["id"]

    def _pedir(self, metodo, caminho, corpo=None, cookie=None):
        dados = json.dumps(corpo).encode() if corpo is not None else None
        req = urllib.request.Request(f"{BASE}{caminho}", data=dados, method=metodo)
        req.add_header("Content-Type", "application/json")
        biscoito = self.cookie if cookie is None else cookie
        if biscoito:
            req.add_header("Cookie", biscoito)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                bruto = r.read().decode("utf-8")
                return (json.loads(bruto) if bruto else None), list(r.headers.items()), r.status
        except urllib.error.HTTPError as e:
            bruto = e.read().decode("utf-8")
            return (json.loads(bruto) if bruto else None), list(e.headers.items()), e.code

    def get(self, caminho):
        return self._pedir("GET", caminho)

    def post(self, caminho, corpo=None):
        return self._pedir("POST", caminho, corpo if corpo is not None else {})

    def patch(self, caminho, corpo):
        return self._pedir("PATCH", caminho, corpo)

    def delete(self, caminho):
        return self._pedir("DELETE", caminho)

    def carrinho(self):
        return self.get("/carrinho")[0]


def mostrar_carrinho(rotulo, itens):
    print(f"  {rotulo}")
    if not itens:
        print("    (vazio)")
        return
    for i in itens:
        var = i["variacao"]
        etiqueta = f"{var['tipo']}={var['valor']}" if var else "sem variação"
        print(f"    itemId={i['itemId']:<5} {i['codigo']:<10} {etiqueta:<22} {i['nome'][:40]}")


def limpar_carrinho(c: Cliente):
    for item in c.carrinho():
        c.delete(f"/carrinho/{item['itemId']}")
