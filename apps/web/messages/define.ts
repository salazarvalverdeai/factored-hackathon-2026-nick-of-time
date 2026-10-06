// One namespace of UI strings in the three languages side by side (spec 16 AC-06). English is the source of the keys;
// the type makes a missing or extra key in Spanish or Portuguese a compile error, and `lib/i18n.test.ts` checks it again.
// Placeholders are written `{name}` and filled by `t(key, { name })`. Customer-facing agent text never lives here.

export interface Dict {
  [key: string]: string | Dict;
}

export type Shape<T> = { [K in keyof T]: T[K] extends string ? string : Shape<T[K]> };

export function defineMessages<const T extends Dict>(m: { en: T; es: NoInfer<Shape<T>>; pt: NoInfer<Shape<T>> }) {
  return m;
}
