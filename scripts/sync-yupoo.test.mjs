import test from 'node:test';
import assert from 'node:assert/strict';
import { extrair, totais, mesclar, decodificar } from './sync-yupoo.mjs';
const html = '<a class="album__main" href="/albums/123?uid=1"><img data-src="https://photo.yupoo.com/test/small.jpg"></a><div class="text_overflow album__title">Gucci &amp; Nike &#x3D; &#39;teste&#39;</div>';
test('importa todos os títulos, inclusive marcas, com imagem e ID estável', () => {
  const [item] = extrair(html);
  assert.equal(item.id, 'qwer888-123');
  assert.equal(item.name, "Gucci & Nike = 'teste'");
  assert.equal(item.image, 'https://photo.yupoo.com/test/medium.jpg');
  assert.equal(item.reviewStatus, 'pending');
});
test('interpreta totais e rejeita página de bloqueio', () => {
  assert.deepEqual(totais('in total 12557 albums in total 105 pages'), { albuns: 12557, paginas: 105 });
  assert.throws(() => totais('<h1>Captcha</h1>'));
  assert.equal(decodificar('page&#x3D;2&amp;a=1'), 'page=2&a=1');
});
test('reimportação não duplica e preserva categorias e outros fornecedores', () => {
  const anteriores = [{ id: 'qwer888-123', category: 'Camisas' }, { id: 'outro-2', category: 'Bolsas' }, { id: 'qwer888-antigo', category: 'Moletons' }];
  const novos = extrair(html);
  const resultado = mesclar(anteriores, novos);
  assert.equal(resultado.length, 3);
  assert.equal(resultado[0].category, 'Camisas');
  assert.deepEqual(mesclar(resultado, novos), resultado);
  assert.deepEqual(resultado[1], anteriores[1]);
  assert.deepEqual(resultado[2], anteriores[2]);
});

test('lê imagens src e cartões album3 sem misturar álbuns', () => {
  const pagina = '<a href="/albums/1"><img src="https://photo.yupoo.com/a/medium.jpg"><div class="album__title">Primeiro</div></a>' +
    '<a href="/albums/2"><img data-src="https://photo.yupoo.com/b/small.jpg"><div class="album3__title">Segundo</div></a>';
  const itens = extrair(pagina, { id: 'loja', base: 'https://loja.x.yupoo.com' });
  assert.deepEqual(itens.map(p => [p.id, p.name]), [['loja-1', 'Primeiro'], ['loja-2', 'Segundo']]);
  assert.equal(itens[1].image, 'https://photo.yupoo.com/b/medium.jpg');
});

test('lê listagem sem total de álbuns e categoria de uma página', () => {
  assert.deepEqual(totais('in total 79 pages'), { albuns: null, paginas: 79 });
  assert.deepEqual(totais('in total 115 albums <span class="categories__box-right-pagination-span">1 / 1</span>'), { albuns: 115, paginas: 1 });
});
test('reimportação preserva a marca sugerida já gravada', () => {
  const novos = extrair(html);
  const anteriores = [{ id: novos[0].id, category: 'Camisas', brand: 'Gucci' }];
  assert.equal(mesclar(anteriores, novos)[0].brand, 'Gucci');
});
