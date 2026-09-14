"""Troca a senha de um administrador e derruba as sessões dele.

As duas coisas juntas, sempre: quem troca a senha está assumindo que ela pode
ter vazado, e deixar aberta a sessão de quem eventualmente a pegou não resolve
nada. Entra na gravação do treinamento (tarefa 87).

    python scripts/trocar_senha_admin.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from _entrada_admin import ler_senha_confirmada, ler_texto  # noqa: E402

from vip_api.banco import SessaoLocal  # noqa: E402
from vip_api.erros.excecoes import AppError  # noqa: E402
from vip_api.servicos.admin import buscar_por_email, trocar_senha, validar_senha  # noqa: E402


def main() -> None:
    email = ler_texto("E-mail do administrador: ")

    with SessaoLocal() as sessao:
        administrador = buscar_por_email(sessao, email)
        if administrador is None:
            raise SystemExit(f"ERRO: não há administrador com o e-mail {email}.")

        print(f"Trocando a senha de {administrador.nome} <{administrador.email}>.")
        senha = ler_senha_confirmada()
        try:
            validar_senha(senha)
        except AppError as erro:
            raise SystemExit(f"ERRO: {erro.mensagem}")

        derrubadas = trocar_senha(sessao, administrador, senha)

    print(
        f"Senha trocada. Sessões abertas revogadas: {derrubadas}. "
        "Quem estiver com o painel aberto vai cair no próximo clique."
    )


if __name__ == "__main__":
    main()
