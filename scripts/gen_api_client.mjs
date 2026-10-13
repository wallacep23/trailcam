#!/usr/bin/env node
// Regenerate the typed API client: backend OpenAPI -> apps/web/openapi.json -> src/api/schema.d.ts.
//
//   pnpm --dir apps/web gen:api          # write both files
//   pnpm --dir apps/web check:api        # exit 1 if either is stale (used by CI)
//
// The Python step runs `uv run --project backend python scripts/export_openapi.py`; set
// TRAILCAM_PYTHON (e.g. "python") to use another interpreter that has the backend installed.
import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const web = join(root, "apps", "web");
const check = process.argv.includes("--check");
const outDir = check ? mkdtempSync(join(tmpdir(), "trailcam-api-")) : null;
const specPath = check ? join(outDir, "openapi.json") : join(web, "openapi.json");
const typesPath = check ? join(outDir, "schema.d.ts") : join(web, "src", "api", "schema.d.ts");

function run(cmd, args, cwd) {
  const res = spawnSync(cmd, args, { cwd, stdio: "inherit" });
  if (res.status !== 0) {
    console.error(`\n✖ ${cmd} ${args.join(" ")} failed`);
    process.exit(res.status ?? 1);
  }
}

const exporter = join(root, "scripts", "export_openapi.py");
const python = process.env.TRAILCAM_PYTHON;
if (python) run(python, [exporter, specPath], root);
else run("uv", ["run", "--project", "backend", "python", exporter, specPath], root);

// Run the CLI through node directly (no shell, works the same on Windows and Linux).
const cli = join(web, "node_modules", "openapi-typescript", "bin", "cli.js");
// Request fields that have server defaults stay optional (FastAPI marks response fields required).
run(process.execPath, [cli, specPath, "-o", typesPath, "--default-non-nullable=false"], web);

if (check) {
  const stale = [
    [specPath, join(web, "openapi.json")],
    [typesPath, join(web, "src", "api", "schema.d.ts")],
  ].filter(([fresh, committed]) => {
    try {
      return readFileSync(fresh, "utf8").replace(/\r\n/g, "\n") !== readFileSync(committed, "utf8").replace(/\r\n/g, "\n");
    } catch {
      return true;
    }
  });
  rmSync(outDir, { recursive: true, force: true });
  if (stale.length) {
    console.error(`\n✖ Generated API client is stale: ${stale.map(([, c]) => c).join(", ")}`);
    console.error("  Run `pnpm --dir apps/web gen:api` and commit the result.");
    process.exit(1);
  }
  console.log("✔ API client is up to date");
}
