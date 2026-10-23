// Copy the built SPA (frontend/dist) into the backend package so FastAPI can serve it.
import { cpSync, existsSync, mkdirSync, rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = resolve(here, "..", "dist");
const target = resolve(here, "..", "..", "backend", "src", "circuits_llm", "web", "static");

if (!existsSync(resolve(dist, "index.html"))) {
  console.error(`No build found at ${dist}; run "npm run build" first.`);
  process.exit(1);
}

rmSync(target, { recursive: true, force: true });
mkdirSync(target, { recursive: true });
cpSync(dist, target, { recursive: true });
console.log(`Copied ${dist} -> ${target}`);
