# Empório da Música — Agente de Atendimento

Agente de atendimento por texto para a Empório da Música, loja fictícia de instrumentos musicais em Campo Grande/MS. O agente responde sobre catálogo, preços, estoque, promoções e pedidos (consultando um banco SQLite) e sobre horários, pagamento, trocas, frete e garantia (consultando o manual de políticas da loja).

Antes de tudo, obrigado pela oportunidade. Me diverti bastante com o desafio, principalmente resolvendo as ambiguidades entre os dados e as políticas.

## Como rodar

Requisitos: Python 3.11+ e uma chave da API da Anthropic.

```bash
git clone https://github.com/Vlencio/emporio-musica-ai-agent.git
cd emporio-musica-ai-agent

python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt

cp .env.example .env        # coloque sua ANTHROPIC_API_KEY no .env

python build_db.py          # cria o database.db a partir dos CSVs
python -m agent.agent       # inicia o chat no terminal (digite "sair" para encerrar)
```

Para rodar a avaliação:

```bash
python -m evals.run_evals              # todos os casos, com juiz LLM
python -m evals.run_evals --no-judge   # só as checagens determinísticas
```

## Estrutura

```
agent/
  agent.py      # loop de conversa (tool_runner + histórico)
  prompts.py    # system prompt
  tools.py      # get_products e get_order
data/           # CSVs originais + politicas_da_loja.md
evals/          # casos de teste, script de avaliação e resultados
examples/       # conversas de exemplo
pdf/            # PDF das políticas e script de conversão para .md
build_db.py     # carga dos CSVs no SQLite
schema.sql      # schema do banco
config.py       # caminhos e variáveis de ambiente
```

## Como construí a solução

### 1. Dados

Comecei estudando os dados, para entender o que o agente precisaria consultar.

Cada CSV tinha cara de tabela de banco, e os arquivos se relacionavam entre si (pedidos → clientes, itens → pedidos e produtos, promoções → produtos). A decisão natural foi transformar tudo em um banco de dados. Escolhi o SQLite por vir embutido no Python: quem for rodar o projeto não precisa instalar nem configurar servidor.

Escrevi o schema à mão (`schema.sql`), com chaves primárias, chaves estrangeiras e `CHECK`s, e carreguei os CSVs com pandas (`build_db.py`), respeitando a ordem das tabelas por causa das FKs. Algumas decisões de modelagem:

- `orders` e `order_items` ficaram separadas (relação 1:N): os pedidos 15 e 20 têm dois itens cada.
- `order_items` usa chave primária composta `(order_id, product_id)`, já que o CSV não tem id próprio para os itens.
- `specs` ficou como JSON em uma coluna `TEXT` validada com `json_valid`, porque as chaves mudam por categoria (violões têm `top` e `scale`, baterias têm `shells` e `pieces`, teclados têm `keys`).

O PDF de políticas eu deixei para tratar junto com o agente, já que ele seria usado como contexto do modelo.

### 2. Tools

Com os dados no banco, montei as tools antes do agente, para o modelo ser construído em cima de algo já testado.

Optei por **tools com SQL fixo e parâmetros**, em vez de um agente que escreve SQL livre (text-to-SQL), por dois motivos: o banco é pequeno e as perguntas são previsíveis, então SQL livre seria complexidade sem ganho; e o banco tem dados pessoais de clientes, então deixar o modelo montar queries abriria espaço para injeção de SQL e para vazamento (um "me mostra todos os pedidos" bastaria).

- **`get_products`**: busca no catálogo com filtros opcionais (nome, categoria, faixa de preço, só com estoque). O `WHERE` é montado dinamicamente, mas os valores sempre entram por `?`. Já devolve o nome da categoria, as specs como objeto e a promoção ativa com o preço final calculado no SQL, para o modelo não fazer conta de cabeça. Quando não encontra nada, devolve também as categorias que de fato têm produtos.
- **`get_order`**: consulta os pedidos do cliente e só retorna dados se **telefone e e-mail** baterem com o mesmo cadastro. O telefone é comparado só pelos dígitos e o e-mail sem diferenciar maiúsculas, para aceitar "67998123456" e "(67) 99812-3456". Escolhi pedir os dois dados porque o e-mail sozinho não identifica o cliente: os clientes 11 e 43 compartilham o mesmo e-mail.

As duas tools montam o JSON de resposta direto no SQL (`json_object` + `json_group_array`), o que já agrupa os itens de cada pedido.

### 3. Modelo e agente

Usei o **Claude Haiku 5.5** (`claude-haiku-5-5`): é barato, rápido, segue bem o system prompt e lida bem com tool use. Também pesou a familiaridade: já desenvolvi com o SDK da Anthropic, e o decorator `@beta_tool` gera o schema da tool direto da assinatura e da docstring da função, enquanto o `tool_runner` já executa o loop de chamadas de ferramenta.

