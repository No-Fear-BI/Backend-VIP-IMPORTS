import { spawnSync } from 'node:child_process';
import { readFile, writeFile, rename, copyFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';

const fornecedores = [
  { id: 'qwer888', base: 'https://1234qwer888.x.yupoo.com', caminho: '/categories' },
  { id: 'jypj', base: 'https://jypj.x.yupoo.com', caminho: '/categories/4836989', categoria: 'Bolsas' },
];
const arquivo = new URL('../data/pending-products.json', import.meta.url);
export const decodificar = (texto) => texto.replace(/&#x([\da-f]+);/gi, (_, n) => String.fromCodePoint(parseInt(n, 16))).replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n))).replaceAll('&quot;', '"').replaceAll('&apos;', "'").replaceAll('&amp;', '&').replaceAll('&nbsp;', ' ');
export function extrair(html, fornecedor = fornecedores[0]) {
  const itens = [];
  const padrao = /href="\/albums\/(\d+)[^"]*"[^>]*>(?:(?!href="\/albums\/)[\s\S])*?<img\b[^>]*?\s(?:data-src|src)="(https?:\/\/[^\"]+)"[\s\S]*?album(?:3)?__title">([\s\S]*?)<\/div>/g;
  for (const m of html.matchAll(padrao)) {
    const nome = decodificar(m[3].replace(/<[^>]*>/g, '')).replace(/\s+/g, ' ').trim();
    if (!nome) throw new Error(`Álbum ${m[1]} sem título`);
    itens.push({ id: `${fornecedor.id}-${m[1]}`, name: nome, category: fornecedor.categoria || 'A classificar', detail: 'Disponibilidade sujeita à confirmação', image: decodificar(m[2]).replace('/small.', '/medium.'), sourceUrl: `${fornecedor.base}/albums/${m[1]}`, supplier: fornecedor.id, available: true, lastCheckedAt: new Date().toISOString(), reviewStatus: 'pending' });
  }
  return itens;
}
export function totais(html) {
  const albuns = /in total\s+(\d+)\s+albums/i.exec(html);
  const paginas = /in total\s+(\d+)\s+pages/i.exec(html) || /categories__box-right-pagination-span">\s*\d+\s*\/\s*(\d+)/.exec(html);
  if (!paginas) throw new Error('Página sem totais reconhecidos; importação cancelada.');
  return { albuns: albuns ? Number(albuns[1]) : null, paginas: Number(paginas[1]) };
}
async function baixar(fornecedor, pagina) {
  let erro;
  for (let tentativa = 0; tentativa < 4; tentativa++) {
    try {
      const resposta = await fetch(`${fornecedor.base}${fornecedor.caminho}?page=${pagina}`, { headers: { 'user-agent': 'Mozilla/5.0 (compatible; VIPImportsCatalog/1.0)' }, signal: AbortSignal.timeout(45000) });
      if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
      return await resposta.text();
    } catch (falha) {
      erro = falha;
      if (tentativa < 3) await new Promise(r => setTimeout(r, 1500 * (tentativa + 1)));
    }
  }
  throw new Error(`Falha na página ${pagina}: ${erro.message}`);
}
export function mesclar(anteriores, coletados) {
  const mapa = new Map(anteriores.map(p => [p.id, p]));
  for (const p of coletados) {
    const anterior = mapa.get(p.id);
    mapa.set(p.id, { ...p, category: p.category !== 'A classificar' ? p.category : (anterior?.category || p.category), ...(anterior?.brand ? { brand: anterior.brand } : {}) });
  }
  return [...mapa.values()];
}
// Fontes da coleta. Sem arquivo: só os fornecedores embutidos. Com arquivo: os links dele e, com
// `incluirPadrao`, também os embutidos que o arquivo não cobre (o qwer888 não está no arquivo, e
// listá-lo por link daria o id `1234qwer888-…`, que repetiria todos os álbuns já na fila).
export function montarFontes(links, incluirPadrao = false) {
  if (!links) return fornecedores;
  const doArquivo = [...new Set(links)].map(link => {
    const url = new URL(link);
    if (url.protocol !== 'https:' || !url.hostname.endsWith('.x.yupoo.com')) throw new Error('Fornecedor inválido');
    const categoria = url.hostname === 'jyxzfz.x.yupoo.com' && url.pathname === '/categories/2986404'
      ? 'Cintos'
      : url.hostname === 'jyxzfz.x.yupoo.com' && url.pathname === '/categories/3709412'
        ? 'Bolsas'
        : undefined;
    return { id: url.hostname.split('.')[0], base: url.origin, caminho: url.pathname, ...(categoria ? { categoria } : {}) };
  });
  if (!incluirPadrao) return doArquivo;
  const jaCobertos = new Set(doArquivo.map(f => f.id));
  return [...doArquivo, ...fornecedores.filter(f => !jaCobertos.has(f.id))];
}
async function main() {
  const argumentos = process.argv.slice(2);
  const caminhoLista = argumentos.find(a => !a.startsWith('--'));
  const fontes = montarFontes(caminhoLista ? JSON.parse(await readFile(caminhoLista, 'utf8')) : null, argumentos.includes('--padrao'));
  const anteriores = JSON.parse(await readFile(arquivo, 'utf8'));
  const coletados = [];
  const relatoriosFornecedores = [];
  for (const fornecedor of fontes) {
    const primeira = await baixar(fornecedor, 1);
    const esperado = totais(primeira);
    const paginas = [extrair(primeira, fornecedor)];
    if (!paginas[0].length && esperado.albuns !== 0) throw new Error(`Nenhum álbum reconhecido: ${fornecedor.base}${fornecedor.caminho}`);
    console.log(`${fornecedor.id}: ${esperado.albuns ?? 'álbuns não informado'} álbuns, ${esperado.paginas} páginas.`);
    let proxima = 2;
    await Promise.all(Array.from({ length: 3 }, async () => {
      while (proxima <= esperado.paginas) {
        const numero = proxima++;
        const html = await baixar(fornecedor, numero);
        const total = totais(html);
        if (total.paginas !== esperado.paginas || (esperado.albuns && total.albuns !== esperado.albuns)) throw new Error('Catálogo mudou durante a coleta. Execute novamente.');
        const itens = extrair(html, fornecedor);
        if (!itens.length) throw new Error(`Página ${numero} vazia inesperadamente.`);
        paginas[numero - 1] = itens;
        if (numero % 10 === 0 || numero === esperado.paginas) console.log(`${fornecedor.id}: página ${numero}/${esperado.paginas}`);
        await new Promise(r => setTimeout(r, 250));
      }
    }));
    const itens = paginas.flat();
    const unicosFornecedor = new Set(itens.map(p => p.id));
    if ((esperado.albuns && unicosFornecedor.size !== esperado.albuns) || unicosFornecedor.size !== itens.length) throw new Error(`Coleta inconsistente para ${fornecedor.id}; arquivo anterior preservado.`);
    coletados.push(...itens);
    relatoriosFornecedores.push({ fornecedor: fornecedor.id, origem: `${fornecedor.base}${fornecedor.caminho}`, paginas: esperado.paginas, informado: esperado.albuns ?? null, coletados: unicosFornecedor.size });
  }
  const unicos = new Set(coletados.map(p => p.id));
  const produtos = mesclar(anteriores, coletados);
  const relatorio = { concluidoEm: new Date().toISOString(), fornecedores: relatoriosFornecedores, coletados: unicos.size, anteriores: anteriores.length, adicionados: produtos.length - anteriores.length, total: produtos.length };
  await copyFile(arquivo, new URL('../data/pending-products.backup.json', import.meta.url));
  const temporario = new URL('../data/pending-products.tmp.json', import.meta.url);
  await writeFile(temporario, JSON.stringify(produtos, null, 2) + '\n');
  await rename(temporario, arquivo);
  await writeFile(new URL('../data/sync-yupoo-report.json', import.meta.url), JSON.stringify(relatorio, null, 2) + '\n');
  console.log(JSON.stringify(relatorio, null, 2));
  // Categoria e marca sugerida pelo título dos itens novos (scripts/classificar_fila.py). Se o Python não
  // estiver à mão, a fila já foi gravada: só avisa, e o comando pode ser rodado depois.
  const classificacao = spawnSync('python', [fileURLToPath(new URL('./classificar_fila.py', import.meta.url)), '--gravar'], { stdio: 'inherit' });
  if (classificacao.status !== 0) console.warn('Aviso: não consegui classificar a fila. Rode: python scripts/classificar_fila.py --gravar');
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main().catch(erro => { console.error(erro); process.exitCode = 1; });
