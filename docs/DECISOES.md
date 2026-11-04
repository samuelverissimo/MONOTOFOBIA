# Decisões de preparação das regras

## Plano

1. Extrair cada página dos PDFs localmente para texto UTF-8, mantendo as colunas em ordem de leitura.
2. Conferir páginas amostrais e registrar limitações da extração antes de usar esses textos como fonte.
3. Na Fase 1, implementar modelos, cálculos puros, permissões e comando de promoção do mestre.
4. Na Fase 2, carregar catálogos curtos com referência à página impressa; não copiar descrições extensas.
5. Nas fases seguintes, construir fichas, rolagens e painel em entregas separadas, com testes de permissão e segurança a cada fase.

## Decisões tomadas

- Os PDFs existentes estão na raiz de `docs/`, embora o caminho indicado fosse `docs/regras/`. O extrator aceita ambos os locais e grava sempre em `docs/regras/texto/OPRPG/` e `docs/regras/texto/SaH/`, sem mover nem duplicar os PDFs.
- PDFs em qualquer nível de `docs/`, textos extraídos e `docs/ARQUIVOS SECRETOS/` são ignorados pelo Git. Nenhum conteúdo de livro ou material privado será enviado ao repositório.
- A extração usa blocos com coordenadas do PyMuPDF. Quando detecta duas colunas sobrepostas, lê a coluna esquerda antes da direita; blocos largos, como títulos, funcionam como separadores. Páginas sem texto geram arquivo vazio para preservar a correspondência de páginas.
- Nomes `pagina-NNN.txt` indicam a página física do PDF, não a paginação impressa. Para o miolo do OPRPG, as amostras confirmam página impressa = página PDF − 10; essa relação não será aplicada automaticamente a capa, páginas sem número ou outros livros.
- O repositório GitHub `samuelverissimo/MONOTOFOBIA` está público. Não há arquivos de `docs/` rastreados atualmente, mas o proprietário deve torná-lo privado antes de adicionar dados da mesa ou material licenciado.
- As páginas sem texto extraível contêm imagens rasterizadas e geram TXT vazio, não sendo consideradas páginas em branco. OPRPG: PDF p. 2, 3, 4, 5, 7, 10, 14, 15, 16, 22, 48, 60, 78, 104, 162, 186, 304 e 331. SaH: PDF p. 7, 63, 125 e 167. Qualquer regra/tabela possivelmente contida nelas deve ser conferida visualmente antes de cadastrar dados.

## Pontos a confirmar no texto dos livros

- Ordem dos dados quando modificadores `+O`/`−O` levam a quantidade de dados a zero ou a valor negativo.
- Fórmulas e marcos de progressão em cada classe, em especial limites e benefícios do Sobrevivente ao usar Treinamento Especial.
- Compatibilidade e efeitos precisos das opções de nível de experiência, evolução por patentes, ferimentos debilitantes e Pontos de Determinação.
- Nomes, categorias, escaladas e duração de todas as condições; a implementação usará resumos mecânicos próprios, sem transcrição extensa.
- Páginas que contenham tabelas ou diagramas com ordem de leitura ambígua serão marcadas para conferência visual; nenhum valor será inferido apenas de uma extração embaralhada.

## Amostras de extração

- OPRPG: PDF p. 23 contém página impressa 13 e seção de criação; PDF p. 51 contém página impressa 41 e a tabela/descrição de perícias; PDF p. 320 contém página impressa 310 e o apêndice de condições.
- SaH: PDF p. 13 contém página impressa 12 e conteúdo de origens; PDF p. 41 contém página impressa 40 e tabela de equipamento.
- A página OPRPG PDF p. 51 foi renderizada e comparada com o TXT; a coluna descritiva termina antes da Tabela 2.1, confirmando a ordem após o ajuste da heurística. Páginas imagem-only permanecem pendentes de conferência visual caso sejam fonte de regras.

## Decisões da Fase 1

- O User nativo permanece. O formulário normaliza username e bloqueia os nomes reservados mesmo com espaços, pontuação simples ou variação de caixa; uma migração adiciona índice funcional `Lower(username)` para rejeitar duplicatas em caixa diferente no banco.
- Uma rolagem com atributo 0 começa com 2d20 e escolhe o menor (OPRPG p. 40). Se um atributo positivo, após penalidades, cair abaixo de 1 dado, a penalidade é invertida em dados e escolhe-se o pior valor (OPRPG p. 11). Isso corrige/complementa o resumo da solicitação. Para atributo 0 com dados extras positivos ou negativos, a implementação mantém a regra de escolher o menor; se uma regra de habilidade disser explicitamente o contrário, deve ser refinada com sua fonte.
- NEX 99 conta como o 19º aumento desde NEX 5; isso produz 156 PV para Combatente com Vigor 3. As regras e cálculos registram referências impressas; os dados de catálogo serão carregados apenas na Fase 2.