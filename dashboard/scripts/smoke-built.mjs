// Execute the production bundle against real loopback API responses in jsdom.
// This checks browser-facing code paths, not pixels or a real browser engine.
import { JSDOM } from "jsdom";
import { readdir } from "node:fs/promises";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { performance } from "node:perf_hooks";

const started = performance.now();
const base = new URL(process.argv[2]);
if (base.protocol !== "http:" || base.hostname !== "127.0.0.1")
  throw new Error("Loopback preview URL required");
const html = await (await fetch(base)).text();
const dom = new JSDOM(html, { url: base.href, pretendToBeVisual: true });
for (const name of [
  "window",
  "document",
  "navigator",
  "HTMLElement",
  "Element",
  "Node",
  "MutationObserver",
  "getComputedStyle",
]) {
  Object.defineProperty(globalThis, name, {
    configurable: true,
    value:
      name === "getComputedStyle"
        ? dom.window[name].bind(dom.window)
        : dom.window[name],
  });
}
globalThis.requestAnimationFrame = dom.window.requestAnimationFrame.bind(
  dom.window,
);
globalThis.cancelAnimationFrame = dom.window.cancelAnimationFrame.bind(
  dom.window,
);
globalThis.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
};
const nativeFetch = globalThis.fetch;
const requests = [];
globalThis.fetch = async (input, options) => {
  const url = typeof input === "string" ? new URL(input, base) : input;
  const record = {
    path:
      typeof input === "string" ? url.pathname + url.search : "Request object",
    method: options?.method ?? "GET",
    aborted: false,
  };
  requests.push(record);
  try {
    return await nativeFetch(url, options);
  } catch (error) {
    record.aborted = error.name === "AbortError";
    throw error;
  }
};
const root = dom.window.document.getElementById("root");
const failures = [];
dom.window.addEventListener("error", (event) => failures.push(event.message));
const assets = resolve("dist/assets");
const entry = (await readdir(assets)).find((file) =>
  /^index-.*\.js$/.test(file),
);
if (!entry) throw new Error("Production entry missing");
await import(pathToFileURL(resolve(assets, entry)).href);
async function wait(condition, label) {
  const deadline = performance.now() + 15000;
  while (!condition()) {
    if (failures.length) throw new Error(failures.join("; "));
    if (performance.now() > deadline) throw new Error(`Timed out: ${label}`);
    await new Promise((resolve) => setTimeout(resolve, 30));
  }
}
function click(text) {
  const element = [...root.querySelectorAll("a,button")].find(
    (node) => node.textContent.trim() === text,
  );
  if (!element) throw new Error(`Missing action: ${text}`);
  element.dispatchEvent(
    new dom.window.MouseEvent("click", { bubbles: true, button: 0 }),
  );
}
if (process.argv.includes("--unavailable")) {
  const message =
    "Local API is unavailable. Start the FleetPulse backend and retry.";
  await wait(
    () => root.textContent.includes(message),
    "backend-unavailable overview",
  );
  for (const [page, title] of [
    ["Driving analytics", "Patterns behind the journey."],
    ["Data quality", "Quality you can trace."],
    ["ML intelligence", "A forecast. With perspective."],
    ["Prediction lab", "A prepared context. A measured forecast."],
  ]) {
    click(page);
    await wait(
      () =>
        root.querySelector("h1")?.textContent === title &&
        root.textContent.includes(message),
      "backend-unavailable " + page,
    );
  }
  if (
    root.querySelectorAll("form input").length ||
    root.querySelector(".prediction-result")
  )
    throw new Error(
      "Unavailable API produced fabricated inference inputs/results",
    );
  console.log(
    JSON.stringify(
      {
        passed: true,
        pages: 5,
        backend_unavailable: true,
        environment: "jsdom production bundle; not browser verification",
      },
      null,
      2,
    ),
  );
} else {
  await wait(
    () => root.textContent.includes("22,434,106"),
    "real overview observations",
  );
  click("Driving analytics");
  await wait(
    () => root.querySelectorAll("tbody tr").length >= 25,
    "bounded real trip table",
  );
  click("Data quality");
  await wait(
    () =>
      root.textContent.includes("22,436,808") &&
      root.textContent.includes("2,702"),
    "pipeline reconciliation",
  );
  click("ML intelligence");
  await wait(
    () =>
      root.textContent.includes("10.89") &&
      root.textContent.includes("No EV is represented in test."),
    "actual model metrics",
  );
  click("Prediction lab");
  await wait(
    () => root.querySelectorAll("form input").length === 31,
    "31 prepared fields",
  );
  click("Run example prediction");
  await wait(
    () => root.querySelector("#past_speed_last_kmh").value !== "",
    "example populated",
  );
  await wait(
    () =>
      root.textContent.includes("36.62") &&
      root.textContent.includes("hgb-day6-ea8d587632fa"),
    "real saved-model inference",
  );
  click("Reset");
  await wait(
    () =>
      !root.querySelector(".prediction-result") &&
      root.querySelector("#past_speed_last_kmh").value === "",
    "reset clears stale prediction",
  );
  if (failures.length) throw new Error(failures.join("; "));
  console.log(
    JSON.stringify(
      {
        passed: true,
        pages: 5,
        real_prediction_kmh: 36.61748855856695,
        prepared_inputs: 31,
        runtime_seconds: (performance.now() - started) / 1000,
        environment:
          "jsdom production-bundle integration; not visual browser QA",
        api_requests: requests.filter((r) => r.path.startsWith("/api/v1")),
      },
      null,
      2,
    ),
  );
}
dom.window.close();
