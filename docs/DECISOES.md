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
- Em 2026-11-04, o proprietário informou que tornou o repositório privado. Isso reduz a exposição pública, mas não autoriza redistribuição de conteúdo protegido nem substitui práticas de minimização de dados.
- Temporizadores de condições são opcionais e definidos por instância, não derivados dos catálogos. O sistema decrementa no início do turno da ficha afetada e remove/audita ao iniciar o turno quando resta um; condições sem valor são atemporais até remoção ou encerramento da cena, e Morrendo permanece no contador próprio do combate.
- A extração usa blocos com coordenadas do PyMuPDF. Quando detecta duas colunas sobrepostas, lê a coluna esquerda antes da direita; blocos largos, como títulos, funcionam como separadores. Páginas sem texto geram arquivo vazio para preservar a correspondência de páginas.
- Nomes `pagina-NNN.txt` indicam a página física do PDF, não a paginação impressa. Para o miolo do OPRPG, as amostras confirmam página impressa = página PDF − 10; essa relação não será aplicada automaticamente a capa, páginas sem número ou outros livros.
- No momento desta decisão inicial, o repositório GitHub `samuelverissimo/MONOTOFOBIA` estava público. Em atualização posterior, o proprietário informou que o tornou privado; dados pessoais continuam sujeitos a minimização e conteúdo protegido não deve ser redistribuído sem autorização.
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

## Fundações de segurança e operação

- Registro histórico: em 2026-11-04, a API do GitHub confirmou que `samuelverissimo/MONOTOFOBIA` estava público e a conta disponível não tinha permissão administrativa para mudar a visibilidade. Posteriormente, o proprietário informou que alterou essa configuração para privado.
- `db.sqlite3`, `.env`, arquivos de log, PDFs dentro de `docs/`, textos extraídos e `docs/ARQUIVOS SECRETOS/` permanecem ignorados pelo Git. `.gitattributes` normaliza finais de linha para LF.
- O `requirements-dev.txt` contém dependências de runtime e ferramentas de desenvolvimento. PyMuPDF, usado apenas por `tools/extrair_pdf.py`, fica em `requirements-pdf.txt`; a CI não instala as dependências de PDF ou pre-commit.
- Fichas arquivadas, mortas ou aposentadas são somente leitura para o dono nos fluxos de recurso, condição, rolagem, inventário, avanço de NEX e edição. O mestre pode alterá-las; arquivar/restaurar continua sendo uma operação de status própria.
- Dano e cura de PV são limitados ao recurso disponível e ao máximo. PV temporários absorvem dano antes dos PV; o endpoint informa a quantidade aplicada e o excedente, e registra cada recurso efetivamente alterado em `LogAlteracao`.
- O token CSRF é exposto no meta tag da página para o JavaScript próprio, sem tornar o cookie CSRF legível por JavaScript (`CSRF_COOKIE_HTTPONLY=True`). HSTS preload permanece desativado enquanto o tempo de HSTS for inferior a um ano.
- As escritas solicitadas em inventário, status, avanço de NEX, edição e configuração da mesa têm rate limit por usuário. A CI também verifica alterações de migração e executa `check --deploy` com configuração de produção simulada.
- O polling do painel do mestre é de 5 segundos e limitado a 120 consultas por minuto por usuário. A alteração de condições em grupo aceita até 50 fichas ativas, sob transação e com uma entrada de auditoria por ficha.
- Os gastos de PE/PD no rastreador são acumulados por participante no turno atual, limitados pelo teto de PE da progressão ou pelo teto de PD da patente. Ao iniciar o próximo turno desse participante, o contador é zerado; gastos são debitados e auditados junto ao recurso da ficha.

## Conferência visual da página 50 do PDF OPRPG

