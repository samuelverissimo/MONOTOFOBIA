# Como usar

## Jogadores

1. Entre com sua conta e abra uma ficha ativa.
2. Use a página como referência durante a sessão: ela mostra atributos, Defesa, perícias, recursos, condições com resumos mecânicos e inventário.
3. Ao registrar dano, os PV acima do máximo são consumidos primeiro. O dano não reduz PV abaixo de zero; o excedente não aplicado é informado.
4. Ajuste PV, PE, SAN ou PD pelos botões −5, −1, +1, +5 ou informe uma alteração inteira (por exemplo, +5). O valor regular preenche até o máximo; o restante passa a ser temporário no mesmo recurso. Diminuições consomem esse excedente primeiro. As alterações são auditadas.
5. Se desejar, marque **Alto contraste e texto ampliado** para esta tela. **Manter a tela acesa** usa a API de Screen Wake Lock quando o navegador oferece suporte; se não houver suporte, a ficha informa isso.
6. Em **Teste**, escolha atributo, perícia ou dados livres. A instrução informa quantos d20 rolar, qual resultado usar e os modificadores conhecidos de condição, treinamento e carga; o resultado mostra o detalhamento linha a linha. Se a perícia exigir kit, marque se o kit adequado está disponível. O padrão é informar os resultados físicos e, se quiser, a DT para comparar. Dados extras/penalidades manuais e bônus numéricos situacionais ficam em campos separados.
7. A opção **Rolar no site** é secundária e usa a mesma quantidade e ordem de escolha dos dados. Perícias marcadas como somente treinadas não podem ser roladas sem treinamento.
8. Para um ataque, use **Teste** com Luta ou Pontaria e informe a Defesa do alvo como DT; para o dano, use **Dano**, copiando a expressão da arma/efeito e digitando os resultados físicos. Informe o multiplicador de crítico quando aplicável; ele multiplica somente os dados, não o bônus. Ambos podem ser rolados digitalmente como alternativa e ficam no histórico.
9. Abra **Histórico de rolagens** para consultar as rolagens públicas das fichas que você pode ver. Rolagens secretas ficam visíveis somente ao mestre.
10. Fichas arquivadas, mortas ou aposentadas ficam somente para consulta. O dono pode restaurar uma ficha arquivada quando houver espaço no limite de fichas ativas; o mestre pode editar fichas inativas.
11. Use **Escalar para...** quando uma condição indicar uma próxima etapa. Penalidades numéricas compatíveis são aplicadas automaticamente; efeitos que dependem de alvo, ação ou contexto continuam descritos na condição.
12. Consulte **Pendências** na ficha para resolver escolhas de progressão; quando o catálogo ainda não tiver uma opção, use a alternativa personalizada e registre somente um resumo curto.
13. No estágio 5 do Sobrevivente, registre o perigo de Cicatrizado. Ao fazer Fortitude, Reflexos ou Vontade contra esse perigo, marque a opção correspondente para aplicar a penalidade de 1 dado. A reação de Cicatrizado pode ser usada uma vez por sessão; ela reduz permanentemente o máximo de PV ou PE/PD, de acordo com a opção.
14. Se o mestre ativar Ferimentos Debilitantes, cada ferimento ativo aplica −1 dado a testes baseados no atributo afetado. O mestre registra o atributo depois do gatilho de dano massivo, registra o sucesso em Medicina DT 20 e confirma a cura depois que o personagem dormir. Ferimentos em Vigor podem reduzir PV máximos.
15. Em **Mesas**, encontre mesas públicas ou inscreva uma ficha em mesa privada com o código. A ficha indica as mesas às quais está vinculada.
16. Em **Perfil e conta**, altere nome, usuário, e-mail ou senha, consulte o tipo de conta e saia da sessão. Jogadores não podem conceder a si mesmos permissões de mestre; o último mestre não pode remover a própria função.
17. Ao criar a ficha, defina os graus das perícias e a progressão inicial oferecida pela mesa; trilhas do catálogo só aparecem como escolha válida quando os pré-requisitos estruturados são satisfeitos. Progressões acima do início podem gerar escolhas pendentes de habilidades/poderes ainda não selecionados.

Com a ficha aberta em mais de um aparelho, recursos e condições são sincronizados por consultas leves a cada 30 segundos enquanto a página está visível.

Em navegadores compatíveis e em HTTPS (ou localhost), o site pode ser instalado como aplicativo. O service worker mantém apenas recursos estáticos; fichas, páginas autenticadas, rolagens e segredos nunca são armazenados para uso offline. Sem conexão, ele mostra uma página genérica e exige reconexão para acessar a mesa.

## Mestre

