"""Extrai texto local de cada página dos livros, respeitando a ordem das colunas."""

import argparse
from pathlib import Path

import pymupdf

RAIZ = Path(__file__).resolve().parents[1]

FONTES = {
    'OPRPG': (
        'ordem-paranormal-rpg-v1-3.pdf',
        (
            RAIZ / 'docs' / 'regras' / 'ordem-paranormal-rpg-v1-3.pdf',
            RAIZ / 'docs' / 'ordem-paranormal-rpg-v1-3.pdf',
        ),
    ),
    'SaH': (
        'Sobrevivendo_Ao_Horror_v1_2.pdf',
        (
            RAIZ / 'docs' / 'regras' / 'Sobrevivendo_Ao_Horror_v1_2.pdf',
            RAIZ / 'docs' / 'Sobrevivendo Ao Horror v1.2.pdf',
            RAIZ / 'docs' / 'Sobrevivendo_Ao_Horror_v1_2.pdf',
        ),
    ),
}


def localizar_pdf(chave: str, caminho_informado: Path | None) -> Path:
    if caminho_informado:
        caminho = caminho_informado
        if not caminho.is_absolute():
            caminho = RAIZ / caminho
        if not caminho.is_file():
            raise FileNotFoundError(f'PDF não encontrado: {caminho}')
        return caminho

    nome, candidatos = FONTES[chave]
    for caminho in candidatos:
        if caminho.is_file():
            return caminho
    raise FileNotFoundError(
        f'PDF de {chave} não encontrado. Coloque {nome} em docs/regras/ '
        'ou informe o caminho com a opção correspondente.'
    )


def extrair_texto_pagina(pagina: pymupdf.Page) -> str:
    blocos = []
    for bruto in pagina.get_text('blocks', sort=False):
        if len(bruto) < 7 or bruto[6] != 0 or not bruto[4].strip():
            continue
        blocos.append(
            {
                'x0': bruto[0],
                'y0': bruto[1],
                'x1': bruto[2],
                'y1': bruto[3],
                'texto': bruto[4].strip(),
            }
        )

    if not blocos:
        return ''

    meio = pagina.rect.width / 2
    largura_coluna = pagina.rect.width * 0.72
    abrangentes = [b for b in blocos if b['x1'] - b['x0'] >= largura_coluna]
    colunas = [b for b in blocos if b not in abrangentes]
    esquerda = [b for b in colunas if (b['x0'] + b['x1']) / 2 < meio]
    direita = [b for b in colunas if (b['x0'] + b['x1']) / 2 >= meio]

    sobreposicoes = sum(
        min(a['y1'], b['y1']) - max(a['y0'], b['y0']) > pagina.rect.height * 0.015
        for a in esquerda
        for b in direita
    )
    duas_colunas = len(esquerda) >= 2 and len(direita) >= 2 and sobreposicoes >= 2

    def ordenar_faixa(faixa):
        if duas_colunas:
            return sorted(
                (b for b in faixa if b in esquerda), key=lambda b: (b['y0'], b['x0'])
            ) + sorted(
                (b for b in faixa if b in direita), key=lambda b: (b['y0'], b['x0'])
            )
        return sorted(faixa, key=lambda b: (b['y0'], b['x0']))

    if not duas_colunas or not abrangentes:
        ordenados = ordenar_faixa(blocos)
    else:
        ordenados = []
        restantes = list(colunas)
        for separador in sorted(abrangentes, key=lambda b: (b['y0'], b['x0'])):
            faixa = [b for b in restantes if b['y0'] < separador['y0']]
            ordenados.extend(ordenar_faixa(faixa))
            restantes = [b for b in restantes if b not in faixa]
            ordenados.append(separador)
        ordenados.extend(ordenar_faixa(restantes))

    return '\n\n'.join(bloco['texto'] for bloco in ordenados).strip()


def extrair_livro(chave: str, origem: Path, destino: Path) -> int:
    pasta = destino / chave
    pasta.mkdir(parents=True, exist_ok=True)
    documento = pymupdf.open(origem)
    total_paginas = documento.page_count
    try:
        for indice, pagina in enumerate(documento):
            conteudo = extrair_texto_pagina(pagina)
            arquivo = pasta / f'pagina-{indice + 1:03}.txt'
            arquivo.write_text(conteudo, encoding='utf-8')
    finally:
        documento.close()
    return total_paginas


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Gera um arquivo de texto por página dos PDFs locais.'
    )
    parser.add_argument('--oprg', type=Path, help='Caminho do PDF do livro básico.')
    parser.add_argument('--sah', type=Path, help='Caminho do PDF do suplemento.')
    parser.add_argument(
        '--saida',
        type=Path,
        default=RAIZ / 'docs' / 'regras' / 'texto',
        help='Pasta de saída (padrão: docs/regras/texto).',
    )
    args = parser.parse_args()
    destino = args.saida if args.saida.is_absolute() else RAIZ / args.saida

    for chave, argumento in (('OPRPG', args.oprg), ('SaH', args.sah)):
        origem = localizar_pdf(chave, argumento)
        paginas = extrair_livro(chave, origem, destino)
        print(f'{chave}: {paginas} páginas extraídas para {destino / chave}')


if __name__ == '__main__':
    main()