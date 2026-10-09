import { useRef, useState } from "react";
import { ArrowRight, FlaskConical, RotateCcw } from "lucide-react";
import example from "../../../docs/examples/day7_prediction_request.json";
import {
  ApiError,
  request,
  useApi,
  type Contract,
  type Prediction,
} from "../api";
import { Heading, human, number, Panel, State } from "../components";

export function prepare(contract: Contract, inputs: Record<string, string>) {
  const features: Record<string, number | null> = {};
  if (
    contract.features.length !== 31 ||
    contract.feature_order.length !== 31 ||
    new Set(contract.feature_order).size !== 31 ||
    contract.feature_order.some(
      (name) => !contract.features.some((f) => f.name === name),
    )
  )
    throw new Error("The API feature contract is incompatible.");
  for (const feature of contract.features) {
    const raw = inputs[feature.name]?.trim() ?? "";
    if (!raw) {
      if (feature.nullable) {
        features[feature.name] = null;
        continue;
      }
      throw new Error(`Enter ${human(feature.name)}.`);
    }
    const value = Number(raw);
    if (
      !Number.isFinite(value) ||
      !/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(raw)
    )
      throw new Error(`${human(feature.name)} must be a finite number.`);
    if (
      (feature.ge !== undefined && value < feature.ge) ||
      (feature.le !== undefined && value > feature.le)
    )
      throw new Error(`${human(feature.name)} is outside the allowed range.`);
    features[feature.name] = value;
  }
  for (const f of contract.features.filter((f) => f.nullable)) {
    const fraction =
      features[f.name.replace(/_sample_mean$/, "_observed_fraction")];
    if ((features[f.name] === null) !== (fraction === 0))
      throw new Error(
        `${human(f.name)} must be null exactly when its observed fraction is zero.`,
      );
  }
  return {
    input_kind: contract.input_kind,
    feature_schema_version: contract.schema_version,
    history_seconds: contract.history_seconds,
    speed_unit: "km/h",
    acceleration_unit: "m/s^2",
    time_unit: "s",
    features,
  };
}
export function PredictionLab() {
  const contract = useApi<Contract>("/ml/features");
  const inFlight = useRef(false);
  const [inputs, setInputs] = useState<Record<string, string>>({}),
    [result, setResult] = useState<Prediction>(),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const groups = [
    {
      name: "Speed & stopping",
      match: (name: string) => name.includes("speed") || name.includes("stop_"),
    },
    { name: "Acceleration", match: (name: string) => name.includes("accel") },
    {
      name: "Sampling coverage",
      match: (name: string) =>
        ["past_sample_count", "past_gap_max_s"].includes(name),
    },
    {
      name: "Available sensors",
      match: (name: string) =>
        !name.includes("speed") &&
        !name.includes("stop_") &&
        !name.includes("accel") &&
        !["past_sample_count", "past_gap_max_s"].includes(name),
    },
  ];
  const reset = () => {
    setInputs({});
    setResult(undefined);
    setError("");
  };
  const exampleInputs = () =>
    Object.fromEntries(
      Object.entries(example.features).map(([name, value]) => [
        name,
        value == null ? "" : String(value),
      ]),
    );
  async function predict(values: Record<string, string>) {
    if (inFlight.current || !contract.data) return;
    inFlight.current = true;
    setError("");
    setResult(undefined);
    setBusy(true);
    try {
      const payload = prepare(contract.data, values);
      setResult(
        await request<Prediction>("/ml/predict", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }),
      );
    } catch (e) {
      const err = e as Error;
      setError(
        err.message +
          (err instanceof ApiError && err.details.length
            ? " " +
              err.details
                .map((d) => [d.field, d.message].filter(Boolean).join(": "))
                .join("; ")
            : ""),
      );
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await predict(inputs);
  }
  function runExample() {
    if (inFlight.current) return;
    const values = exampleInputs();
    setInputs(values);
    void predict(values);
  }
  return (
    <>
      <Heading
        eyebrow="PREDICTION LAB"
        title="A prepared context. A measured forecast."
        description="Try a verified telemetry example, or supply the saved model's exact 31 prepared features."
      />
      <div className="notice warning">
        <strong>Raw GPS input is not sufficient.</strong> Supply a fully
        prepared, past-only 60-second feature vector with chronological,
        trip-boundary and ≤2-second gap checks. This form does not derive
        features from raw telemetry or certify their provenance.
      </div>
      <State {...contract}>
        {contract.data && (
          <>
            <div className="prediction-quick-demo">
              <Panel
                title="Quick Demo"
                subtitle="One verified context. A real API forecast."
              >
                <p>
                  Run the existing anonymous Day 7 example from actual prepared,
                  past-only telemetry. The button loads all 31 verified features
                  and calls the saved model through the prediction API.
                </p>
                <div className="actions">
                  <button
                    className="button primary"
                    disabled={busy}
                    onClick={runExample}
                  >
                    <FlaskConical size={17} />
                    {busy ? "Running prediction…" : "Run example prediction"}
                    <ArrowRight size={16} />
                  </button>
                  <button
                    className="button secondary"
                    disabled={busy}
                    onClick={reset}
                  >
                    <RotateCcw size={15} />
                    Reset
                  </button>
                </div>
                <p className="footnote">
                  No prediction is pre-filled. Results appear only after a
                  successful API response. Inspect the example's prepared
                  features in Advanced below.
                </p>
              </Panel>
            </div>
            {error && (
              <div className="notice error" role="alert">
                {error}
              </div>
            )}
            {result && (
              <section
                className="prediction-result"
                role="status"
                aria-label="Prediction result"
              >
                <div>
                  <span className="eyebrow">
                    NEXT {result.forecast_seconds} SECONDS
                  </span>
                  <h2>
                    {number(result.predicted_mean_speed_kmh, 2)}
                    <small>{result.units}</small>
                  </h2>
                  <p>Predicted time-weighted mean vehicle speed</p>
                </div>
                <div>
                  <span className="badge">{result.model_id}</span>
                  <p>{result.warning}</p>
                  <p className="muted">
                    This is a point forecast. No individual-trip confidence
                    interval is available.
                  </p>
                </div>
              </section>
            )}
            <details className="prediction-advanced">
              <summary>Advanced: Prepared feature vector</summary>
              <Panel
                title="Prepared feature vector"
                subtitle="Every field is required in the payload. Only six optional sensor means may be null."
                action={
                  <div className="actions">
                    <button
                      className="button secondary"
                      disabled={busy}
                      onClick={() => {
                        setInputs(exampleInputs());
                        setResult(undefined);
                        setError("");
                      }}
                    >
                      <FlaskConical size={15} />
                      Load verified example
                    </button>
                  </div>
                }
              >
                <p className="footnote">
                  The example is the documented, anonymous Day 7 vector from
                  actual prepared telemetry. Blank sensor means represent null,
                  never zero. Observed fractions must explicitly declare
                  availability.
                </p>
                <form onSubmit={submit} noValidate>
                  <fieldset disabled={busy} className="feature-fieldset">
                    {groups.map((group) => (
                      <div className="feature-group" key={group.name}>
                        <h3>
                          {group.name}
                          <span>
                            {
                              contract.data!.features.filter((f) =>
                                group.match(f.name),
                              ).length
                            }{" "}
                            features
                          </span>
                        </h3>
                        <div className="feature-grid">
                          {contract
                            .data!.features.filter((f) => group.match(f.name))
                            .map((f) => (
                              <label key={f.name} htmlFor={f.name}>
                                <span>{human(f.name)}</span>
                                <div className="unit-input">
                                  <input
                                    id={f.name}
                                    name={f.name}
                                    type="text"
                                    inputMode="decimal"
                                    value={inputs[f.name] ?? ""}
                                    placeholder={
                                      f.nullable
                                        ? "Null if unavailable"
                                        : "Required"
                                    }
                                    aria-required={!f.nullable}
                                    onChange={(e) => {
                                      setInputs((old) => ({
                                        ...old,
                                        [f.name]: e.target.value,
                                      }));
                                      setResult(undefined);
                                      setError("");
                                    }}
                                  />
                                  <small>{f.units}</small>
                                </div>
                                <code>{f.name}</code>
                              </label>
                            ))}
                        </div>
                      </div>
                    ))}
                  </fieldset>
                  <div className="prediction-submit">
                    <span className="muted">
                      60s history → next 60s mean speed · CPU inference only
                    </span>
                    <button
                      className="button primary"
                      disabled={busy}
                      type="submit"
                    >
                      {busy ? "Running inference…" : "Predict mean speed"}
                      <ArrowRight size={16} />
                    </button>
                  </div>
                </form>
              </Panel>
            </details>
          </>
        )}
      </State>
    </>
  );
}
