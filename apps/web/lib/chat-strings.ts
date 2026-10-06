// Every piece of /chat chrome text in one place (spec 07 AC-16 to AC-22), so the UI-language work can move it without
// hunting through components. Customer-facing words are ES/PT (the session language); the few operator controls of the
// demo stay in English. Nothing here carries a score, a zone or a policy id.
import type { Language } from "./types.ts";

type Bi<T = string> = Record<Language, T>;

export const CHAT_STRINGS = {
  assistant: { es: "Asistente de disputas", pt: "Assistente de disputas" } as Bi,
  online: { es: "En línea", pt: "Online" } as Bi,
  talkingWith: { es: (name: string) => `hablando con ${name}`, pt: (name: string) => `falando com ${name}` } as Bi<(name: string) => string>,
  newCase: { es: "Nuevo caso", pt: "Novo caso" } as Bi,
  newCaseHint: {
    es: "Empieza una conversación nueva. Tus casos abiertos se conservan.",
    pt: "Começa uma conversa nova. Seus casos abertos são mantidos.",
  } as Bi,
  demoNote: { es: "Demo con datos sintéticos", pt: "Demo com dados sintéticos" } as Bi,
  demoDate: { es: "fecha de la demo", pt: "data da demo" } as Bi,
  thinking: { es: "Pensando…", pt: "Pensando…" } as Bi,
  placeholder: {
    es: "Escribe o mantén presionado el micrófono para hablar",
    pt: "Escreva ou segure o microfone para falar",
  } as Bi,
  placeholderTyped: { es: "Escribe tu mensaje…", pt: "Escreva sua mensagem…" } as Bi,
  composerHint: {
    es: "Una persona del banco siempre está a un toque.",
    pt: "Uma pessoa do banco está sempre a um toque.",
  } as Bi,
  send: { es: "Enviar", pt: "Enviar" } as Bi,
  howDecided: { es: "Cómo lo decidí", pt: "Como decidi" } as Bi,
  steps: { es: (n: number) => (n === 1 ? "1 paso" : `${n} pasos`), pt: (n: number) => (n === 1 ? "1 etapa" : `${n} etapas`) } as Bi<(n: number) => string>,
  notCompleted: {
    es: (n: number) => (n === 1 ? "1 no se completó" : `${n} no se completaron`),
    pt: (n: number) => (n === 1 ? "1 não concluída" : `${n} não concluídas`),
  } as Bi<(n: number) => string>,
  working: { es: "Trabajando", pt: "Trabalhando" } as Bi,
  detail: { es: "detalle", pt: "detalhe" } as Bi,
  rule: { es: "ver regla", pt: "ver regra" } as Bi,
  technicalTrace: { es: "Ver traza técnica", pt: "Ver rastro técnico" } as Bi,
  hideTechnicalTrace: { es: "Ocultar traza técnica", pt: "Ocultar rastro técnico" } as Bi,
  confirmTitle: { es: "Antes de actuar necesito tu confirmación", pt: "Antes de agir preciso da sua confirmação" } as Bi,
  confirmYes: { es: "Sí, adelante", pt: "Sim, pode seguir" } as Bi,
  confirmNo: { es: "No, todavía no", pt: "Não, ainda não" } as Bi,
  copy: { es: "Copiar", pt: "Copiar" } as Bi,
  copied: { es: "Copiado", pt: "Copiado" } as Bi,
  copyReceipt: { es: "Copiar el comprobante", pt: "Copiar o comprovante" } as Bi,
  viewCase: { es: "Ver mi caso", pt: "Ver meu caso" } as Bi,
  source: { es: "Fuente", pt: "Fonte" } as Bi,
  sources: { es: "Fuentes", pt: "Fontes" } as Bi,
  verified: { es: "Verificado", pt: "Verificado" } as Bi,
  receipt: { es: "Comprobante", pt: "Comprovante" } as Bi,
  caseWord: { es: "caso", pt: "caso" } as Bi,
  then: { es: "luego, resolución a más tardar el", pt: "depois, resolução até" } as Bi,
  rowCharge: { es: "Cargo", pt: "Cobrança" } as Bi,
  rowDone: { es: "Hecho", pt: "Feito" } as Bi,
  rowNext: { es: "Sigue", pt: "Próximo" } as Bi,
  checkedOn: { es: "verificada el", pt: "verificada em" } as Bi,
  pick: { es: "Elegir", pt: "Escolher" } as Bi,
  citedFrom: { es: "Dato de la herramienta", pt: "Dado da ferramenta" } as Bi,
  openDetail: { es: "Ver detalle", pt: "Ver detalhe" } as Bi,
  close: { es: "Cerrar", pt: "Fechar" } as Bi,
  // The rule's detail panel (the mock's "Consultó la política del banco"): words only, never a score or a policy id.
  ruleTitle: { es: "Lo que dicen las reglas del banco", pt: "O que dizem as regras do banco" } as Bi,
  ruleLead: {
    es: "El asistente no decide: consulta las reglas del banco, y las reglas dicen qué puede hacer.",
    pt: "O assistente não decide: consulta as regras do banco, e as regras dizem o que ele pode fazer.",
  } as Bi,
  ruleResult: { es: "Resultado", pt: "Resultado" } as Bi,
  ruleAllowed: { es: "Acciones permitidas", pt: "Ações permitidas" } as Bi,
  ruleNote: {
    es: "En el chat no se muestran el puntaje del banco ni los códigos de las reglas. Una persona cierra cada caso.",
    pt: "No chat não aparecem a pontuação do banco nem os códigos das regras. Uma pessoa fecha cada caso.",
  } as Bi,
  stepStatus: { es: "Estado", pt: "Situação" } as Bi,
  stepResult: { es: "Resultado", pt: "Resultado" } as Bi,
  // Operator controls of the demo (English UI).
  signOut: "Sign out",
  expire: "Expire session (demo)",
} as const;
