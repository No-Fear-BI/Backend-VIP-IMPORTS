"""Classifica a fila de revisão do Yupoo (data/pending-products.json) pelo título do álbum.

Os títulos vêm do fornecedor, em chinês (simplificado ou tradicional), então a regra é por palavra:
a PRIMEIRA categoria cujo termo aparece no título vence — a ordem de REGRAS importa (calçado e
acessório antes de roupa, "套装" conjunto antes de "卫衣" moletom etc.). Título sem termo nenhum
(só número e tamanho, como "170 P XS-L") fica como estava: "A classificar" continua "A classificar",
e uma categoria que o item já tinha é mantida.

    python scripts/classificar_fila.py            # só mostra o resultado, não grava
    python scripts/classificar_fila.py --gravar   # regrava data/pending-products.json

Só o campo `category` muda; o arquivo é regravado no mesmo formato do importador (2 espaços, LF).
O arquivo está no git: para desfazer, `git checkout data/pending-products.json`.
"""

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parents[1] / "data" / "pending-products.json"
SEM_CATEGORIA = "A classificar"

# Termos em letras latinas casam só como palavra inteira (senão "bag" pegaria "baggy"); os em
# chinês casam em qualquer posição. Exceções do chinês estão em IGNORAR.
REGRAS: list[tuple[str, list[str]]] = [
    ("Relógios", ["手表", "腕表", "手錶", "r:watch", "relógio", "relogio"]),
    ("Cintos", ["腰带", "腰帶", "皮带", "皮帶", "r:belt", "cinto"]),
    (
        "Chinelos e sapatos baixos",
        ["拖鞋", "凉拖", "涼拖", "凉鞋", "涼鞋", "洞洞鞋", "毛拖", "半拖", "皮鞋", "乐福", "樂福", "懒人鞋", "懶人鞋",
         "单鞋", "單鞋", "平底鞋", "豆豆鞋", "玛丽珍", "芭蕾鞋", "r:slippers?", "r:sandals?", "r:loafers?", "chinelo", "sapato"],
    ),
    (
        "Tênis",
        ["球鞋", "运动鞋", "運動鞋", "板鞋", "老爹鞋", "跑鞋", "休闲鞋", "休閑鞋", "篮球鞋", "籃球鞋", "足球鞋",
         "r:sneakers?", "tênis", "tenis"],
    ),
    (
        "Bolsas",
        ["背包", "双肩包", "雙肩包", "手提包", "斜挎包", "单肩包", "單肩包", "腰包", "钱包", "錢包", "挎包", "旅行包",
         "胸包", "邮差包", "郵差包", "水桶包", "链条包", "鏈條包", "女包", "男包", "皮包", "手袋", "包包", "托特",
         "r:bags?", "r:wallets?", "bolsa"],
    ),
    ("Conjuntos", ["套装", "套裝", "两件套", "兩件套", "三件套", "conjunto"]),
    ("Coletes", ["马甲", "馬甲", "r:vest", "colete"]),
    ("Jaquetas de inverno", ["羽绒", "羽絨", "棉服", "棉衣"]),
    (
        "Jaquetas esportes",
        ["运动外套", "運動外套", "运动夹克", "運動夾克", "出场服", "出場服", "冲锋衣", "衝鋒衣", "棒球服", "防晒衣", "防曬衣",
         "足球服", "球衣外套"],
    ),
    ("Jaquetas", ["夹克", "夾克", "风衣", "風衣", "外套", "r:jackets?", "jaqueta"]),
    ("Casacos", ["大衣", "r:coats?", "casaco"]),
    ("Moletons", ["卫衣", "衛衣", "连帽", "連帽", "r:hoodies?", "moletom"]),
    ("Jeans", ["牛仔", "r:jeans"]),
    ("Ternos", ["西装", "西裝", "西服", "terno"]),
    ("Bermudas", ["短裤", "短褲", "五分裤", "五分褲", "r:shorts", "bermuda"]),
    ("Camisas", ["衬衫", "襯衫", "camisa"]),
    ("Camisetas", ["t恤", "短袖", "r:polo", "r:tee", "camiseta"]),
    ("Suéteres", ["毛衣", "针织", "針織", "开衫", "開衫", "r:sweaters?", "suéter"]),
]
# Palavras que contêm um termo mas não são o produto ("包邮" = frete grátis, "包头" = bico fechado,
# "包装" = embalagem, "包括"/"包含" = inclui).
IGNORAR = ["包邮", "包郵", "包头", "包頭", "包装", "包裝", "包括", "包含", "包退", "包换", "包換", "包跟", "包边", "包邊"]

_COMPILADAS = [
    (
        categoria,
        [re.compile(rf"(?<![a-z]){t[2:]}(?![a-z])") if t.startswith("r:") else t for t in termos],
    )
    for categoria, termos in REGRAS
]


def classificar(nome: str) -> str | None:
    texto = nome.lower()
    for ignorado in IGNORAR:
        texto = texto.replace(ignorado, " ")
    for categoria, termos in _COMPILADAS:
        for termo in termos:
            if (termo.search(texto) if isinstance(termo, re.Pattern) else termo in texto):
                return categoria
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gravar", action="store_true", help="regrava o arquivo (sem isto só mostra o resultado)")
    args = parser.parse_args()

    produtos = json.loads(ARQUIVO.read_text(encoding="utf-8-sig"))
    antes = Counter(p["category"] for p in produtos)
    trocas: Counter[tuple[str, str]] = Counter()
    exemplos: dict[str, list[str]] = defaultdict(list)

    for produto in produtos:
        nova = classificar(produto["name"])
        if nova is None or nova == produto["category"]:
            continue
        trocas[(produto["category"], nova)] += 1
        exemplos[nova].append(produto["name"][:70])
        produto["category"] = nova

    depois = Counter(p["category"] for p in produtos)
    sys.stdout.reconfigure(encoding="utf-8")
    print(f"{len(produtos)} produtos")
    for categoria, quantidade in depois.most_common():
        print(f"  {categoria:28} {quantidade:6}  (antes {antes.get(categoria, 0)})")
    ja_tinham = sum(q for (de, _), q in trocas.items() if de != SEM_CATEGORIA)
    print(f"\n{sum(trocas.values())} itens mudaram de categoria; {ja_tinham} deles já tinham uma categoria:")
    for (de, para), quantidade in trocas.most_common():
        if de != SEM_CATEGORIA:
            print(f"  {de} -> {para}: {quantidade}")
    random.seed(1)
    print("\nAmostras:")
    for categoria, nomes in exemplos.items():
        print(f"  {categoria}")
        for nome in random.sample(nomes, min(3, len(nomes))):
            print(f"    - {nome}")

    if args.gravar:
        ARQUIVO.write_text(json.dumps(produtos, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
        print(f"\nGravado em {ARQUIVO}")
    else:
        print("\n(nada foi gravado — use --gravar)")


if __name__ == "__main__":
    main()
