#!/usr/bin/env node
/**
 * Compatibility shim for videowright 0.1.1.
 *
 * The published tarball ships `src/cli/entry/**` (its Vite entry) and `dist/**`,
 * but not the library sources those entries import. Both `videowright dev` and
 * `videowright render` boot Vite with `node_modules/videowright/src/cli/entry`
 * as the root, and the entries import the library by relative path —
 * `"../../index.js"`, `"../../../timeline/resolveTiming.js"` — which lands in
 * `videowright/src/`, a directory the package does not ship. Vite then fails to
 * resolve the import, the page never signals ready, and the CLI exits with
 * `page.waitForFunction: Timeout 30000ms exceeded` (render) or shows an error
 * overlay (dev).
 *
 * This writes the missing files as re-exports of the built library so the
 * relative imports resolve. It is idempotent, never overwrites an existing
 * file, and exits quietly when a future version ships the real modules or when
 * `node_modules` is absent.
 */
import { existsSync, mkdirSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const packageDir = resolve(scriptDir, "../node_modules/videowright");
const srcDir = join(packageDir, "src");
const distDir = join(packageDir, "dist");

if (!existsSync(distDir) || !existsSync(join(packageDir, "src/cli/entry"))) {
  process.exit(0);
}

/** Every `.js` file under a directory, as paths relative to it. */
function walk(dir, base = dir) {
  return readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) return walk(full, base);
    return entry.endsWith(".js") ? [relative(base, full)] : [];
  });
}

let written = 0;
for (const relativeModule of walk(distDir)) {
  // Only the library modules outside `cli/` are needed; `cli/entry` is shipped.
  if (relativeModule.startsWith("cli/")) continue;
  const target = join(srcDir, relativeModule);
  if (existsSync(target)) continue;
  mkdirSync(dirname(target), { recursive: true });
  const depth = relative(srcDir, dirname(target))
    .split(/[\\/]/)
    .filter(Boolean).length;
  const up = "../".repeat(depth + 1);
  writeFileSync(target, `export * from "${up}dist/${relativeModule}";\n`);
  written += 1;
}

if (written > 0) {
  console.log(`videowright shim: wrote ${written} re-export module(s) into node_modules.`);
}