- Abra **Painel do mestre** para gerenciar mesas, fichas inscritas, cenas e pistas, histórico de rolagens e configuração da mesa. O painel é restrito a superusuários; jogadores recebem acesso negado e não recebem esses dados. O painel também permite marcar fichas ativas e aplicar uma condição em grupo.
- Configure mesas públicas ou privadas no painel. Mesas privadas usam um código numérico de oito dígitos; jogadores encontram mesas públicas ou informam o código para se inscrever com uma ficha.
- Na seção **Cenas** do painel, crie cenas de investigação, escreva descrição pública e anotações privadas, e mantenha pistas ocultas até revelá-las ou marcá-las como anotadas. Jogadores veem somente cenas ativas, descrição pública e pistas não ocultas.
- Use **Bestiário** para manter registros próprios/autorizados de ameaças. É possível editar e arquivar registros; no início do combate, selecione uma ameaça ativa para ver seus dados no roster. O bestiário e as anotações permanecem privados ao mestre. PV registrados no bestiário são referência; o rastreador ainda não controla PV de ameaças.
- Use **Combates** no painel para abrir cenas, registrar participantes e resultados físicos de Iniciativa, acompanhar turnos e marcar ações/reação. Personagens surpreendidos são pulados na primeira rodada. O mestre pode informar o dano físico já calculado e aplicá-lo à ficha vinculada; o roster pode conter ameaças sem ficha e só aparece para o mestre.
- Durante o turno do personagem ativo, o mestre pode registrar gastos de PE ou PD. O painel desconta o recurso, impede saldo insuficiente e respeita o limite de PE por turno da progressão ou o limite de PD da patente; o contador reinicia quando o personagem voltar a agir em um novo turno.
- Ao ajustar PV de um valor positivo a zero, Inconsciente e Morrendo são registradas. O mestre pode confirmar um sucesso físico em Medicina DT 20 para estabilizar; se o personagem iniciar três turnos Morrendo na mesma cena, a ficha muda para morta. O controle não resolve ataques nem automatiza alcance ou reações.
- Na seção **Histórico de rolagens** do painel, consulte e filtre as rolagens; o histórico é paginado e inclui rolagens secretas, visíveis apenas ao mestre.
- Configure as opções disponíveis na seção **Configuração** do painel. A progressão pode ser alterada mesmo depois da criação de fichas; a mudança adapta a progressão de todas as fichas à configuração global e limita os recursos atuais aos novos máximos, sem reabastecê-los.
- A evolução por patentes exige também o modo Sem Sanidade (PV/PD). As fichas mostram patente, prestígio, deslocamento e as mesas às quais estão vinculadas.
- Use **Iniciar nova sessão** no painel para renovar o uso por sessão de Cicatrizado.
- Ative Ferimentos Debilitantes em **Configurar mesa** se a campanha usar essa regra. No detalhe da ficha, o mestre registra o atributo afetado e administra tratamento/cura; o rastreador de combate não automatiza o gatilho de dano massivo.
- Avance NEX das classes que usam essa progressão ou, para Sobrevivente, avance o estágio. O avanço do Sobrevivente é exclusivo do mestre e cria as escolhas pendentes de trilha, habilidades e atributo previstas para os estágios alcançados.
- No sistema opcional, o nível representa a competência da classe e o NEX representa exposição paranormal. O mestre registra as exposições; aprendizado de ritual de Ocultista soma ao NEX o círculo escolhido. Os aumentos de nível criam as pendências dos marcos correspondentes.
- Na evolução por patentes, registre em cada ficha os eventos de prestígio da missão. Solução do caso pode ser registrada uma vez por missão; pista adicional, até três vezes; mortes aceitam uma quantidade. A ficha promove automaticamente ao atingir o próximo marco, mantém a patente após perda de prestígio e registra escolhas de classe pendentes. A ficha informa limite de PD por turno e recuperação por patente; o jogador escolhe PV ao dormir ou PD ao relaxar.
- Revise e resolva as pendências geradas pelo avanço; as alterações são auditadas. A descrição de habilidades por estágio é um lembrete, não uma automatização de efeitos que dependem da cena ou da sessão.
- O mestre pode editar fichas ativas e inativas. Alterações de ficha são registradas no histórico de auditoria.
- Arquive fichas que não devem contar no limite de fichas ativas; a restauração respeita esse limite.

## Desenvolvimento local

Siga o preparo de ambiente no [README](../README.md). As ferramentas de segurança e desenvolvimento são instaladas com `requirements-dev.txt`. O extrator de PDFs é separado e requer `python -m pip install -r requirements-pdf.txt`.

Não adicione ao Git os arquivos `.env`, `db.sqlite3`, logs, PDFs, textos extraídos ou materiais de campanha. O repositório está público; a privatização deve ser confirmada pelo proprietário antes de incluir dados da mesa.