O histórico da conversa fica em memória e guarda cada passo (incluindo chamadas de tool e seus resultados), para o agente manter o contexto entre mensagens ("quanto custa o F310?" → "e tem em estoque?").

**Prompt.** Estruturei o system prompt com tags XML (`<persona>`, `<regras>`, `<contexto>`, `<politicas>`), seguindo a recomendação da Anthropic, para separar instrução de conteúdo. As regras cobrem só o que o manual não resolve sozinho ou o que é crítico: quando consultar as ferramentas, verificação de identidade, não acumular PIX com promoção, arrependimento só para compras online, escopo e prioridade das notas de interpretação.

**Políticas no prompt, sem RAG.** Converti o PDF para Markdown com `pymupdf4llm`, limpei os artefatos de página à mão e coloquei o documento inteiro no system prompt. São 8 páginas: um RAG adicionaria complexidade sem ganho. Com o documento inteiro no contexto, as notas de interpretação (abaixo) sempre chegam junto com o texto original.

**Data e hora.** A cada mensagem, o prompt recebe a data e a hora atuais no fuso de Campo Grande (`America/Campo_Grande`, uma hora atrás de Brasília), para o agente saber responder "vocês estão abertos agora?".

### 4. Avaliação

Para medir o agente, criei um conjunto de **26 casos de teste** (`evals/cases.json`), com o gabarito tirado dos dados reais. Eles cobrem catálogo, estoque e status, promoções, políticas, trocas, pedidos, segurança (pedido só pelo nome, prompt injection), fora do escopo, contexto entre turnos e dados inconsistentes. Escrevi parte dos casos e usei IA para propor outros.

Cada caso passa por duas checagens:

- **Determinística:** se chamou (ou não) a tool esperada e se valores obrigatórios ou proibidos aparecem na resposta, via regex.
- **Juiz LLM:** o Claude Sonnet 5.5, um modelo mais capaz que o avaliado, compara a conversa (com os resultados das tools e as políticas) ao comportamento esperado.

| Rodada | Resultado | O que mudou |
|---|---|---|
| 1 | 24/26 | linha de base |
| 2 | 26/26 | o juiz passou a receber as políticas (estava reprovando o WhatsApp como "inventado"); `get_products` passou a devolver as categorias disponíveis quando a busca vem vazia (o agente oferecia "outras opções de sopro", que não existem) |
| 3 | 26/26 | ajustes pontuais no prompt (ex.: oferecer o WhatsApp só quando o agente não conseguir resolver) |

Resultados completos e transcrições em `evals/results/`. Conversas de exemplo em `examples/`.

**Limites da avaliação.** Os casos foram escritos durante o desenvolvimento, e a melhoria da tool veio depois de ver uma falha, então existe risco de "estudar para a prova". O juiz é da mesma família do agente, o que as checagens determinísticas compensam só em parte. 26 casos é uma amostra pequena.

## Ambiguidades e decisões tomadas

O enunciado pede para assumir interpretações razoáveis e documentar. As decisões sobre o manual estão também no fim de `data/politicas_da_loja.md` ("Notas de interpretação"), que o prompt manda priorizar em caso de conflito. Não alterei o texto original das políticas.

**No manual de políticas**

- **Dois telefones.** A seção 1.2 traz (67) 3341-4444 como "Telefone / WhatsApp" e a seção 7 traz (67) 3321-4500 como canal principal de WhatsApp. Assumi: 3341-4444 = telefone geral; 3321-4500 = WhatsApp de atendimento.
- **Dois e-mails.** A capa traz `contato@emporiodamusica.com.br` e a seção 1.2 traz a versão com acento. Assumi que o acento é erro de digitação.
- **Parcela mínima no cartão.** A tabela diz "parcela mínima de R$ 100,00", mas a seção 3.1 define mínimos por faixa. Vale a seção 3.1.
- **Parcelamento em até 3x.** "Sem valor mínimo (exceto abaixo de R$ 50,00)" foi interpretado como parcela mínima de R$ 50,00. Ex.: R$ 120 parcela em no máximo 2x.
- **Defeito × garantia.** Troca por defeito em até 30 dias após a compra (4.2) e garantia legal de 90 dias a partir do recebimento (8.1). Assumi: até 30 dias, troca direta; de 31 a 90 dias, garantia legal com intermediação da loja.
- **Valores-limite.** "Acima de R$ 500" e "abaixo de R$ 500" não cobrem o valor exato. Assumi frete grátis a partir de R$ 500,00, inclusive. O mesmo critério vale para a combinação de formas de pagamento (a partir de R$ 2.000,00).
- **Catálogo do manual × banco.** O manual fala em mais de 300 instrumentos, incluindo sopro e cordas orquestrais, mas os dados têm 65 produtos e as categorias de sopro e cordas orquestrais estão vazias. Para disponibilidade, o banco é a fonte da verdade.
- **Black Friday.** O manual diz que ela acontece em novembro, mas não há promoção de Black Friday ativa no banco. O agente só considera as promoções ativas no sistema.

