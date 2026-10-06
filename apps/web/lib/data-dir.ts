// Server only (node modules): not imported by client components.
import { realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import { resolve, sep } from "node:path";

/**
 * Where the page reads its result files. `override` (EVALUATION_DATA_DIR, local checks only) is resolved and refused
 * unless it is inside the repository or the system temp directory; anything else falls back to the default.
 */
export function dataDir(override: string | undefined, cwd = process.cwd(), tmp = tmpdir()): string {
  const fallback = resolve(cwd, "public", "data");
  if (!override) return fallback;
  const target = resolve(override);
  const roots = [resolve(cwd, "..", ".."), realpathSync(tmp), tmp].map((r) => resolve(r));
  return roots.some((r) => target === r || target.startsWith(r + sep)) ? target : fallback;
}
