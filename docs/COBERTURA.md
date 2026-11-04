# Cobertura dos catálogos de regras

## Fundações da Fase 0 desta rodada

- Testes de ataque podem usar Luta/Pontaria com a Defesa do alvo como DT; a seção de dano aceita resultados físicos, considera o multiplicador crítico apenas nos dados e registra o resultado na mesma tabela de rolagens. O rolador digital é alternativo.
- Painel de combate exclusivo do mestre registra cenas, participantes de ficha ou ameaças com nome manual, iniciativa física, surpresa e ordem fixa de turnos. Registra ações padrão/movimento/completa e uma reação defensiva por rodada. O mestre pode aplicar dano informado fisicamente à ficha selecionada; ao reduzir PV a zero, registra Inconsciente/Morrendo. Curar 1 PV remove Inconsciente, mas não Morrendo. O mestre confirma o sucesso físico de Medicina DT 20 para estabilizar; três turnos iniciados Morrendo na mesma cena marcam a ficha como morta. Ações, danos e estabilizações ficam auditados. Não há mapa virtual nem dados do painel em páginas/API de jogadores.
- Dano/cura de PV com limite, absorção inicial por PV temporários, indicação do aplicado/excedente e auditoria de cada valor alterado.
- Ficha oferece ajustes de recursos em −5, −1, +1, +5 e por valor digitado, incluindo PV temporários; PV temporários são limitados a zero, auditados e sincronizados no polling. PE/PV/SAN/PD continuam limitados pelos máximos calculados.
- Modo sessão opcional amplia a fonte e aumenta contraste na tela atual. O bloqueio de tela usa Screen Wake Lock se houver suporte; falhas e indisponibilidade são informadas. Não é uma preferência de conta e ainda precisa de teste em aparelho real.
- Fichas arquivadas, mortas e aposentadas não aceitam edição, recursos, condições, rolagens, inventário nem avanço de NEX pelo dono; o mestre mantém acesso. Arquivamento/restauração pelo dono permanece disponível.
- Rate limit por usuário nas operações de inventário, alteração de status, avanço de NEX, edição e configuração da mesa.
- Token CSRF no meta tag do template base; o JavaScript o lê sem depender de um formulário oculto. O cookie continua HttpOnly.
- Testes físicos como fluxo principal: instrução de dados/bônus calculada pela ficha, entrada validada de resultados d20, seleção maior/menor conforme regra já centralizada e comparação opcional com DT. A rolagem digital continua disponível como alternativa.
- Resposta do teste apresenta a quantidade/ordem final dos dados e detalha condição, treinamento e bônus por linha; o cálculo usa `parametros_teste`, inclusive para pools que caem abaixo de um dado.
- Interface da ficha responsiva em telas pequenas, com grade de recursos em duas colunas, navegação de seções quebrável, alvos de botão com altura mínima de 44px e foco visível para teclado.
- Painel do mestre acessível somente a superusuários, com contagens por status, fichas da mesa e 25 rolagens recentes; polling atualiza a lista e novas rolagens a cada 5 segundos. Jogador recebe 403 e a home não revela link nem dados do painel.
- Painel do mestre atualiza a cada 5 segundos e permite aplicar uma condição a até 50 fichas ativas selecionadas. A ação é exclusiva do mestre, rate-limited e auditada por ficha; fichas inativas e IDs inválidos não são aceitos.
- Histórico de rolagens paginado e filtrável por ficha visível; jogadores não recebem rolagens secretas nem conseguem consultar fichas alheias, enquanto o mestre pode consultar todas.
- Polling autenticado da ficha a cada 30 segundos, pausado quando a página não está visível; atualiza recursos, máximos e condições sem expor anotações ou recursos ocultos pelo modo da mesa.
- Condições exibem resumo mecânico e aplicam efeitos numéricos catalogados em testes e Defesa. Escaladas substituem a condição ativa e geram auditoria; efeitos que dependem do alvo/ação são informativos. Duração opcional por ficha (1–99 turnos) é reduzida no início do turno do afetado, expira com auditoria e é preservada ao escalar; Morrendo mantém seu contador próprio. Ao encerrar combate, condições marcadas para terminar com a cena são removidas e auditadas; as persistentes permanecem.
- O rastreador bloqueia ações normais com Atordoado/Pasmo, ação completa com Enjoado e ações/reação com Inconsciente. A permissão é validada no servidor; restrições dependentes de contexto, como ações mentais, ainda não são modeladas.
- O carregador valida os efeitos estruturados das condições antes de gravar; campos desconhecidos, booleanos e modificadores fora do limite abortam a transação com erro explícito.
- Cicatrizado do Sobrevivente é registrado como pendência no estágio 5. A ficha lembra o perigo e aplica −1 dado somente quando o jogador identifica um teste de resistência contra esse perigo; a reação é limitada à sessão corrente e o mestre reinicia a sessão pelo painel.
- Testes aplicam automaticamente penalidade de sobrecarga às perícias indicadas no catálogo e perguntam se o kit necessário está disponível; a resposta do servidor calcula ambos os modificadores.
- Requisitos de desenvolvimento separados dos utilitários de PDF; CI sem dependências PDF, com verificação de migrações e `check --deploy` em ambiente simulado.
- Em 2026-11-04, o proprietário informou que alterou a visibilidade do GitHub para privado. Dados pessoais e conteúdo de terceiros ainda exigem controle de acesso e autorização; a privacidade do repositório não equivale a licença de redistribuição.

