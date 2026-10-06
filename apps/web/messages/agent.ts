// UI strings for /agent (spec 16 AC-06, spec 04 AC-08). Code identifiers, node keys, tool names, policy ids and model ids
// stay as written; the generated rows of lib/agent-reference.ts are not translated.
import { defineMessages } from "./define.ts";

export const agent = defineMessages({
  en: {
    meta: { title: "Agent" },
    title: "Agent",
    description: "How a dispute turn runs: the graph, the policy that decides, the tools that act and the models.",
    constitution: "The LLM understands, the rules decide, the tools act, verification confirms, a person closes.",
    constitutionNote:
      "The constitution of the system. Every table on this page is generated from the repository's code and contracts by {script}, and the web tests fail when it drifts from them.",
    onThisPage: "On this page",
    nav: {
      architecture: "Architecture",
      graph: "Graph",
      policies: "Policies",
      tools: "Tools",
      guardrails: "Guardrails",
      models: "Models",
    },
    common: { yes: "yes", noZoneHuman: "no, zone human", fullRule: "Full rule" },
    architecture: {
      title: "Architecture",
      note: "Agent on LangGraph Platform, customer tools as an MCP server, case state in Postgres. Diagram from {source}, as shown in the README; where it and the tables below differ, the tables are current.",
      open: "Open the architecture diagram at full size",
      alt: "Architecture: customer and analyst web pages, the FastAPI api, the FastMCP tool server, Postgres and gold data on one EC2; the dispute_intake graph on LangGraph Platform calling Amazon Bedrock and the MCP tools.",
    },
    graph: {
      title: "Graph {name}",
      note: "{count} nodes; the run starts at {start} and ends after {end}. A branch follows the policy engine's result or a tool read, never the LLM's text. Source: {source}.",
      label: "Graph nodes",
      head: { node: "Node", does: "What it does", next: "Next" },
      oneOf: "one of ",
    },
    nodes: {
      identity: "Reads the session, mode and arm from the run config the api injects; never from the customer's text.",
      greet: "First turn of a verified session: greets with the first name returned by get_customer_profile.",
      understand:
        "Language, injection flag, intent and slots with the B0 rules; below τ, arms S1/S2 ask the LLM, only in a verified session.",
      route: "Spec 02 rules 1–4 through the policy engine's screen(); the engine, not the graph, picks the branch.",
      refuse: "Deny or re-authenticate with no data and a way forward; the denial is recorded in policy_denials.",
      connect: "Registers a call request where the policy says, on the active case or a general one; never refused.",
      retrieve:
        "Finds the customer's transaction with search_transaction; for exactly one, reads its card, score, amount and any active case.",
      decide: "Runs the policy engine's decide() on tool facts only; the graph follows its result, never a rule of its own.",
      plan: "States the numbered steps before acting; in the confirm state it asks before anything is done.",
      act: "Runs only the writes decide() allowed: open_case first, then block_card when allowed, each with an idempotency key.",
      verify:
        "Reads each write's post-condition with its verifying tool: verified only with a V- id, otherwise not confirmed and escalated.",
      duplicate: "The charge already has an active case: nothing is opened; the case and its stored deadlines come from get_case.",
      clarify: "One question, nothing done: up to the allowed number of option cards, or a request for the details.",
      status: "Re-reads cards or cases in this turn and answers with tool facts and the time of the reading.",
      respond:
        "Builds the reply, the receipt and the handoff card from templates and tool results; the grounding gate drops any fact no tool returned.",
    },
    policies: {
      title: "Policies",
      note: "{source} version {version}, {default}. Every decision cites one of these {count} ids; the LLM never reads or edits the file.",
      zonesTitle: "Zones from the bank's fraud score",
      score: "score {range}",
      orNoScore: "{range} or no score",
      idsTitle: "Policy ids",
      head: { id: "Policy id", decides: "What it decides", guardrail: "Guardrail" },
    },
    tools: {
      title: "Customer tools",
      note: "The {count} tools of the FastMCP server, the only way the agent reaches data. Each takes the session, never a customer id, and a write is reported as verified only after its read. Sources: {tools} and {purposes} §6.3.",
      head: { tool: "Tool", kind: "Kind", purpose: "Purpose", verified: "Verified with" },
      kind: { R: "Read", W: "Write", N: "Notification" },
    },
    guardrails: {
      title: "Guardrails",
      note: "{count} guardrails, each in code with a case in the evaluation set; every deny cites its id. Source: {source} {key}.",
      head: { id: "Id", layer: "Layer", guardrail: "Guardrail", how: "How", cited: "Cited by" },
    },
    models: {
      title: "Models and decision engines",
      note: "Everything that decides, scores or advises (ADR 0021). A run with no arm is S0, with no LLM call; the S1 and S2 ids are the defaults in {source}.",
      label: "Model inventory",
      head: { engine: "Engine", kind: "Kind", version: "Version", role: "Role", source: "Source" },
      providersTitle: "Score providers",
      providersNote:
        "The active provider is {provider}. A score from a source that cannot place a zone sends the case to a person.",
      providersHead: { provider: "Provider", version: "Version", canPlace: "Can place a zone", note: "Note" },
    },
    inventory: {
      policy: {
        engine: "Policy engine",
        kind: "Rules",
        role: "Decides every action, default {default}; the LLM never reads or edits it.",
      },
      clock: {
        engine: "Regulatory clock",
        kind: "Rules (data table)",
        role: "The legal deadline per country and product, each entry with source_url and verified_on; no entry → POL-CLOCK-UNKNOWN.",
      },
      fraud: {
        engine: "Fraud score",
        kind: "Bank's score (vendor)",
        role: "Places the case in a zone; only the deciding sources below can.",
      },
      b0: {
        engine: "Intent classifier and injection rules (B0)",
        kind: "Rules",
        role: "Language, intent, slots and the injection flag in the understand node; the graph loads arm {arm}.",
      },
      b1: {
        engine: "Intent classifier (B1)",
        kind: "TF-IDF + logistic regression",
        role: "Learned arm measured by the spec 11 protocol; not loaded by the graph.",
      },
      s1: {
        engine: "LLM arm S1",
        kind: "LLM · Amazon Bedrock",
        role: "Intent and slots below τ in a verified session when the run's arm is S1; also the demo persona's opening message.",
      },
      s2: {
        engine: "LLM arm S2",
        kind: "LLM · Amazon Bedrock",
        role: "The same step on the quality-ceiling model when the run's arm is S2.",
      },
      judge: {
        engine: "Judge",
        kind: "LLM · advisory",
        version: "Claude Haiku 4.5 until the spec 15 benchmark picks the judge's model",
        role: "A second opinion for the analyst on cases in review, every reason tied to evidence; never decides or changes state.",
      },
      auditor: {
        engine: "Outcome auditor",
        kind: "Deterministic checks",
        role: "Re-derives each run's decision, deadline, verified actions and facts from its records; findings go to audit_findings.",
      },
    },
  },
  es: {
    meta: { title: "Agente" },
    title: "Agente",
    description: "Cómo corre un turno de disputa: el grafo, la política que decide, las herramientas que actúan y los modelos.",
    constitution: "El LLM entiende, las reglas deciden, las herramientas actúan, la verificación confirma, una persona cierra.",
    constitutionNote:
      "La constitución del sistema. Cada tabla de esta página se genera a partir del código y los contratos del repositorio con {script}, y las pruebas web fallan cuando se desvía de ellos.",
    onThisPage: "En esta página",
    nav: {
      architecture: "Arquitectura",
      graph: "Grafo",
      policies: "Políticas",
      tools: "Herramientas",
      guardrails: "Salvaguardas",
      models: "Modelos",
    },
    common: { yes: "sí", noZoneHuman: "no, zona humana", fullRule: "Regla completa" },
    architecture: {
      title: "Arquitectura",
      note: "Agente en LangGraph Platform, herramientas del cliente como servidor MCP, estado de los casos en Postgres. Diagrama de {source}, como aparece en el README; donde difiera de las tablas de abajo, las tablas son las vigentes.",
      open: "Abrir el diagrama de arquitectura en tamaño completo",
      alt: "Arquitectura: páginas web del cliente y del analista, la api FastAPI, el servidor de herramientas FastMCP, Postgres y los datos gold en una EC2; el grafo dispute_intake en LangGraph Platform, que llama a Amazon Bedrock y a las herramientas MCP.",
    },
    graph: {
      title: "Grafo {name}",
      note: "{count} nodos; la ejecución empieza en {start} y termina después de {end}. Una rama sigue el resultado del motor de políticas o una lectura de herramienta, nunca el texto del LLM. Fuente: {source}.",
      label: "Nodos del grafo",
      head: { node: "Nodo", does: "Qué hace", next: "Siguiente" },
      oneOf: "uno de ",
    },
    nodes: {
      identity: "Lee la sesión, el modo y el brazo de la configuración de ejecución que inyecta la api; nunca del texto del cliente.",
      greet: "Primer turno de una sesión verificada: saluda con el nombre que devuelve get_customer_profile.",
      understand:
        "Idioma, marca de inyección, intención y campos con las reglas B0; por debajo de τ, los brazos S1/S2 consultan al LLM, solo en una sesión verificada.",
      route: "Reglas 1–4 de la spec 02 mediante screen() del motor de políticas; el motor, no el grafo, elige la rama.",
      refuse: "Niega o pide reautenticar, sin datos y con un camino a seguir; la negación se registra en policy_denials.",
      connect: "Registra una solicitud de llamada donde lo indica la política, en el caso activo o en uno general; nunca se rechaza.",
      retrieve:
        "Encuentra la transacción del cliente con search_transaction; si hay exactamente una, lee su tarjeta, puntaje, monto y cualquier caso activo.",
      decide: "Ejecuta decide() del motor de políticas solo sobre hechos de herramientas; el grafo sigue su resultado, nunca una regla propia.",
      plan: "Enuncia los pasos numerados antes de actuar; en el estado de confirmación pregunta antes de hacer cualquier cosa.",
      act: "Ejecuta solo las escrituras que decide() permitió: primero open_case, luego block_card cuando se permite, cada una con una clave de idempotencia.",
      verify:
        "Lee la poscondición de cada escritura con su herramienta de verificación: verificada solo con un id V-; si no, no confirmada y escalada.",
      duplicate: "El cargo ya tiene un caso activo: no se abre nada; el caso y sus plazos guardados vienen de get_case.",
      clarify: "Una pregunta, nada hecho: hasta el número permitido de tarjetas de opciones, o una solicitud de los detalles.",
      status: "Vuelve a leer tarjetas o casos en este turno y responde con hechos de herramientas y la hora de la lectura.",
      respond:
        "Arma la respuesta, el comprobante y la tarjeta de traspaso a partir de plantillas y resultados de herramientas; el filtro de fundamentación descarta cualquier hecho que ninguna herramienta devolvió.",
    },
    policies: {
      title: "Políticas",
      note: "{source} versión {version}, {default}. Cada decisión cita uno de estos {count} ids; el LLM nunca lee ni edita el archivo.",
      zonesTitle: "Zonas según el puntaje de fraude del banco",
      score: "puntaje {range}",
      orNoScore: "{range} o sin puntaje",
      idsTitle: "Ids de política",
      head: { id: "Id de política", decides: "Qué decide", guardrail: "Salvaguarda" },
    },
    tools: {
      title: "Herramientas del cliente",
      note: "Las {count} herramientas del servidor FastMCP, la única vía del agente a los datos. Cada una recibe la sesión, nunca un id de cliente, y una escritura se reporta como verificada solo después de su lectura. Fuentes: {tools} y {purposes} §6.3.",
      head: { tool: "Herramienta", kind: "Tipo", purpose: "Propósito", verified: "Verificada con" },
      kind: { R: "Lectura", W: "Escritura", N: "Notificación" },
    },
    guardrails: {
      title: "Salvaguardas",
      note: "{count} salvaguardas, cada una en código y con un caso en el conjunto de evaluación; cada negación cita su id. Fuente: {source} {key}.",
      head: { id: "Id", layer: "Capa", guardrail: "Salvaguarda", how: "Cómo", cited: "Citada por" },
    },
    models: {
      title: "Modelos y motores de decisión",
      note: "Todo lo que decide, puntúa o aconseja (ADR 0021). Una ejecución sin brazo es S0, sin llamada al LLM; los ids de S1 y S2 son los predeterminados en {source}.",
      label: "Inventario de modelos",
      head: { engine: "Motor", kind: "Tipo", version: "Versión", role: "Rol", source: "Fuente" },
      providersTitle: "Proveedores de puntaje",
      providersNote:
        "El proveedor activo es {provider}. Un puntaje de una fuente que no puede asignar una zona envía el caso a una persona.",
      providersHead: { provider: "Proveedor", version: "Versión", canPlace: "Puede asignar una zona", note: "Nota" },
    },
    inventory: {
      policy: {
        engine: "Motor de políticas",
        kind: "Reglas",
        role: "Decide cada acción, por defecto {default}; el LLM nunca lo lee ni lo edita.",
      },
      clock: {
        engine: "Reloj regulatorio",
        kind: "Reglas (tabla de datos)",
        role: "El plazo legal por país y producto, cada entrada con source_url y verified_on; sin entrada → POL-CLOCK-UNKNOWN.",
      },
      fraud: {
        engine: "Puntaje de fraude",
        kind: "Puntaje del banco (proveedor)",
        role: "Ubica el caso en una zona; solo pueden hacerlo las fuentes decisoras de abajo.",
      },
      b0: {
        engine: "Clasificador de intención y reglas de inyección (B0)",
        kind: "Reglas",
        role: "Idioma, intención, campos y marca de inyección en el nodo understand; el grafo carga el brazo {arm}.",
      },
      b1: {
        engine: "Clasificador de intención (B1)",
        kind: "TF-IDF + regresión logística",
        role: "Brazo aprendido, medido con el protocolo de la spec 11; el grafo no lo carga.",
      },
      s1: {
        engine: "Brazo LLM S1",
        kind: "LLM · Amazon Bedrock",
        role: "Intención y campos por debajo de τ en una sesión verificada cuando el brazo de la ejecución es S1; también el mensaje inicial de la persona demo.",
      },
      s2: {
        engine: "Brazo LLM S2",
        kind: "LLM · Amazon Bedrock",
        role: "El mismo paso con el modelo de techo de calidad cuando el brazo de la ejecución es S2.",
      },
      judge: {
        engine: "Juez",
        kind: "LLM · consultivo",
        version: "Claude Haiku 4.5 hasta que el benchmark de la spec 15 elija el modelo del juez",
        role: "Una segunda opinión para el analista en casos en revisión, cada razón ligada a evidencia; nunca decide ni cambia el estado.",
      },
      auditor: {
        engine: "Auditor de resultados",
        kind: "Verificaciones deterministas",
        role: "Vuelve a derivar la decisión, el plazo, las acciones verificadas y los hechos de cada ejecución a partir de sus registros; los hallazgos van a audit_findings.",
      },
    },
  },
  pt: {
    meta: { title: "Agente" },
    title: "Agente",
    description: "Como corre um turno de contestação: o grafo, a política que decide, as ferramentas que agem e os modelos.",
    constitution: "O LLM entende, as regras decidem, as ferramentas agem, a verificação confirma, uma pessoa fecha.",
    constitutionNote:
      "A constituição do sistema. Cada tabela desta página é gerada a partir do código e dos contratos do repositório por {script}, e os testes web falham quando ela diverge deles.",
    onThisPage: "Nesta página",
    nav: {
      architecture: "Arquitetura",
      graph: "Grafo",
      policies: "Políticas",
      tools: "Ferramentas",
      guardrails: "Salvaguardas",
      models: "Modelos",
    },
    common: { yes: "sim", noZoneHuman: "não, zona humana", fullRule: "Regra completa" },
    architecture: {
      title: "Arquitetura",
      note: "Agente no LangGraph Platform, ferramentas do cliente como servidor MCP, estado dos casos no Postgres. Diagrama de {source}, como aparece no README; onde ele e as tabelas abaixo diferirem, valem as tabelas.",
      open: "Abrir o diagrama de arquitetura em tamanho real",
      alt: "Arquitetura: páginas web do cliente e do analista, a api FastAPI, o servidor de ferramentas FastMCP, Postgres e os dados gold em uma EC2; o grafo dispute_intake no LangGraph Platform, que chama o Amazon Bedrock e as ferramentas MCP.",
    },
    graph: {
      title: "Grafo {name}",
      note: "{count} nós; a execução começa em {start} e termina depois de {end}. Um desvio segue o resultado do motor de políticas ou uma leitura de ferramenta, nunca o texto do LLM. Fonte: {source}.",
      label: "Nós do grafo",
      head: { node: "Nó", does: "O que faz", next: "Próximo" },
      oneOf: "um de ",
    },
    nodes: {
      identity: "Lê a sessão, o modo e o braço da configuração de execução que a api injeta; nunca do texto do cliente.",
      greet: "Primeiro turno de uma sessão verificada: cumprimenta com o primeiro nome que get_customer_profile retorna.",
      understand:
        "Idioma, sinal de injeção, intenção e campos com as regras B0; abaixo de τ, os braços S1/S2 consultam o LLM, só em sessão verificada.",
      route: "Regras 1–4 da spec 02 pelo screen() do motor de políticas; o motor, não o grafo, escolhe o desvio.",
      refuse: "Nega ou pede nova autenticação, sem dados e com um caminho a seguir; a negação é registrada em policy_denials.",
      connect: "Registra um pedido de ligação onde a política indica, no caso ativo ou em um geral; nunca é recusado.",
      retrieve:
        "Encontra a transação do cliente com search_transaction; se houver exatamente uma, lê o cartão, o score, o valor e qualquer caso ativo.",
      decide: "Executa o decide() do motor de políticas só sobre fatos de ferramentas; o grafo segue o resultado, nunca uma regra própria.",
      plan: "Enuncia os passos numerados antes de agir; no estado de confirmação, pergunta antes de fazer qualquer coisa.",
      act: "Executa só as escritas que o decide() permitiu: primeiro open_case, depois block_card quando permitido, cada uma com uma chave de idempotência.",
      verify:
        "Lê a pós-condição de cada escrita com a ferramenta que a verifica: verificada só com um id V-; caso contrário, não confirmada e escalada.",
      duplicate: "A cobrança já tem um caso ativo: nada é aberto; o caso e seus prazos salvos vêm de get_case.",
      clarify: "Uma pergunta, nada feito: até o número permitido de cartões de opção, ou um pedido dos detalhes.",
      status: "Relê cartões ou casos neste turno e responde com fatos de ferramentas e a hora da leitura.",
      respond:
        "Monta a resposta, o comprovante e o cartão de repasse a partir de modelos e resultados de ferramentas; o filtro de fundamentação descarta qualquer fato que nenhuma ferramenta retornou.",
    },
    policies: {
      title: "Políticas",
      note: "{source} versão {version}, {default}. Cada decisão cita um destes {count} ids; o LLM nunca lê nem edita o arquivo.",
      zonesTitle: "Zonas pelo score de fraude do banco",
      score: "score {range}",
      orNoScore: "{range} ou sem score",
      idsTitle: "Ids de política",
      head: { id: "Id de política", decides: "O que decide", guardrail: "Salvaguarda" },
    },
    tools: {
      title: "Ferramentas do cliente",
      note: "As {count} ferramentas do servidor FastMCP, o único caminho do agente até os dados. Cada uma recebe a sessão, nunca um id de cliente, e uma escrita é informada como verificada só depois da sua leitura. Fontes: {tools} e {purposes} §6.3.",
      head: { tool: "Ferramenta", kind: "Tipo", purpose: "Finalidade", verified: "Verificada com" },
      kind: { R: "Leitura", W: "Escrita", N: "Notificação" },
    },
    guardrails: {
      title: "Salvaguardas",
      note: "{count} salvaguardas, cada uma em código e com um caso no conjunto de avaliação; cada negação cita seu id. Fonte: {source} {key}.",
      head: { id: "Id", layer: "Camada", guardrail: "Salvaguarda", how: "Como", cited: "Citada por" },
    },
    models: {
      title: "Modelos e motores de decisão",
      note: "Tudo o que decide, pontua ou aconselha (ADR 0021). Uma execução sem braço é S0, sem chamada ao LLM; os ids de S1 e S2 são os padrões em {source}.",
      label: "Inventário de modelos",
      head: { engine: "Motor", kind: "Tipo", version: "Versão", role: "Papel", source: "Fonte" },
      providersTitle: "Provedores de score",
      providersNote:
        "O provedor ativo é {provider}. Um score de uma fonte que não pode definir uma zona envia o caso para uma pessoa.",
      providersHead: { provider: "Provedor", version: "Versão", canPlace: "Pode definir uma zona", note: "Nota" },
    },
    inventory: {
      policy: {
        engine: "Motor de políticas",
        kind: "Regras",
        role: "Decide cada ação, padrão {default}; o LLM nunca o lê nem o edita.",
      },
      clock: {
        engine: "Relógio regulatório",
        kind: "Regras (tabela de dados)",
        role: "O prazo legal por país e produto, cada entrada com source_url e verified_on; sem entrada → POL-CLOCK-UNKNOWN.",
      },
      fraud: {
        engine: "Score de fraude",
        kind: "Score do banco (fornecedor)",
        role: "Coloca o caso em uma zona; só as fontes decisoras abaixo podem.",
      },
      b0: {
        engine: "Classificador de intenção e regras de injeção (B0)",
        kind: "Regras",
        role: "Idioma, intenção, campos e sinal de injeção no nó understand; o grafo carrega o braço {arm}.",
      },
      b1: {
        engine: "Classificador de intenção (B1)",
        kind: "TF-IDF + regressão logística",
        role: "Braço aprendido, medido pelo protocolo da spec 11; o grafo não o carrega.",
      },
      s1: {
        engine: "Braço LLM S1",
        kind: "LLM · Amazon Bedrock",
        role: "Intenção e campos abaixo de τ em sessão verificada quando o braço da execução é S1; também a mensagem inicial da persona de demonstração.",
      },
      s2: {
        engine: "Braço LLM S2",
        kind: "LLM · Amazon Bedrock",
        role: "O mesmo passo com o modelo de teto de qualidade quando o braço da execução é S2.",
      },
      judge: {
        engine: "Juiz",
        kind: "LLM · consultivo",
        version: "Claude Haiku 4.5 até o benchmark da spec 15 escolher o modelo do juiz",
        role: "Uma segunda opinião para o analista em casos em revisão, cada motivo ligado a evidências; nunca decide nem muda o estado.",
      },
      auditor: {
        engine: "Auditor de resultados",
        kind: "Verificações determinísticas",
        role: "Refaz a decisão, o prazo, as ações verificadas e os fatos de cada execução a partir dos registros; os achados vão para audit_findings.",
      },
    },
  },
});