- Corrigida a referência: a conferência anterior abriu por engano a página física 60. A página física 50 foi renderizada e contém a página impressa 40, com regra de teste de perícia, atributo-base, bônus por grau de treinamento, exigências de treinamento, penalidade de carga e kits. O texto extraído localmente corresponde ao conteúdo visível. Não inferir que a página física 50 seja a página impressa 50; no miolo do livro, a página impressa 50 é a página física 60.
- No fluxo da ficha, rolagem física é a opção padrão: o servidor valida quantidade/face dos dados e calcula o total; a DT é opcional. O botão digital permanece como alternativa. Condições catalogadas aplicam automaticamente modificadores numéricos validados a testes e Defesa; efeitos dependentes de alvo, ação, sentidos ou duração continuam como lembretes, sem serem inferidos pelo sistema.
- A página impressa 40 confirma as penalidades de carga e de falta de kit em perícias marcadas no catálogo. O sistema aplica −5 ao bônus da perícia quando houver sobrecarga ou falta do kit, respectivamente; o jogador confirma a posse do kit na ficha e a carga é derivada do inventário.
- O campo `Condicao.efeitos` aceita apenas modificadores inteiros de uma lista restrita, sem texto livre. As condições escaláveis têm ação explícita para substituir a condição pela próxima etapa, com auditoria. As notas privadas de uma condição não são incluídas no polling.
- Defesa mostrada na ficha considera Agilidade, bônus da ficha, condições e sobrecarga. Modificadores situacionais por tipo de ataque, como a Defesa de Caído, permanecem indicados no resumo, pois a ficha não tem contexto de alvo/ataque.
- O painel do mestre é uma rota separada e exige `is_mestre`; usuários comuns recebem 403. Ele exibe apenas a lista de fichas, contagens de status e as 25 rolagens mais recentes, sem renderizar anotações privadas. Uma rota de polling exclusiva atualiza fichas e busca rolagens por cursor; a home dos jogadores permanece filtrada pelo queryset de permissões e não mostra o link do painel.
- O histórico de rolagens deriva as fichas permitidas de `fichas_visiveis_para`; filtro por ficha não permitida retorna 404. Registros marcados como secretos são excluídos para jogadores e preservados para o mestre.
- A atualização entre aparelhos usa polling GET autenticado de 30 segundos apenas na página de detalhe e para enquanto a aba está oculta. O JSON usa o queryset permitido, retorna recursos e máximos do modo atual e nomes/IDs de condições; não inclui anotação da condição, notas da ficha, história ou valores de outros recursos.
- A progressão do Sobrevivente é separada do NEX: o mestre avança estágios 1–5, com versionamento otimista, auditoria e criação atômica de escolhas baseadas em SaH pp.30-31. O catálogo ainda não completo torna necessárias opções personalizadas limitadas a resumos curtos. Habilidades por estágio são informativas; efeitos que dependem da cena/sessão não são automatizados.
- A opção `jogador_pode_subir_nex` não autoriza avanço de estágio: a configuração é específica ao avanço de NEX, portanto estágio permanece uma ação exclusiva do mestre.

## Cicatrizado e controle de sessão

- SaH p. 31 estabelece que Cicatrizado é recebido no estágio 5: o personagem escolhe um perigo paranormal de um elemento já enfrentado, sofre −1 dado em testes de resistência contra esse perigo e pode usar uma reação uma vez por sessão. O sistema guarda o elemento e a descrição curta do perigo, aplica a penalidade somente a Fortitude, Reflexos ou Vontade quando o jogador confirma o alvo e compara esse valor com o perigo registrado.
- A reação permite sacrificar permanentemente 1 PV para ignorar dano mental ou custo de PE, ou 1 PE para reduzir dano físico à metade. No modo sem Sanidade, PE é substituído por PD; o sacrifício reduz o máximo correspondente e ajusta o recurso atual somente se ele exceder o novo máximo. O dano físico é informado ao registrar a reação e a ficha retorna a metade arredondada para baixo para o mestre aplicar.
- `ConfiguracaoMesa.numero_sessao` é um contador inteiro no singleton. Apenas o mestre pode iniciar uma sessão por POST protegido por CSRF e rate limit. O número usado no último Cicatrizado é guardado na ficha; uma transação e bloqueio das linhas impedem duplicação no mesmo aparelho/sessão.
- Não há relógio ou WebSocket: a sessão é iniciada manualmente pelo mestre no painel, apropriado ao uso presencial. Habilidades de Cicatrizado que exigem decisão do mestre continuam explicitadas na interface, não inferidas automaticamente.

## Ferimentos Debilitantes

- SaH p. 105 descreve um ferimento após falha em Fortitude contra dano massivo, com −1 dado em testes baseados no atributo afetado; um ferimento em Vigor reduz PV máximos em um ponto por cada NEX de 5% ou nível de experiência. A recuperação exige Medicina DT 20 e dormir.
- A mesa pode ativar a regra; o mestre registra o atributo resultante, confirma o sucesso físico do teste de Medicina e registra a recuperação após dormir. Ferimentos ativos penalizam dados no servidor; ferimentos de Vigor reduzem PV máximos e, se isso deixar PV atual acima do máximo, o valor atual é limitado com auditoria. O máximo de personagem que usa apenas estágios (Sobrevivente) não recebe esta redução, pois o texto consultado não define a conversão de estágio para NEX/nível.
- O teste de dano massivo não é detectado automaticamente pelo rastreador de combate: o gatilho precisa ser avaliado fisicamente e registrado pelo mestre, sem inferência pela aplicação.