## Carregamento da Fase 2

O comando `python manage.py carregar_regras` carrega JSONs locais em uma transação e atualiza cada registro pelo `slug`. Uma segunda execução não duplica registros. O banco contém 126 registros desta carga:

| Catálogo | Quantidade | Fonte impressa |
| --- | ---: | --- |
| Atributos | 5 | OPRPG p.14 |
| Perícias | 28 | OPRPG p.41 |
| Classes e progressões | 4 | OPRPG pp.25, 29 e 33; SaH pp.30-33 |
| Condições | 38 | OPRPG pp.310-311 |
| Patentes | 5 | OPRPG p.52; SaH p.108 |
| Origens do livro básico | 26 | OPRPG pp.16-21 |
| Origens do suplemento | 20 | SaH pp.7-13 |

Todos os registros têm `fonte`, `slug` e indicação de `personalizado`. Os resumos são mecânicos e curtos, escritos para a ficha; nenhum capítulo ou bloco longo dos livros foi copiado.

O campo `Poder.pre_requisitos` agora valida e aplica um schema neutro e cumulativo: `classe_slug`, `trilha_slug`, `nex_min`, `estagio_min`, `atributos_min`, `pericias_treinadas` e `poderes`. O seletor de progressão só oferece poderes cujos requisitos a ficha satisfaz; a validação é repetida no POST com a ficha bloqueada. O carregador rejeita campos desconhecidos e valores fora do formato. Os JSONs continuam sem entradas de livro; a implementação do schema não inclui requisitos derivados de conteúdo licenciado.

## Conferências realizadas

- A tabela 2.1 foi conferida no TXT OPRPG PDF p.51, correspondente à página impressa 41. As 28 entradas têm atributo-base; os marcadores de treinamento, penalidade de carga e kit foram transpostos da tabela.
- As características e tabelas de NEX de Combatente, Especialista e Ocultista foram lidas em OPRPG pp.25, 29 e 33. A tabela de NEX confirma progressão de limite de PE de 1 a 19 e 20 em NEX 99% (OPRPG p.23). A tabela do Ocultista registra círculos de rituais nos marcos correspondentes.
- Sobrevivente e progressão por estágio foram lidos em SaH pp.30-33. As fórmulas opcionais de PD foram conferidas em SaH p.104.
- As condições e suas escaladas foram conferidas no apêndice OPRPG pp.310-311. As escaladas registradas incluem Abalado→Apavorado, Fraco→Debilitado→Inconsciente, Fatigado→Exausto→Inconsciente e Frustrado→Esmorecido. Condições terminam no fim da cena por padrão, conforme o apêndice.
- Efeitos estruturados continuam limitados a modificadores numéricos diretos de dados e Defesa. O rastreador também bloqueia ações normais com Atordoado/Pasmo, ação completa com Enjoado e ações/reação com Inconsciente; duração opcional é contada por ficha no início do turno. Contexto de alvo/ataque, ações mentais, deslocamento, percepção sensorial, iniciativa e durações específicas do catálogo ainda não são automatizados.
- Patentes, crédito e limites por categoria foram conferidos na tabela 3.1 do OPRPG p.52.
- A evolução por patentes foi conferida em SaH pp.108-109: limites de PD por patente, recuperação, faixas de prestígio e recompensas/perdas por missão. A promoção usa o limite de PD como nível equivalente para benefícios de classe; perda de prestígio não rebaixa a patente.
- Origens do básico foram cruzadas com a tabela 1.1 e as entradas OPRPG pp.16-21; as novas origens foram cruzadas com SaH pp.7-13. Amnésico e Profetizado mantêm suas escolhas livres nos campos apropriados; especializações de Profissão são registradas separadamente.
- A tabela de perícias de duas colunas foi comparada visualmente à página renderizada OPRPG PDF p.51; a ordem extraída da coluna esquerda para a direita está correta nessa amostra.
- A página física 50 do PDF OPRPG (página impressa 40) foi renderizada: ela contém os trechos de teste de perícia, atributo-base e bônus de perícia. A regra de atributo-base e bônus é exercitada por `bonus_pericia` e pelos testes do fluxo de rolagem.
- A carga é calculada com os itens e espaços efetivamente cadastrados; excesso reduz Defesa em 5 e aplica −5 em perícias marcadas com penalidade de carga. Para perícias com kit, o jogador informa se o possui; a ausência aplica −5, sem alterar os itens do inventário.

