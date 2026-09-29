# Diferenciales frente a otros equipos (para el README final y el video)

Con ~180 equipos y 10 días, la mayoría convergerá en un chat con RAG sobre políticas inventadas, casi siempre W1, con el LLM decidiendo, métricas de contención sobre una demo y sin held-out. Lo que nos separa, cada uno atado a un criterio del reto y con una prueba que se muestra:

| Diferencial | Criterio del reto | Cómo se demuestra |
| --- | --- | --- |
| Verificación visible: aceptado ≠ verificado; tool caída → acción no confirmada | Punto 2 | Caso `tool_failure` en el video |
| Política fuera del modelo, con cada DENY como fila y guardrails con ID | Puntos 3 y 5 | La inyección engaña al texto y no a la regla |
| Modo de aprobación configurable y cierre siempre humano | "AI should not be autonomous just because it can" | Interruptor supervisado en la consola |
| Evaluación por estado final, pass^4, n por celda, ES/PT y ataques, sobre held-out sellado | Puntos 4 y 5 | Tabla con fallas incluidas |
| Bloqueos del agente medidos contra `is_fraud` real del dataset | Unsafe outcomes | Métrica que no escribimos nosotros |
| Los 15 números reproducibles con `make setup` en 60 s y corregidos en público | Punto 1, Data Analytics | Índice número → query → CSV en `docs/eda/README.md` |
| Reloj regulatorio por país con fuente | Business reasoning | Día hábil 2 visible en el caso |
| Dos actores con tools separadas y notificación al cliente en cada estado | Escalation quality | Consola + panel del cliente |
| Etiquetas dato / externo / supuesto / simulado / proyectado en todo | Honestidad que pide el kickoff | Cada número del pitch y del README |

Dónde podríamos perder: si el caso end-to-end no corre el miércoles 30; si el clasificador ES/PT queda flojo y el componente aprendido parece decorado (el baseline de reglas va antes que el modelo); y si la demo se ve pobre frente a interfaces bonitas (`/chat` parte de `agent-chat-ui`).
