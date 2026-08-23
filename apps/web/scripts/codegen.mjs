// Copy the client `ledger product` generated into the app.
//
// It is copied rather than imported across directories so the app has no
// build-time dependency on the pipeline's output layout, and so a checkout
// without a generated tree still typechecks against the last committed client.
import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, "..", "..", "..");
const out = join(repo, "bench", "out", "product", "client");
const dest = join(here, "..", "src", "generated");

const python = process.env.LEDGER_PYTHON || join(repo, ".venv", "bin", "python");
const ledger = process.env.LEDGER_SRC || resolve(repo, "..", "ledger");

if (existsSync(python) && existsSync(ledger)) {
  try {
    execFileSync(python, ["-m", "ledger", "-m", "project.yaml", "product"], {
      cwd: repo,
      env: { ...process.env, PYTHONPATH: ledger },
      stdio: "inherit",
    });
  } catch {
    console.warn("[codegen] ledger product failed; keeping the committed client");
  }
} else {
  console.warn("[codegen] ledger or the tenant venv is absent; keeping the committed client");
}

if (existsSync(out)) {
  mkdirSync(dest, { recursive: true });
  for (const f of readdirSync(out)) cpSync(join(out, f), join(dest, f));
  console.log(`[codegen] copied ${readdirSync(out).length} file(s) into src/generated`);
} else {
  console.warn("[codegen] no generated client at", out);
}
