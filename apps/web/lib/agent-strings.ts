// UI strings of the /agent drawings (components/agent/*), in one module and shaped like a messages dictionary so they
// can move to the i18n dictionaries (spec 16 AC-06) as they are. Placeholders are written `{name}` and filled by `fill`.

export const AGENT_UI = {
  graph: {
    title: "Graph {name}: {nodes} nodes and {edges} edges from START to END. Each node can be focused to read what it does.",
    scrollHint: "Scroll sideways to see the whole graph; the table below lists the same nodes.",
    legendLabel: "Edge colors",
    branchOn: "Branch on a {kind}",
    alwaysNext: "Always next",
    replay: "Replay",
    replayLabel: "Replay the graph drawing in order, from START to END",
    panelLabel: "Selected node",
    panelHint: "Hover a node, or Tab to one, to see what it does and what decides each way out. Esc clears.",
    goesTo: "Goes to",
    when: "when",
    always: "always",
    comesFrom: "Comes from",
    current: "Current node",
    onPath: "On this run's path",
  },
  arch: {
    title: "Services architecture: {services} services and {flows} request paths, from the browser to the data and the models.",
    legendLabel: "Path kinds",
    kinds: {
      request: "Request (HTTPS)",
      agent: "Agent run and tools",
      llm: "LLM call",
      data: "Data",
      deploy: "Delivery (CI/CD)",
    },
    play: "Walk through",
    pause: "Pause",
    previous: "Previous step",
    next: "Next step",
    step: "Step {n} of {total}",
    overview: "Overview",
    panelLabel: "Selected service or step",
    panelHint: "Walk through the request paths, or hover or Tab to a service to read its role. Esc clears.",
    sends: "Sends",
    receives: "Receives",
    stepsTitle: "Request paths, in order",
    staticView: "Static view (SVG)",
    staticNote: "· the original drawing, which also shows the notifications and the S3 bucket.",
  },
} as const;

/** Fills `{name}` placeholders. */
export function fill(text: string, values: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in values ? String(values[k]) : m));
}
