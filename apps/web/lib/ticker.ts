// Pure helpers of the number ticker, kept apart so `npm test` can check them without a DOM.

export function formatTicker(n: number, decimalPlaces: number): string {
  return Intl.NumberFormat("en-US", {
    minimumFractionDigits: decimalPlaces,
    maximumFractionDigits: decimalPlaces,
  }).format(Number(n.toFixed(decimalPlaces)));
}

/** Where the subtle count starts: close to the value, so a frame caught mid-animation is never a misleading 0. */
export function tickerStart(value: number, startValue?: number): number {
  return startValue ?? value * 0.9;
}
