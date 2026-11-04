# Empório da Música — Customer Service Agent

**[English](#english) · [Português](#português)**

---

## English

A text-based customer service agent for Empório da Música, a fictional musical instrument store in Campo Grande, Brazil. The agent answers questions about the catalog, prices, stock, promotions and orders (by querying a SQLite database) and about opening hours, payment, returns, shipping and warranty (by consulting the store's policy manual).

First of all, thank you for the opportunity. I really enjoyed this challenge, especially working through the ambiguities between the data and the policies.

### How to run

Requirements: Python 3.11+ and an Anthropic API key.

```bash
git clone https://github.com/Vlencio/emporio-musica-ai-agent.git
cd emporio-musica-ai-agent

python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt

cp .env.example .env        # add your ANTHROPIC_API_KEY to .env

python build_db.py          # builds database.db from the CSVs
python -m agent.agent       # starts the terminal chat (type "sair" to exit)
```

To run the evaluation:

```bash
python -m evals.run_evals              # all cases, with the LLM judge
python -m evals.run_evals --no-judge   # deterministic checks only
```

### Structure

```
agent/
  agent.py      # conversation loop (tool_runner + history)
  prompts.py    # system prompt
  tools.py      # get_products and get_order
data/           # original CSVs + politicas_da_loja.md
evals/          # test cases, evaluation script and results
examples/       # example conversations
pdf/            # policy PDF and PDF-to-Markdown script
build_db.py     # loads the CSVs into SQLite
schema.sql      # database schema
config.py       # paths and environment variables
```

### How I built it

#### 1. Data

I started by studying the data to understand what the agent would need to query.

Each CSV looked like a database table, and the files referenced each other (orders → customers, items → orders and products, promotions → products), so turning everything into a database was the natural choice. I picked SQLite because it ships with Python: whoever runs the project doesn't need to install or configure a server.

I wrote the schema by hand (`schema.sql`), with primary keys, foreign keys and `CHECK` constraints, and loaded the CSVs with pandas (`build_db.py`) in foreign-key order. Some modeling decisions:

- `orders` and `order_items` stay separate (1:N relationship): orders 15 and 20 have two items each.
- `order_items` uses a composite primary key `(order_id, product_id)`, since the CSV has no item id.
- `specs` is stored as JSON in a `TEXT` column validated with `json_valid`, because the keys change by category (acoustic guitars have `top` and `scale`, drums have `shells` and `pieces`, keyboards have `keys`).

I left the policy PDF for later, since it would be used as model context.

#### 2. Tools

With the data in the database, I built the tools before the agent, so the model would sit on top of something already tested.

I chose **fixed, parameterized SQL tools** instead of an agent that writes free-form SQL (text-to-SQL), for two reasons: the database is small and the questions are predictable, so free-form SQL would add complexity with no gain; and the database holds customer personal data, so letting the model build queries would open the door to SQL injection and data leaks (a single "show me all orders" would be enough).

- **`get_products`**: catalog search with optional filters (name, category, price range, in stock only). The `WHERE` clause is built dynamically, but values always go through `?` placeholders. It returns the category name, specs as an object and the active promotion with the final price computed in SQL, so the model doesn't do mental math. When nothing is found, it also returns the categories that actually have products.
- **`get_order`**: returns a customer's orders only when **phone and e-mail** match the same record. Phones are compared by digits only and e-mails case-insensitively, so "67998123456" and "(67) 99812-3456" both work. Both fields are required because e-mail alone doesn't identify a customer: customers 11 and 43 share the same e-mail.

Both tools build the JSON response directly in SQL (`json_object` + `json_group_array`), which also groups each order's items.

#### 3. Model and agent

I used **Claude Haiku 5.5** (`claude-haiku-5-5`): it is cheap, fast, follows the system prompt well and handles tool use well. Familiarity also mattered: I have built with the Anthropic SDK before, and the `@beta_tool` decorator generates the tool schema from the function signature and docstring, while `tool_runner` handles the tool-calling loop.

Conversation history is kept in memory and stores every step (including tool calls and their results), so the agent keeps context across messages ("how much is the F310?" → "is it in stock?").

**Prompt.** The system prompt is structured with XML tags (`<persona>`, `<regras>`, `<contexto>`, `<politicas>`), following Anthropic's recommendation, to separate instructions from content. The rules only cover what the manual doesn't settle on its own or what is critical: when to use the tools, identity verification, no stacking of the PIX discount on promotions, cancellation rights only for online purchases, scope, and the priority of the interpretation notes.

**Policies in the prompt, no RAG.** I converted the PDF to Markdown with `pymupdf4llm`, cleaned up page artifacts by hand and put the whole document in the system prompt. It is 8 pages long, so RAG would add complexity without benefit. With the full document in context, the interpretation notes (below) always arrive together with the original text.

**Date and time.** Every message injects the current date and time in Campo Grande's time zone (`America/Campo_Grande`, one hour behind Brasília) into the prompt, so the agent can answer "are you open right now?".

#### 4. Evaluation

To measure the agent, I created a set of **26 test cases** (`evals/cases.json`) with ground truth taken from the actual data. They cover catalog, stock and status, promotions, policies, returns, orders, security (orders by name only, prompt injection), out-of-scope questions, multi-turn context and inconsistent data. I wrote part of the cases and used AI to propose others.

Each case goes through two checks:

- **Deterministic:** whether the expected tool was (or wasn't) called, and whether required or forbidden values appear in the answer (regex).
- **LLM judge:** Claude Sonnet 5.5, a more capable model than the one being evaluated, compares the conversation (with tool results and the policies) against the expected behavior.

| Run | Result | What changed |
|---|---|---|
| 1 | 24/26 | baseline |
| 2 | 26/26 | the judge started receiving the policies (it was flagging the WhatsApp number as "made up"); `get_products` now returns the available categories when the search is empty (the agent was offering "other wind instruments", which don't exist) |
| 3 | 26/26 | small prompt adjustments (e.g. only offer WhatsApp when the agent can't solve the issue) |

Full results and transcripts are in `evals/results/`. Example conversations are in `examples/`.

**Limitations of the evaluation.** The cases were written during development and the tool improvement came after seeing a failure, so there is a risk of "teaching to the test". The judge is from the same model family as the agent, which the deterministic checks only partly offset. 26 cases is a small sample.

### Ambiguities and decisions

The brief asks to assume reasonable interpretations and document them. Decisions about the manual are also at the end of `data/politicas_da_loja.md` ("Notas de interpretação"), which the prompt tells the agent to prioritize in case of conflict. I did not change the original policy text.

**In the policy manual**

- **Two phone numbers.** Section 1.2 lists (67) 3341-4444 as "Phone / WhatsApp" and section 7 lists (67) 3321-4500 as the main WhatsApp channel. Assumed: 3341-4444 = general store phone; 3321-4500 = customer service WhatsApp.
- **Two e-mails.** The cover shows `contato@emporiodamusica.com.br` and section 1.2 shows an accented version. Assumed the accent is a typo.
- **Minimum credit card installment.** The table says "minimum installment R$ 100.00", but section 3.1 defines minimums by range. Section 3.1 prevails.
- **Up to 3 installments.** "No minimum (except below R$ 50.00)" was read as a R$ 50.00 minimum installment. E.g. R$ 120 can be split into at most 2 installments.
- **Defect vs. warranty.** Defect exchange within 30 days of purchase (4.2) and a 90-day legal warranty from delivery (8.1). Assumed: up to 30 days, direct exchange; from 31 to 90 days, legal warranty with the store mediating.
- **Boundary values.** "Above R$ 500" and "below R$ 500" don't cover the exact value. Assumed free shipping from R$ 500.00, inclusive. The same rule applies to combining payment methods (from R$ 2,000.00).
- **Manual catalog vs. database.** The manual mentions over 300 instruments, including wind and orchestral strings, but the data has 65 products and those categories are empty. The database is the source of truth for availability.
- **Black Friday.** The manual says it happens in November, but there is no active Black Friday promotion in the database. The agent only considers promotions active in the system.

**In the data**

- **Order totals that don't match their items:** order 3 (2 × R$ 1,749 = R$ 3,498, total R$ 3,450) and order 20 (R$ 799 + R$ 689 = R$ 1,488, total R$ 1,400). `order_items` doesn't store the unit price at purchase time, which would explain differences due to promotions or price changes. In a real system this table would have a `unit_price`.
- **`coming_soon` product in a delivered order:** product 130 appears in order 3 (delivered) and order 14 (pending).
- **Order 11** was placed for a product with an active 10% promotion and charged without the discount.
- **Duplicate e-mail:** customers 11 and 43 share `bruno.martins@jmail.com`, which is why identification uses phone + e-mail.
- **Contradictory names and descriptions:** the "Music Man Bass 1X" is described as a Fender Jazz Bass; the "Yamaha Bass 3X" as a 5-string Ibanez, with a 4-string spec; the "Yamaha Kit 1" drum set as a Pearl Export; the "Korg Synth 1 Pro" as an 88-key Roland, with a 61-key spec. The agent relies on the name and specs.
- **Truncated name:** "Giannini GN-15 Nylon Cedr Natural" ("Cedr" instead of "Cedro"). Left as is; in tests the agent sometimes corrects the name on its own.
- **`strings` means different things by category:** material (`nylon`/`steel`) for acoustic guitars and ukuleles, count (`"6"`, `"4"`) for electric guitars and basses.
- **Order 8** is "shipped" with an estimated delivery of 02/28/2026, already overdue. The agent flags the delay.

### Known limitations

- Conversation history lives in memory and is lost when the program closes.
- There is no identity verification beyond phone + e-mail.
- Name and category search uses `LIKE`, which in SQLite is accent-sensitive ("violoes" doesn't match "Violões").
- Monetary values are stored as `REAL`. In a real system they would be cents stored as `INTEGER`.
- The agent doesn't actually log complaints or hand off to humans: it only points to the WhatsApp channel.
- The model sometimes reorganizes lists (e.g. grouping by type) and breaks the price ordering returned by the tool.

### What I would do with more time

- **Review the policies with the store** to remove the ambiguities above, instead of relying on interpretation notes.
- **Prompt caching** for the policies in the system prompt: the document is sent on every call and makes up most of the tokens. Caching would cut cost and latency significantly without changing the architecture. If the manual grew enough to need RAG, the interpretation notes would have to move into the prompt or into chunk metadata.
- **Move business-rule calculations into the tools**, such as the PIX price, which the model currently computes in its head.
- **Persist the history** (SQLite or Redis) and expose the agent through an API (FastAPI) for WhatsApp integration.
- **Broaden the evaluation** with real customer questions, cases not seen during development and long conversations with a simulated user. Run the evaluation in CI on every prompt change.
- **Output guardrail** checking, before sending, that the answer doesn't contain other customers' personal data.

### Use of AI coding assistants

I used **Claude** (claude.ai) as a pair programmer and reviewer throughout the project, and **Claude Code** to edit files (mainly the policy Markdown). My workflow:

- **Data exploration:** I discussed the CSV structure and asked for help finding inconsistencies; several of those listed above came out of this process.
- **Code review:** I wrote the schema, `build_db.py` and the tools, and used Claude to review them. It caught, for example, a typo in a foreign key, a `**args` that broke the tool schema (and would have opened a SQL injection hole) and a missing space before `ORDER BY`.
- **Architecture decisions:** I discussed alternatives (text-to-SQL vs. fixed tools, RAG vs. full document in the prompt, building JSON in SQL vs. in Python) and made the calls.
- **Evaluation:** Claude wrote the first version of the evaluation script and part of the test cases. I ran it, analyzed the results and adjusted both the agent and the evaluation itself based on them.

The decisions and the final code are mine; AI sped up the review and helped me spot problems earlier.

---

## Português

Agente de atendimento por texto para a Empório da Música, loja fictícia de instrumentos musicais em Campo Grande/MS. O agente responde sobre catálogo, preços, estoque, promoções e pedidos (consultando um banco SQLite) e sobre horários, pagamento, trocas, frete e garantia (consultando o manual de políticas da loja).

Antes de tudo, obrigado pela oportunidade. Me diverti bastante com o desafio, principalmente resolvendo as ambiguidades entre os dados e as políticas.

### Como rodar

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

### Estrutura

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

### Como construí a solução

#### 1. Dados

Comecei estudando os dados, para entender o que o agente precisaria consultar.

Cada CSV tinha cara de tabela de banco, e os arquivos se relacionavam entre si (pedidos → clientes, itens → pedidos e produtos, promoções → produtos). A decisão natural foi transformar tudo em um banco de dados. Escolhi o SQLite por vir embutido no Python: quem for rodar o projeto não precisa instalar nem configurar servidor.

Escrevi o schema à mão (`schema.sql`), com chaves primárias, chaves estrangeiras e `CHECK`s, e carreguei os CSVs com pandas (`build_db.py`), respeitando a ordem das tabelas por causa das FKs. Algumas decisões de modelagem:

- `orders` e `order_items` ficaram separadas (relação 1:N): os pedidos 15 e 20 têm dois itens cada.
- `order_items` usa chave primária composta `(order_id, product_id)`, já que o CSV não tem id próprio para os itens.
- `specs` ficou como JSON em uma coluna `TEXT` validada com `json_valid`, porque as chaves mudam por categoria (violões têm `top` e `scale`, baterias têm `shells` e `pieces`, teclados têm `keys`).

O PDF de políticas eu deixei para tratar junto com o agente, já que ele seria usado como contexto do modelo.

#### 2. Tools

Com os dados no banco, montei as tools antes do agente, para o modelo ser construído em cima de algo já testado.

Optei por **tools com SQL fixo e parâmetros**, em vez de um agente que escreve SQL livre (text-to-SQL), por dois motivos: o banco é pequeno e as perguntas são previsíveis, então SQL livre seria complexidade sem ganho; e o banco tem dados pessoais de clientes, então deixar o modelo montar queries abriria espaço para injeção de SQL e para vazamento (um "me mostra todos os pedidos" bastaria).

- **`get_products`**: busca no catálogo com filtros opcionais (nome, categoria, faixa de preço, só com estoque). O `WHERE` é montado dinamicamente, mas os valores sempre entram por `?`. Já devolve o nome da categoria, as specs como objeto e a promoção ativa com o preço final calculado no SQL, para o modelo não fazer conta de cabeça. Quando não encontra nada, devolve também as categorias que de fato têm produtos.
- **`get_order`**: consulta os pedidos do cliente e só retorna dados se **telefone e e-mail** baterem com o mesmo cadastro. O telefone é comparado só pelos dígitos e o e-mail sem diferenciar maiúsculas, para aceitar "67998123456" e "(67) 99812-3456". Escolhi pedir os dois dados porque o e-mail sozinho não identifica o cliente: os clientes 11 e 43 compartilham o mesmo e-mail.

As duas tools montam o JSON de resposta direto no SQL (`json_object` + `json_group_array`), o que já agrupa os itens de cada pedido.

#### 3. Modelo e agente

Usei o **Claude Haiku 5.5** (`claude-haiku-5-5`): é barato, rápido, segue bem o system prompt e lida bem com tool use. Também pesou a familiaridade: já desenvolvi com o SDK da Anthropic, e o decorator `@beta_tool` gera o schema da tool direto da assinatura e da docstring da função, enquanto o `tool_runner` já executa o loop de chamadas de ferramenta.

O histórico da conversa fica em memória e guarda cada passo (incluindo chamadas de tool e seus resultados), para o agente manter o contexto entre mensagens ("quanto custa o F310?" → "e tem em estoque?").

**Prompt.** Estruturei o system prompt com tags XML (`<persona>`, `<regras>`, `<contexto>`, `<politicas>`), seguindo a recomendação da Anthropic, para separar instrução de conteúdo. As regras cobrem só o que o manual não resolve sozinho ou o que é crítico: quando consultar as ferramentas, verificação de identidade, não acumular PIX com promoção, arrependimento só para compras online, escopo e prioridade das notas de interpretação.

**Políticas no prompt, sem RAG.** Converti o PDF para Markdown com `pymupdf4llm`, limpei os artefatos de página à mão e coloquei o documento inteiro no system prompt. São 8 páginas: um RAG adicionaria complexidade sem ganho. Com o documento inteiro no contexto, as notas de interpretação (abaixo) sempre chegam junto com o texto original.

**Data e hora.** A cada mensagem, o prompt recebe a data e a hora atuais no fuso de Campo Grande (`America/Campo_Grande`, uma hora atrás de Brasília), para o agente saber responder "vocês estão abertos agora?".

#### 4. Avaliação

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

### Ambiguidades e decisões tomadas

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

### Limitações conhecidas

- O histórico da conversa fica em memória e se perde ao fechar o programa.
- Não há verificação de identidade além de telefone + e-mail.
- A busca por nome e categoria usa `LIKE`, que no SQLite não ignora acentos ("violoes" não encontra "Violões").
- Valores monetários estão como `REAL`. Num sistema real, seriam centavos em `INTEGER`.
- O agente não registra reclamações nem encaminha para humanos de fato: só orienta o contato pelo WhatsApp.
- Às vezes o modelo reorganiza listas (por exemplo, agrupando por tipo) e quebra a ordenação por preço que a tool devolve.

### O que faria com mais tempo

- **Revisar as políticas com a loja** para eliminar as ambiguidades acima, em vez de depender de notas de interpretação.
- **Prompt caching** das políticas no system prompt: o documento é enviado a cada chamada e é a maior parte dos tokens. Com cache, o custo e a latência caem bastante sem mudar a arquitetura. Se o manual crescesse a ponto de exigir RAG, as notas de interpretação teriam que ir para o prompt ou para os metadados dos chunks.
- **Mover para as tools as contas com regra de negócio**, como o preço no PIX, que o modelo hoje calcula de cabeça.
- **Persistir o histórico** (SQLite ou Redis) e expor o agente por uma API (FastAPI) para integrar com o WhatsApp.
- **Ampliar a avaliação** com perguntas de clientes reais, casos não vistos durante o desenvolvimento e conversas longas com um usuário simulado. Rodar a avaliação em CI a cada mudança de prompt.
- **Guardrail na saída**, checando antes do envio se a resposta não contém dados pessoais de outros clientes.

### Uso de assistentes de IA

Usei o **Claude** (claude.ai) como par de programação e revisor durante todo o projeto, e o **Claude Code** para editar arquivos (principalmente o Markdown das políticas). Meu fluxo foi:

- **Exploração dos dados:** discuti a estrutura dos CSVs e pedi ajuda para levantar inconsistências; várias das listadas acima saíram desse processo.
- **Revisão de código:** escrevi o schema, o `build_db.py` e as tools, e usei o Claude para revisar. Ele apontou, por exemplo, um erro de digitação numa FK, um `**args` que quebrava o schema da tool (e abriria brecha de SQL injection) e um espaço faltando antes do `ORDER BY`.
- **Decisões de arquitetura:** discuti alternativas (text-to-SQL × tools fixas, RAG × documento inteiro no prompt, montar JSON no SQL × em Python) e escolhi.
- **Avaliação:** o Claude escreveu a primeira versão do script de avaliação e parte dos casos de teste. Eu rodei, analisei os resultados e ajustei o agente e o próprio eval a partir deles.

As decisões e o código final são meus; a IA acelerou a revisão e me ajudou a enxergar problemas mais cedo.