## Fora desta carga

- O carregador agora aceita trilhas, poderes, rituais e itens de OPRPG/SaH, com arquivos JSON inicialmente vazios. Os modelos também podem ser mantidos pelo admin restrito ao superusuário; os registros ainda dependem de curadoria e conferência antes de serem adicionados.
- Armas, proteções, equipamentos e itens amaldiçoados ainda não têm registros de catálogo; o inventário manual segue disponível.
- Trilhas, poderes, rituais e itens ainda dependem de curadoria e de dados mecânicos curtos nos JSONs.
- Dados da comunidade e conteúdo personalizado: nada foi importado; serão incluídos somente por criação própria do mestre.

## Progressão por NEX (Fase 4)

- No modo padrão, o mestre pode avançar fichas de Combatente, Especialista e Ocultista para um NEX maior entre 5% e 99%. O jogador só pode fazê-lo quando `jogador_pode_subir_nex` está habilitado.
- O NEX, a versão da ficha, o registro de auditoria e as escolhas pendentes dos marcos são atualizados na mesma transação. Os máximos de recursos são derivados dos cálculos já existentes após o avanço.
- A tela exibe pendências de trilha, poderes, aumento de atributo, treinamento e rituais geradas pela função de progressão. As escolhas podem ser resolvidas e auditadas; catálogos ainda vazios oferecem também uma escolha personalizada com resumo curto.
- Sobrevivente avança por estágios 1–5, sem NEX. O mestre pode avançar estágio com versão otimista, auditoria e geração transacional de pendências conforme SaH pp.30-31. O formulário só aparece antes do estágio 5; a lista de habilidades do estágio atual é informativa. No estágio 5, o perigo de Cicatrizado é registrado e a reação pode ser usada uma vez por sessão, sacrificando permanentemente 1 PV máximo ou 1 PE/PD máximo, conforme a reação escolhida.
- Ferimentos Debilitantes podem ser ativados na configuração da mesa. O mestre registra o atributo afetado e controla os passos de Medicina DT 20 e recuperação após dormir; dados afetados penalizam testes e ferimentos em Vigor reduzem PV máximos com base em NEX/nível. O rastreador de combate não automatiza o gatilho de dano massivo.
- A opção Nível de Experiência e Nível de Exposição separa nível (1–20) e NEX (0–99%). Níveis avançam separadamente e geram escolhas nos marcos equivalentes de NEX; exposições são registradas pelo mestre, com limites e auditoria. Aprender ritual como Ocultista soma ao NEX o círculo do ritual. O cálculo de PV/PE/SAN/PD usa o nível como equivalente a NEX e o NEX permanece disponível para efeitos de exposição.
- A evolução por patentes exige modo Sem Sanidade (PV/PD), inicia personagens compatíveis como Recrutas, registra os eventos de prestígio por ficha e promove sem rebaixar patente quando o total diminui. Solução é limitada a uma e pistas adicionais a três por ficha/missão; perdas por morte aceitam quantidade. Promoção gera escolhas de classe, atualiza os máximos e recursos atuais de PV/PD, e a ficha mostra limite de PD por turno e recuperação por patente. Dormir/relaxar recupera o valor definido pela patente, sem ultrapassar o máximo. O registro e as mudanças são auditados.
- Rastreador de combate registra gastos de PE/PD por turno, desconta o recurso da ficha atomicamente, audita a alteração e rejeita gastos acima do limite ou do saldo. PE respeita o limite de classe/NEX; PD respeita o limite da patente no modo Sem Sanidade. A contagem zera quando o participante inicia o turno seguinte.
- A progressão da mesa deve ser escolhida antes da criação das fichas e fica bloqueada depois que existe qualquer ficha, para evitar converter estado ambíguo entre NEX, nível e exposição. Em evolução por patentes, o limite de PD da patente é usado como nível equivalente para cálculos de recursos e marcos de classe.

