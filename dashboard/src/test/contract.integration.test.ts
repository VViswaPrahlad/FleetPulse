import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import { prepare } from "../pages/Prediction";
import type {
  Contract,
  Stats,
  Metrics,
  Page,
  Powertrain,
  Pipeline,
  Prediction,
  Cohort,
} from "../api";
import example from "../../../docs/examples/day7_prediction_request.json";

// Optional on a fresh checkout without datasets; required in the actual Day 8
// verification run after scripts/validate_day8_actual.py exports real responses.
const path = resolve(process.cwd(), "../results/day8/contracts.json");
const available = existsSync(path);
const data = available
  ? (JSON.parse(readFileSync(path, "utf8")) as {
      overview: Stats;
      pipeline: Pipeline;
      features: Contract;
      metrics: Metrics;
      powertrains: Page<Powertrain>;
      prediction: Prediction;
      speed_cohorts: Page<Cohort>;
      powertrain_cohorts: Page<Cohort>;
      openapi: { paths: Record<string, unknown> };
    })
  : undefined;
describe.skipIf(!available)("actual FastAPI response compatibility", () => {
  it("reconciles frontend KPI and pipeline counts", () => {
    expect(data!.overview.observation_count).toBe(
      data!.pipeline.silver_observations,
    );
    expect(data!.pipeline.bronze_observations).toBe(
      data!.pipeline.silver_observations +
        data!.pipeline.quarantined_observations,
    );
    expect(
      data!.powertrains.items.reduce((sum, p) => sum + p.vehicle_count, 0),
    ).toBe(data!.overview.vehicle_count);
  });
  it("uses exact feature names, units, nullability and prepared example", () => {
    const inputs = Object.fromEntries(
      Object.entries(example.features).map(([k, v]) => [
        k,
        v == null ? "" : String(v),
      ]),
    );
    expect(prepare(data!.features, inputs)).toEqual(example);
    expect(data!.features.features.filter((f) => f.nullable)).toHaveLength(6);
    expect(data!.prediction.predicted_mean_speed_kmh).toBeCloseTo(
      36.61748855856695,
      10,
    );
  });
  it("finds every dashboard route in OpenAPI", () => {
    for (const path of [
      "/fleet/overview",
      "/vehicles",
      "/trips",
      "/trends/daily",
      "/trends/monthly",
      "/fleet/powertrains",
      "/quality/summary",
      "/quality/pipeline",
      "/ml/metrics",
      "/ml/vehicle-errors",
      "/ml/cohorts",
      "/ml/features",
      "/ml/predict",
    ])
      expect(data!.openapi.paths).toHaveProperty("/api/v1" + path);
  });
  it("reconciles speed and powertrain cohorts on identical evaluation windows", () => {
    const speed = data!.speed_cohorts.items.filter(
      (c) => c.method === "hist_gradient_boosting",
    );
    const power = data!.powertrain_cohorts.items.filter(
      (c) => c.method === "hist_gradient_boosting",
    );
    expect(speed.reduce((n, c) => n + c.windows, 0)).toBe(1919);
    expect(power.reduce((n, c) => n + c.windows, 0)).toBe(1919);
    expect(power.some((c) => c.category === "EV")).toBe(false);
    expect(data!.metrics.vehicle_cluster_bootstrap.test.vehicles).toBe(50);
  });
});