## Nível de Experiência e Nível de Exposição

- SaH pp. 98–99 separa a competência geral (nível 1–20) da exposição paranormal (NEX 0–99%). Cada nível equivale a 5% de NEX para progressão da classe; nível 20 usa a progressão de NEX 99%. O NEX separado continua sendo alterado apenas por exposição e por aprender rituais.
- O mestre registra exposição branda (+0%), moderada (+1%), profunda (+2%) ou total (+5%). O mestre também pode registrar o aumento de NEX por aprendizado de ritual; ao resolver pendência de ritual de Ocultista, o círculo escolhido é somado automaticamente. O limite de exposição é 99%.
- A criação em modo opcional inicia personagens de classe no nível 1 e NEX 0. Avançar nível atualiza recursos e cria as mesmas escolhas de marco da progressão equivalente, sem mudar exposição. Para evitar conversões sem fatos sobre histórico paranormal, o sistema de progressão fica imutável depois da primeira ficha criada.

## Evolução por patentes

- SaH pp.108-109 define a evolução por patentes como variante de Nível de Experiência e Exposição. Cada patente determina limite de PD por turno e recuperação; para efeitos e pré-requisitos de habilidades, o nível equivale ao limite de PD da patente. Por isso, os máximos de PV/PD e os marcos de classe usam essa equivalência.
- A configuração exige o modo Sem Sanidade, e a criação atribui patente Recruta às classes compatíveis. O modelo mantém uma progressão exclusiva (NEX, estágio ou patente) e a troca de sistema permanece bloqueada após existir ficha.
- O mestre registra separadamente cada evento de prestígio por ficha e número da sessão. Solução é única por missão; pistas adicionais limitadas a três; mortes permitem quantidade. As alterações de prestígio, promoção, recursos e escolhas são transacionais e auditadas.
- Promoção automática seleciona a maior patente cujo requisito de prestígio foi atingido; uma perda de prestígio não rebaixa a patente, conforme SaH p.109. Dormir recupera PV ou relaxar recupera PD, na quantidade da patente e sem exceder máximos (SaH p.108).
- Os PDFs locais SaH pp.108-109 foram consultados para confirmar esses valores e eventos; nenhum trecho extenso foi copiado ao site. O catálogo guarda apenas os limiares mecânicos, resumos curtos e fonte impressa.

## Ataques e avaliação de dano presencial

- Ataques continuam usando o formulário de teste já existente: Luta/Pontaria, modificadores conhecidos da ficha e Defesa do alvo como DT. Assim, condições, treinamento, carga e penalidades permanecem calculados no serviço existente.
- A seção de dano recebe a expressão de dados informada pelo jogador, os resultados físicos ou usa o rolador digital opcional. O crítico multiplica somente os dados; o bônus numérico é somado uma vez, conforme `rolar_dano`.
- A operação de dano usa `Rolagem`, autorização de edição da ficha e rate limit existentes; resultados registrados ficam no histórico com a mesma filtragem de privacidade.
- O mestre pode criar cenas com participantes ligados a fichas ativas ou ameaças identificadas manualmente. A tela do combate e todas as operações são restritas a `is_mestre`; nomes de ameaças e estado de combate não são incluídos nas páginas ou respostas de jogadores.
- O mestre rola Iniciativa fisicamente e cadastra resultados; a ordem fica fixa. A interface pula participantes surpreendidos na primeira rodada. O mestre resolve fisicamente empates antes de cadastrar os resultados definitivos.
- O rastreador registra ação padrão, movimento (até duas), ação completa e uma reação defensiva por rodada. É uma anotação de uso presencial: não resolve testes, bônus, alvos, nem confirma treinamento para as reações. O mestre pode inserir o dano já calculado fisicamente e aplicá-lo à ficha participante, reaproveitando o controle de PV e auditoria existentes.
- Dano aplicado pelo painel ou por ajuste de PV que leve de PV positivo a zero registra Inconsciente e Morrendo. Curar pelo menos 1 PV remove Inconsciente, mas não Morrendo; o mestre registra sucesso físico em Medicina DT 20 para estabilizar. Ao iniciar o terceiro turno Morrendo na cena, a ficha passa a status morta. A contagem fica na associação da condição Morrendo e é auditada.
- O rastreador não é mapa tático e não automatiza gatilhos de dano massivo, alcance, cobertura, manobras ou reações. Nenhuma lista de armas ou conteúdo de livro foi adicionada ao repositório.