## Inventário manual (Fase 5)

- Jogadores gerenciam itens personalizados da própria ficha; mestres podem gerenciar qualquer ficha. O formulário não aceita IDs de ficha, catálogo ou JSON adicional.
- Quantidade, estado, categoria e espaços usam listas/limites explícitos. A ficha mostra a carga total calculada com `espacos_usados` e a capacidade por Força; exceder a capacidade é sinalizado, não impede registrar itens.
- O catálogo completo de equipamentos, armas e proteções não foi carregado nesta fase; nomes e descrições dos livros continuam fora dos dados de inventário manual.

## Equipamento, cenas e recursos do mestre (Fases 7–9)

- O inventário manual permite cadastrar equipamento próprio na ficha, inclusive espaços, quantidade, categoria, estado e notas. O catálogo de livro continua sem carga por estar pendente de curadoria autorizada; não foram copiados itens licenciados.
- `CenaMesa` guarda tipo, descrição para jogadores e anotações exclusivas do mestre. Cenas são criadas ocultas e só ficam acessíveis a jogadores depois de publicadas. `PistaCena` permanece oculta até o mestre revelar ou marcar como anotada. As views filtram cenas e pistas antes de renderizar, sem enviar segredos em campos ocultos.
- Criar/editar/arquivar cenas e pistas é restrito ao superusuário, usa POST protegido por CSRF, limites de taxa e registros de auditoria.
- O bestiário `AmeacaMesa` aceita estatísticas, ações e anotações próprias/autorizadas. É privado ao mestre, permite editar e arquivar, e registra autoria/auditoria sem copiar texto sensível ao log. O mestre pode vincular ameaça ativa a um combate; suas informações aparecem somente no roster privado.
- O bestiário não contém dados de livros e não automatiza PV atual, ataques ou dano de ameaças; esses valores continuam sob controle manual. O catálogo de equipamento não foi pré-preenchido, aguardando curadoria autorizada.
- O manifesto e o service worker habilitam instalação em navegadores compatíveis e servem uma página offline genérica. Apenas CSS, ícone e manifesto são cacheados; documentos HTML de páginas autenticadas, respostas da API e informações da mesa não entram no cache.

## Configuração da mesa (Fase 6)

- O painel de configurações é restrito ao superusuário e expõe modo de recursos, progressão, permissão de avanço pelos jogadores, limite de fichas ativas e Ferimentos Debilitantes. A combinação de evolução por patentes com modo Sem Sanidade é validada pelo formulário.
- O limite de fichas ativas é verificado ao iniciar e ao concluir a criação. Fichas ativas podem ser arquivadas/restauradas; a restauração respeita o limite e todas as transições usam a versão otimista da ficha.
- O controle de sessão é restrito ao mestre, incrementa `ConfiguracaoMesa.numero_sessao` e é usado para limitar Cicatrizado. Se ainda não houver configuração salva, a rota cria o singleton e inicia na sessão 2.
- A configuração da mesa permite ativar Ferimentos Debilitantes. O mestre registra, trata e cura cada ferimento em operações auditadas; os efeitos mecânicos são aplicados pela ficha, sem automatizar o teste de dano massivo que os origina.

## Limitações de extração

O extrator cria um TXT por página física do PDF. Para o miolo do OPRPG, as amostras confirmam que a página impressa equivale à página PDF menos 10; o campo `fonte` usa a página impressa. Para SaH, as páginas impressas foram conferidas individualmente e não se aplica o deslocamento do livro básico.

As páginas OPRPG PDF p.2, 3, 4, 5, 7, 10, 14, 15, 16, 22, 48, 60, 78, 104, 162, 186, 304 e 331, e SaH PDF p.7, 63, 125 e 167 são imagens sem camada de texto. Não foram usadas como base desta carga; qualquer regra que dependa delas requer conferência visual. A cobertura deve ser revista antes das prioridades seguintes.