// Render-only build guard; the existing local npm scripts are unchanged.
import { spawnSync } from "node:child_process";

const value = process.env.VITE_API_URL;
if (!value)
  throw new Error("Set VITE_API_URL to the actual public HTTPS API origin");
const url = new URL(value);
if (
  url.protocol !== "https:" ||
  url.hostname.includes("*") ||
  url.username ||
  url.password ||
  url.search ||
  url.hash ||
  !["", "/"].includes(url.pathname)
)
  throw new Error("VITE_API_URL must be an HTTPS origin without a path");
if (!process.argv.includes("--check")) {
  for (const args of [
    ["ci", "--prefix", "dashboard"],
    ["--prefix", "dashboard", "run", "build"],
  ]) {
    const result = spawnSync("npm", args, {
      stdio: "inherit",
      shell: process.platform === "win32",
    });
    if (result.error || result.status !== 0)
      throw new Error("Frontend build failed");
  }
}
