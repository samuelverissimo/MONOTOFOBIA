# Modelos da Fase 1

O app `fichas` estabelece os modelos-base para catálogos, personagens, recursos da mesa e registros associados. Catálogos guardam `fonte` e `personalizado`; resumos são limitados a 500 caracteres para evitar transcrição extensa. Nenhum catálogo é pré-carregado nesta fase.

- `Pericia`, `Origem`, `Classe`, `Trilha`, `Poder`, `Ritual`, `ItemCatalogo`, `Condicao` e `Patente`: base para os catálogos mecânicos.
- `ConfiguracaoMesa`: singleton identificado pela chave primária 1, com modo de recursos, progressão, ferimentos debilitantes, compartilhamento e limite de fichas.
- `Ficha`: dono, conceitos/história, progressão, atributos, recursos atuais, ajustes manuais, anotações separadas, estado e versão.
- `FichaPericia`, `FichaPoder`, `FichaRitual`, `FichaCondicao`, `ItemInventario`, `Pendencia`, `Rolagem` e `LogAlteracao`: relações e registros para as fases seguintes.

O acesso deve filtrar fichas por dono ou mestre usando `fichas.permissions`; views futuras precisam chamar essas permissões antes de ler ou alterar qualquer ficha. A migração `accounts.0001_username_case_insensitive` cria índice único funcional no username do User nativo. O comando `definir_mestre` só promove um usuário quando invocado explicitamente.