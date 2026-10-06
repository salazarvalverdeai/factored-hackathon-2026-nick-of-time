// Site header, footer, language selector and strings shared across pages.
import { defineMessages } from "./define.ts";

export const shell = defineMessages({
  en: {
    nav: {
      label: "Main",
      chat: "Chat",
      console: "Console",
      data: "Data",
      evaluation: "Evaluation",
      analytics: "Analytics",
      agent: "Agent",
      menu: "Menu",
      openMenu: "Open the menu",
      closeMenu: "Close the menu",
    },
    home: "Nick of Time, home",
    theme: "Toggle theme",
    language: {
      label: "Language",
      current: "Language: {name}",
      switchTo: "Switch the interface to {name}",
    },
    footer: {
      figureLabels: "Figure labels:",
      whatTheyMean: "what they mean",
    },
    common: {
      loading: "Loading…",
      none: "—",
      close: "Close",
      back: "Back",
      retry: "Try again",
      detail: "Detail",
    },
  },
  es: {
    nav: {
      label: "Principal",
      chat: "Chat",
      console: "Consola",
      data: "Datos",
      evaluation: "Evaluación",
      analytics: "Analítica",
      agent: "Agente",
      menu: "Menú",
      openMenu: "Abrir el menú",
      closeMenu: "Cerrar el menú",
    },
    home: "Nick of Time, inicio",
    theme: "Cambiar el tema",
    language: {
      label: "Idioma",
      current: "Idioma: {name}",
      switchTo: "Cambiar la interfaz a {name}",
    },
    footer: {
      figureLabels: "Etiquetas de cifras:",
      whatTheyMean: "qué significan",
    },
    common: {
      loading: "Cargando…",
      none: "—",
      close: "Cerrar",
      back: "Volver",
      retry: "Reintentar",
      detail: "Detalle",
    },
  },
  pt: {
    nav: {
      label: "Principal",
      chat: "Chat",
      console: "Console",
      data: "Dados",
      evaluation: "Avaliação",
      analytics: "Analytics",
      agent: "Agente",
      menu: "Menu",
      openMenu: "Abrir o menu",
      closeMenu: "Fechar o menu",
    },
    home: "Nick of Time, início",
    theme: "Alternar o tema",
    language: {
      label: "Idioma",
      current: "Idioma: {name}",
      switchTo: "Mudar a interface para {name}",
    },
    footer: {
      figureLabels: "Rótulos dos números:",
      whatTheyMean: "o que significam",
    },
    common: {
      loading: "Carregando…",
      none: "—",
      close: "Fechar",
      back: "Voltar",
      retry: "Tentar de novo",
      detail: "Detalhe",
    },
  },
});
