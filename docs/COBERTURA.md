# Cobertura dos catálogos de regras

## Carregamento da Fase 2

O comando `python manage.py carregar_regras` carrega JSONs locais em uma transação e atualiza cada registro pelo `slug`. Uma segunda execução não duplica registros. O banco contém 126 registros desta carga:

| Catálogo | Quantidade | Fonte impressa |
| --- | ---: | --- |
| Atributos | 5 | OPRPG p.14 |
| Perícias | 28 | OPRPG p.41 |
| Classes e progressões | 4 | OPRPG pp.25, 29 e 33; SaH pp.30-33 |
| Condições | 38 | OPRPG pp.310-311 |
| Patentes | 5 | OPRPG p.52 |
| Origens do livro básico | 26 | OPRPG pp.16-21 |
| Origens do suplemento | 20 | SaH pp.7-13 |

Todos os registros têm `fonte`, `slug` e indicação de `personalizado`. Os resumos são mecânicos e curtos, escritos para a ficha; nenhum capítulo ou bloco longo dos livros foi copiado.

## Conferências realizadas

- A tabela 2.1 foi conferida no TXT OPRPG PDF p.51, correspondente à página impressa 41. As 28 entradas têm atributo-base; os marcadores de treinamento, penalidade de carga e kit foram transpostos da tabela.
- As características e tabelas de NEX de Combatente, Especialista e Ocultista foram lidas em OPRPG pp.25, 29 e 33. A tabela de NEX confirma progressão de limite de PE de 1 a 19 e 20 em NEX 99% (OPRPG p.23). A tabela do Ocultista registra círculos de rituais nos marcos correspondentes.
- Sobrevivente e progressão por estágio foram lidos em SaH pp.30-33. As fórmulas opcionais de PD foram conferidas em SaH p.104.
- As condições e suas escaladas foram conferidas no apêndice OPRPG pp.310-311. As escaladas registradas incluem Abalado→Apavorado, Fraco→Debilitado→Inconsciente, Fatigado→Exausto→Inconsciente e Frustrado→Esmorecido. Condições terminam no fim da cena por padrão, conforme o apêndice.
- Patentes, crédito e limites por categoria foram conferidos na tabela 3.1 do OPRPG p.52.
- Origens do básico foram cruzadas com a tabela 1.1 e as entradas OPRPG pp.16-21; as novas origens foram cruzadas com SaH pp.7-13. Amnésico e Profetizado mantêm suas escolhas livres nos campos apropriados; especializações de Profissão são registradas separadamente.
- A tabela de perícias de duas colunas foi comparada visualmente à página renderizada OPRPG PDF p.51; a ordem extraída da coluna esquerda para a direita está correta nessa amostra.

## Fora desta carga

- Trilhas, poderes de classe/trilha/gerais/paranormais e rituais: ficam para a prioridade 3/4, para evitar carregar escolhas extensas antes das fases de ficha e progressão.
- Armas, proteções, equipamentos e itens amaldiçoados: ficam para a prioridade 5, com conferência de campos e categorias antes da carga.
- Opções de nível de experiência, evolução por patentes e ferimentos debilitantes: os toggles de mesa existem, mas as regras detalhadas e seus efeitos ficam para a fase do painel/configurações.
- Dados da comunidade e conteúdo personalizado: nada foi importado; serão incluídos somente por criação própria do mestre.

## Limitações de extração

O extrator cria um TXT por página física do PDF. Para o miolo do OPRPG, as amostras confirmam que a página impressa equivale à página PDF menos 10; o campo `fonte` usa a página impressa. Para SaH, as páginas impressas foram conferidas individualmente e não se aplica o deslocamento do livro básico.

As páginas OPRPG PDF p.2, 3, 4, 5, 7, 10, 14, 15, 16, 22, 48, 60, 78, 104, 162, 186, 304 e 331, e SaH PDF p.7, 63, 125 e 167 são imagens sem camada de texto. Não foram usadas como base desta carga; qualquer regra que dependa delas requer conferência visual. A cobertura deve ser revista antes das prioridades seguintes.