**Nos dados**

- **Totais de pedidos que não batem com os itens:** pedido 3 (2 × R$ 1.749 = R$ 3.498, total R$ 3.450) e pedido 20 (R$ 799 + R$ 689 = R$ 1.488, total R$ 1.400). `order_items` não guarda o preço unitário da época da compra, o que explicaria diferenças por promoção ou mudança de preço. Num sistema real, essa tabela teria um `unit_price`.
- **Produto `coming_soon` em pedido entregue:** o produto 130 aparece no pedido 3 (entregue) e no 14 (pendente).
- **Pedido 11** foi feito para um produto com promoção ativa de 10% e cobrado sem desconto.
- **E-mail duplicado:** os clientes 11 e 43 compartilham `bruno.martins@jmail.com`, por isso a identificação usa telefone + e-mail.
- **Nome e descrição contraditórios:** o "Music Man Bass 1X" é descrito como Fender Jazz Bass; o "Yamaha Bass 3X" como Ibanez de 5 cordas, com spec de 4; a "Bateria Yamaha Kit 1" como Pearl Export; o "Korg Synth 1 Pro" como Roland de 88 teclas, com spec de 61. O agente se baseia no nome e nas specs.
- **Nome truncado:** "Giannini GN-15 Nylon Cedr Natural" ("Cedr" em vez de "Cedro"). Deixei como está; nos testes o agente às vezes corrige o nome por conta própria.
- **`strings` muda de significado por categoria:** material (`nylon`/`steel`) em violões e ukuleles, quantidade (`"6"`, `"4"`) em guitarras e baixos.
- **Pedido 8** está como "enviado", com previsão de entrega em 28/02/2026, já vencida. O agente sinaliza o atraso.

## Limitações conhecidas

- O histórico da conversa fica em memória e se perde ao fechar o programa.
- Não há verificação de identidade além de telefone + e-mail.
- A busca por nome e categoria usa `LIKE`, que no SQLite não ignora acentos ("violoes" não encontra "Violões").
- Valores monetários estão como `REAL`. Num sistema real, seriam centavos em `INTEGER`.
- O agente não registra reclamações nem encaminha para humanos de fato: só orienta o contato pelo WhatsApp.
- Às vezes o modelo reorganiza listas (por exemplo, agrupando por tipo) e quebra a ordenação por preço que a tool devolve.

## O que faria com mais tempo

- **Revisar as políticas com a loja** para eliminar as ambiguidades acima, em vez de depender de notas de interpretação.
- **Prompt caching** das políticas no system prompt: o documento é enviado a cada chamada e é a maior parte dos tokens. Com cache, o custo e a latência caem bastante sem mudar a arquitetura. Se o manual crescesse a ponto de exigir RAG, as notas de interpretação teriam que ir para o prompt ou para os metadados dos chunks.
- **Mover para as tools as contas com regra de negócio**, como o preço no PIX, que o modelo hoje calcula de cabeça.
- **Persistir o histórico** (SQLite ou Redis) e expor o agente por uma API (FastAPI) para integrar com o WhatsApp.
- **Ampliar a avaliação** com perguntas de clientes reais, casos não vistos durante o desenvolvimento e conversas longas com um usuário simulado. Rodar a avaliação em CI a cada mudança de prompt.
- **Guardrail na saída**, checando antes do envio se a resposta não contém dados pessoais de outros clientes.

## Uso de assistentes de IA

Usei o **Claude** (claude.ai) como par de programação e revisor durante todo o projeto, e o **Claude Code** para editar arquivos (principalmente o Markdown das políticas). Meu fluxo foi:

- **Exploração dos dados:** discuti a estrutura dos CSVs e pedi ajuda para levantar inconsistências; várias das listadas acima saíram desse processo.
- **Revisão de código:** escrevi o schema, o `build_db.py` e as tools, e usei o Claude para revisar. Ele apontou, por exemplo, um erro de digitação numa FK, um `**args` que quebrava o schema da tool (e abriria brecha de SQL injection) e um espaço faltando antes do `ORDER BY`.
- **Decisões de arquitetura:** discuti alternativas (text-to-SQL × tools fixas, RAG × documento inteiro no prompt, montar JSON no SQL × em Python) e escolhi.
- **Avaliação:** o Claude escreveu a primeira versão do script de avaliação e parte dos casos de teste. Eu rodei, analisei os resultados e ajustei o agente e o próprio eval a partir deles.

As decisões e o código final são meus; a IA acelerou a revisão e me ajudou a enxergar problemas mais cedo.