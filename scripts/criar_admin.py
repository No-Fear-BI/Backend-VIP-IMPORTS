"""Cria uma conta de administrador do painel.

NÃO existe rota equivalente, e não é esquecimento: a proposta (item 2.4) não
contratou cadastro de administrador pela API. São duas contas no lançamento —
a do cliente e uma da No Fear para suporte — criadas por quem sobe o ambiente.

    python scripts/criar_admin.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from _entrada_admin import ler_senha_confirmada, ler_texto  # noqa: E402

from vip_api.banco import SessaoLocal  # noqa: E402
from vip_api.erros.excecoes import AppError  # noqa: E402
from vip_api.servicos.admin import (  # noqa: E402
    buscar_por_email,
    criar_administrador,
    validar_email,
    validar_senha,
)


def main() -> None:
    email = ler_texto("E-mail: ")
    nome = ler_texto("Nome: ")

    try:
        email = validar_email(email)
    except AppError as erro:
        raise SystemExit(f"ERRO: {erro.mensagem}")

    if not nome:
        raise SystemExit("ERRO: o nome é obrigatório.")

    with SessaoLocal() as sessao:
        # Confere antes de pedir a senha: digitar uma senha duas vezes para
        # depois descobrir que o e-mail já existe é desrespeito com quem usa.
        if buscar_por_email(sessao, email) is not None:
            raise SystemExit(
                f"ERRO: já existe administrador com o e-mail {email}. "
                "Para trocar a senha dele, use scripts/trocar_senha_admin.py."
            )

        senha = ler_senha_confirmada()
        try:
            validar_senha(senha)
        except AppError as erro:
            raise SystemExit(f"ERRO: {erro.mensagem}")

        administrador = criar_administrador(sessao, email, nome, senha)

    print(
        f"Administrador criado: id={administrador.id} "
        f"email={administrador.email} nome={administrador.nome}"
    )


if __name__ == "__main__":
    main()
