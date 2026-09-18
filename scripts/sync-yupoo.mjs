import { writeFile } from "node:fs/promises";

const suppliers = [
  {
    id: "qwer888",
    baseUrl: "https://1234qwer888.x.yupoo.com",
    categories: [
      ["5307806", "Jaquetas"],
      ["4928722", "Moletons"],
      ["4672832", "Coletes"],
      ["5306911", "Jaquetas de inverno"],
      ["3807639", "Suéteres"],
      ["4181353", "Conjuntos"],
      ["3835122", "Ternos"],
      ["3907667", "Jeans"],
      ["4133439", "Jaquetas"],
      ["4066411", "Bermudas"],
      ["4390759", "Camisetas"],
      ["3965838", "Camisas"],
      ["4472597", "Conjuntos"],
      ["4123851", "Conjuntos"],
      ["4845980", "Bermudas"],
      ["4025547", "Casacos"],
    ],
  },
  {
    id: "jypj",
    baseUrl: "https://jypj.x.yupoo.com",
    categories: [["4836989", "Bolsas"]],
  },
];

const restricted = [
  "adidas", "amiri", "armani", "balenciaga", "bally", "boss", "burberry",
  "bvlgari", "cartier", "casablanca", "celine", "chanel", "coach", "dior",
  "dolce", "fendi", "givenchy", "goyard", "gucci", "hermès", "hermes",
  "loewe", "louis vuitton", "moncler", "montblanc", "nike", "prada",
  "stella mccartney", "thom browne", "valentino", "versace", "zegna",
  "香奈儿", "爱马仕", "古奇", "普拉达", "芬迪", "巴宝莉", "巴黎世家",
  "迪奥", "路易威登", "纪梵希", "赛琳", "蔻驰", "卡地亚", "范思哲",
];

const decode = (value) => value
  .replaceAll("&#x27;", "'").replaceAll("&#39;", "'")
  .replaceAll("&amp;", "&").replaceAll("&quot;", '"')
  .replaceAll(/<[^>]*>/g, "").replaceAll(/\s+/g, " ").trim();

const isRestricted = (value) => {
  const normalized = decode(value).toLocaleLowerCase("pt-BR");
  const compact = normalized.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9\u3400-\u9fff]+/g, "");
  const compactBrands = restricted.map((brand) => brand.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-z0-9\u3400-\u9fff]+/g, ""));
  const disguisedShortBrand = /(?:^|[^a-z])(l\W*v|c\W*h|g\W*g|y\W*s\W*l)(?:[^a-z]|$)/i.test(normalized);
  return disguisedShortBrand || compactBrands.some((brand) => brand.length > 1 && compact.includes(brand));
};

function extractAlbums(html, source, categoryId, category) {
  const pattern = /href="\/albums\/(\d+)[^"]*"[^>]*>[\s\S]*?data-src="([^"]+)"[\s\S]*?album__title">([\s\S]*?)<\/div>/g;
  const items = [];
  for (const match of html.matchAll(pattern)) {
    const name = decode(match[3]);
    if (!name || isRestricted(name)) continue;
    items.push({
      id: `${source.id}-${match[1]}`,
      name,
      category,
      detail: "Disponibilidade sujeita à confirmação",
      image: match[2].replace("/small.", "/medium."),
      sourceUrl: `${source.baseUrl}/albums/${match[1]}?referrercate=${categoryId}`,
      supplier: source.id,
      available: true,
      lastCheckedAt: new Date().toISOString(),
      reviewStatus: "pending",
    });
  }
  return items;
}

async function fetchPage(url) {
  const response = await fetch(url, {
    headers: { "user-agent": "Mozilla/5.0 (compatible; VIPImportsCatalog/1.0)" },
  });
  if (!response.ok) throw new Error(`${response.status} em ${url}`);
  return response.text();
}

const products = [];
const report = [];
for (const source of suppliers) {
  for (const [categoryId, category] of source.categories) {
    let imported = 0;
    try {
      for (let page = 1; page <= 3; page += 1) {
        const html = await fetchPage(`${source.baseUrl}/categories/${categoryId}?page=${page}`);
        const pageItems = extractAlbums(html, source, categoryId, category);
        products.push(...pageItems);
        imported += pageItems.length;
        if (!html.includes(`page=${page + 1}`)) break;
      }
      report.push({ supplier: source.id, category, imported, status: "ok" });
    } catch (error) {
      report.push({ supplier: source.id, category, imported, status: error.message });
    }
  }
}

const unique = [...new Map(products.map((product) => [product.id, product])).values()];
await writeFile(new URL("../data/pending-products.json", import.meta.url), JSON.stringify(unique, null, 2) + "\n");
console.table(report);
console.log(`Produtos enviados para revisão: ${unique.length}`);
