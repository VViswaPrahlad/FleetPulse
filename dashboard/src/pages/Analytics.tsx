import { useState } from "react";
import {
  ArrowUpRight,
  Car,
  Database,
  Gauge,
  GitBranch,
  Route,
  ShieldCheck,
  Timer,
  Zap,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  query,
  useApi,
  methodNames,
  type Stats,
  type Page,
  type Powertrain,
  type Trip,
  type Vehicle,
  type Quality,
  type Pipeline,
  type Metrics,
  type Split,
  type Cohort,
  type VehicleError,
  type Method,
} from "../api";
import {
  colors,
  Heading,
  Kpi,
  number,
  Panel,
  Pagination,
  State,
  tooltipStyle,
  Trends,
  human,
} from "../components";

export function Overview() {
  const fleet = useApi<Stats>("/fleet/overview"),
    power = useApi<Page<Powertrain>>("/fleet/powertrains?limit=100");
  const f = fleet.data;
  return (
    <>
      <Heading
        eyebrow="FLEET OPERATIONS"
        title="Every trip. A clearer picture."
        description="Explore measured vehicle activity, driving patterns and energy telemetry from VED."
      />
      <State {...fleet}>
        {f && (
          <>
            <div className="dataset-banner">
              <span className="status-dot" />
              <strong>Historical coverage</strong>
              <span>
                {f.first_trip_start_reference_day} →{" "}
                {f.last_trip_start_reference_day}
              </span>
              <span className="badge">Silver-backed Gold analytics</span>
            </div>
            <div className="kpi-grid">
              <Kpi
                label="Vehicles"
                value={number(f.vehicle_count)}
                note="Unique vehicles represented"
                icon={<Car size={19} />}
              />
              <Kpi
                label="Trips"
                value={number(f.trip_count)}
                note="Vehicle-scoped trip records"
                icon={<Route size={19} />}
              />
              <Kpi
                label="Observations"
                value={number(f.observation_count)}
                note="Retained Silver observations"
                icon={<Database size={19} />}
              />
              <Kpi
                label="Mean speed"
                value={number(f.speed_time_weighted_mean_kmh, 1)}
                unit="km/h"
                note="Time weighted; eligible intervals"
                icon={<Gauge size={19} />}
              />
            </div>
            <div className="grid-two">
              <Trends compactView />
              <Panel
                title="Powertrain composition"
                subtitle="Vehicle counts, not sensor availability."
              >
                <State {...power} empty={!power.data?.items.length}>
                  <div className="donut-layout">
                    <div
                      className="donut"
                      role="img"
                      aria-label="Vehicles by powertrain"
                    >
                      <ResponsiveContainer width="100%" height="100%">
                        <PieChart>
                          <Pie
                            data={power.data?.items}
                            dataKey="vehicle_count"
                            nameKey="engine_type"
                            innerRadius={64}
                            outerRadius={91}
                            paddingAngle={5}
                            stroke="none"
                          >
                            {power.data?.items.map((p, i) => (
                              <Cell
                                key={p.engine_type}
                                fill={colors[i % colors.length]}
                              />
                            ))}
                          </Pie>
                          <Tooltip contentStyle={tooltipStyle} />
                        </PieChart>
                      </ResponsiveContainer>
                      <div className="donut-center">
                        <strong>{number(f.vehicle_count)}</strong>
                        <span>vehicles</span>
                      </div>
                    </div>
                    <ul className="legend-list">
                      {power.data?.items.map((p, i) => (
                        <li key={p.engine_type}>
                          <span
                            className="legend-dot"
                            style={{ background: colors[i % colors.length] }}
                          />
                          {p.engine_type}
                          <strong>{number(p.vehicle_count)}</strong>
                          <small>
                            {number(
                              (p.vehicle_count / f.vehicle_count) * 100,
                              1,
                            )}
                            %
                          </small>
                        </li>
                      ))}
                    </ul>
                  </div>
                </State>
              </Panel>
            </div>
            <div className="grid-three">
              <Kpi
                label="Observed distance"
                value={number(f.observed_distance_km, 0)}
                unit="km"
                note="Partial estimate; speed integration across gaps ≤2s"
                icon={<Route size={19} />}
              />
              <Kpi
                label="Median speed"
                value={number(f.speed_sample_p50_kmh, 1)}
                unit="km/h"
                note="Observation-weighted fleet percentile"
                icon={<Gauge size={19} />}
              />
              <Kpi
                label="95th percentile"
                value={number(f.speed_sample_p95_kmh, 1)}
                unit="km/h"
                note="Observation-weighted fleet percentile"
                icon={<ArrowUpRight size={19} />}
              />
            </div>
            <p className="footnote">
              Distance excludes unsupported intervals and is not odometer
              mileage. Sample statistics and time-weighted speed use different
              denominators.
            </p>
          </>
        )}
      </State>
    </>
  );
}

export function Driving() {
  const [kind, setKind] = useState<"trips" | "vehicles">("trips"),
    [powertrain, setPowertrain] = useState(""),
    [vehicle, setVehicle] = useState(""),
    [offset, setOffset] = useState(0);
  const invalid =
    vehicle !== "" && (!/^\d+$/.test(vehicle) || Number(vehicle) > 2147483647);
  const rows = useApi<Page<Trip | Vehicle>>(
    query("/" + kind, {
      limit: 25,
      offset,
      powertrain,
      vehicle_id: kind === "trips" && !invalid ? vehicle : undefined,
    }),
  );
  return (
    <>
      <Heading
        eyebrow="DRIVING ANALYTICS"
        title="Patterns behind the journey."
        description="Inspect trips and vehicles without loading raw telemetry into the browser."
      />
      <Panel
        title="Explore the fleet"
        subtitle="Server-side filters · 25 records per page"
        action={
          <div className="segmented">
            {(["trips", "vehicles"] as const).map((k) => (
              <button
                key={k}
                aria-pressed={kind === k}
                onClick={() => {
                  setKind(k);
                  setOffset(0);
                }}
              >
                {k === "trips" ? "Trips" : "Vehicles"}
              </button>
            ))}
          </div>
        }
      >
        <div className="filters">
          <label>
            Powertrain
            <select
              value={powertrain}
              onChange={(e) => {
                setPowertrain(e.target.value);
                setOffset(0);
              }}
            >
              <option value="">All powertrains</option>
              {["ICE", "HEV", "PHEV", "EV"].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </label>
          {kind === "trips" && (
            <label>
              Vehicle ID
              <input
                inputMode="numeric"
                placeholder="Any vehicle"
                value={vehicle}
                onChange={(e) => {
                  setVehicle(e.target.value);
                  setOffset(0);
                }}
              />
            </label>
          )}
          <button
            className="button secondary"
            onClick={() => {
              setPowertrain("");
              setVehicle("");
              setOffset(0);
            }}
          >
            Reset filters
          </button>
        </div>
        {invalid && kind === "trips" ? (
          <p className="notice" role="alert">
            Enter a nonnegative integer vehicle ID up to 2147483647.
          </p>
        ) : (
          <State {...rows} empty={!rows.data?.items.length}>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Vehicle</th>
                    {kind === "trips" && <th>Trip</th>}
                    <th>Powertrain</th>
                    <th>Observations</th>
                    <th>Mean speed</th>
                    <th>P95 speed</th>
                    <th>Partial distance</th>
                    <th>Gaps &gt;2s</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.data?.items.map((row) => (
                    <tr
                      key={`${row.vehicle_id}-${"trip_id" in row ? row.trip_id : ""}`}
                    >
                      <td className="mono">V{row.vehicle_id}</td>
                      {kind === "trips" && (
                        <td className="mono">
                          {"trip_id" in row ? row.trip_id : "—"}
                        </td>
                      )}
                      <td>
                        <span className="badge">{row.engine_type}</span>
                      </td>
                      <td>{number(row.observation_count)}</td>
                      <td>
                        {number(row.speed_time_weighted_mean_kmh, 1)}{" "}
                        <small>km/h</small>
                      </td>
                      <td>
                        {number(row.speed_sample_p95_kmh, 1)}{" "}
                        <small>km/h</small>
                      </td>
                      <td>
                        {number(row.observed_distance_km, 2)} <small>km</small>
                      </td>
                      <td>{number(row.gap_gt_2s_count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </State>
        )}
        {rows.data && !invalid && (
          <Pagination
            total={rows.data.total}
            limit={25}
            offset={offset}
            change={setOffset}
          />
        )}
        <p className="footnote">
          — means unavailable. Trip IDs are unique within a vehicle. Distance is
          supported-interval speed integration, not total travel distance.
        </p>
      </Panel>
      <Trends title="Activity over time" />
    </>
  );
}

export function DataQuality() {
  const quality = useApi<Quality>("/quality/summary"),
    pipeline = useApi<Pipeline>("/quality/pipeline");
  const p = pipeline.data,
    q = quality.data;
  const missing = p
    ? Object.entries(p.missing_measurements).map(([key, value]) => ({
        name: human(key),
        count: value,
        percentage: (value / p.silver_observations) * 100,
      }))
    : [];
  return (
    <>
      <Heading
        eyebrow="DATA TRUST"
        title="Quality you can trace."
        description="Reconciled processing stages, explicit exclusions and preserved missing measurements."
      />
      <Panel
        title="Bronze → Silver → Gold"
        subtitle="Existing outputs; no reprocessing occurs in the dashboard."
      >
        <State {...pipeline}>
          {p && (
            <>
              <div className="pipeline">
                {[
                  {
                    name: "Bronze",
                    value: p.bronze_observations,
                    note: "Original observations",
                    icon: Database,
                  },
                  {
                    name: "Silver",
                    value: p.silver_observations,
                    note: "Retained observations",
                    icon: ShieldCheck,
                  },
                  {
                    name: "Gold",
                    value: p.gold_source_observations,
                    note: "Source observations aggregated",
                    icon: GitBranch,
                  },
                ].map(({ name, value, note, icon: Icon }) => (
                  <div className="pipeline-stage" key={name}>
                    <span className="stage-icon">
                      <Icon size={21} />
                    </span>
                    <span className="eyebrow">{name}</span>
                    <strong>{number(value)}</strong>
                    <p>{note}</p>
                  </div>
                ))}
              </div>
              <div className="notice">
                <strong>
                  {number(p.quarantined_observations)} quarantined
                </strong>{" "}
                · Negative elapsed timestamps. Bronze = Silver + quarantine.
                Gold summarizes {number(p.gold_vehicles)} vehicles and{" "}
                {number(p.gold_trips)} trips; its source-observation count is
                not its Parquet row count.
              </div>
            </>
          )}
        </State>
      </Panel>
      <div className="grid-two">
        <Panel
          title="Missing measurements"
          subtitle="Percentage of retained Silver observations; no imputation."
        >
          <State {...pipeline} empty={!missing.length}>
            <div
              className="chart tall"
              role="img"
              aria-label="Missing measurement percentages"
            >
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={missing}
                  layout="vertical"
                  margin={{ left: 8, right: 25 }}
                >
                  <CartesianGrid stroke="#263142" horizontal={false} />
                  <XAxis
                    type="number"
                    domain={[0, 100]}
                    unit="%"
                    stroke="#8593a7"
                    fontSize={11}
                  />
                  <YAxis
                    dataKey="name"
                    type="category"
                    width={125}
                    stroke="#8593a7"
                    fontSize={11}
                  />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    formatter={(v) => `${number(Number(v), 2)}%`}
                  />
                  <Bar
                    dataKey="percentage"
                    name="Missing"
                    fill={colors[1]}
                    radius={[0, 4, 4, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <details className="chart-data">
              <summary>View measurement counts</summary>
              <ul className="stat-list">
                {missing.map((m) => (
                  <li key={m.name}>
                    <span>{m.name}</span>
                    <strong>
                      {number(m.count)} · {number(m.percentage, 2)}%
                    </strong>
                  </li>
                ))}
              </ul>
            </details>
          </State>
        </Panel>
        <Panel
          title="Quality signals"
          subtitle="Flag counts may overlap; they are not additional exclusions."
        >
          <State {...quality} empty={!q?.flags.items.length}>
            <ul className="stat-list">
              {q?.flags.items.map((flag) => (
                <li key={flag.quality_flag}>
                  <span>{human(flag.quality_flag)}</span>
                  <div>
                    <strong>{number(flag.observation_count)}</strong>
                    <small>
                      {number(flag.observation_fraction * 100, 3)}% of Silver
                    </small>
                  </div>
                </li>
              ))}
            </ul>
            <p className="footnote">{q?.semantics}</p>
          </State>
        </Panel>
      </div>
      <Panel
        title="Cleaning policy"
        subtitle="Measurement provenance remains in Bronze."
      >
        <div className="policy-grid">
          <div>
            <Timer size={19} />
            <h3>Sampling gaps</h3>
            <p>
              Intervals above 2 seconds are flagged and excluded from supported
              distance calculations and forecasting contexts.
            </p>
          </div>
          <div>
            <Zap size={19} />
            <h3>SOC precision</h3>
            <p>
              Tiny floating-point overshoots are clipped to 100% and flagged.
              Signed battery current and valid load above 100% remain measured
              values.
            </p>
          </div>
          <div>
            <ShieldCheck size={19} />
            <h3>Missing sensors</h3>
            <p>
              Unavailable measurements remain null. Fuel forecasting was
              rejected because continuous measured fuel coverage was
              insufficient.
            </p>
          </div>
        </div>
      </Panel>
    </>
  );
}

export function Intelligence() {
  const [split, setSplit] = useState<Split>("test"),
    [dimension, setDimension] = useState("actual_target_speed_range"),
    [offset, setOffset] = useState(0);
  const metrics = useApi<Metrics>("/ml/metrics"),
    cohorts = useApi<Page<Cohort>>(query("/ml/cohorts", { split, dimension })),
    errors = useApi<Page<VehicleError>>(
      query("/ml/vehicle-errors", { split, limit: 25, offset }),
    );
  const m = metrics.data,
    ci = m?.vehicle_cluster_bootstrap[split];
  const comparison = m
    ? Object.entries(m.metrics[split]).map(([key, value]) => ({
        name: methodNames[key as Method],
        ...value,
      }))
    : [];
  const groups = [...new Set(cohorts.data?.items.map((c) => c.category))].map(
    (category) => {
      const rows = cohorts.data!.items.filter((c) => c.category === category);
      return {
        category,
        model: rows.find((c) => c.method === "hist_gradient_boosting")?.mae_kmh,
        persistence: rows.find((c) => c.method === "last_observed_speed")
          ?.mae_kmh,
        windows: rows[0].windows,
        vehicles: rows[0].vehicles,
      };
    },
  );
  return (
    <>
      <Heading
        eyebrow="ML INTELLIGENCE"
        title="A forecast. With perspective."
        description="Next-60-second time-weighted mean speed, using only the preceding 60 seconds."
      >
        <div className="segmented">
          {(["validation", "test"] as const).map((s) => (
            <button
              key={s}
              aria-pressed={s === split}
              onClick={() => {
                setSplit(s);
                setOffset(0);
              }}
            >
              {s === "test" ? "Held-out test" : "Validation"}
            </button>
          ))}
        </div>
      </Heading>
      <State {...metrics}>
        {m && (
          <>
            <div className="kpi-grid">
              <Kpi
                label="Model MAE"
                value={number(
                  m.metrics[split].hist_gradient_boosting.mae_kmh,
                  2,
                )}
                unit="km/h"
                note="Same examples as all baselines"
                icon={<Gauge size={19} />}
              />
              <Kpi
                label="Model RMSE"
                value={number(
                  m.metrics[split].hist_gradient_boosting.rmse_kmh,
                  2,
                )}
                unit="km/h"
                note="Larger errors weighted more heavily"
                icon={<Route size={19} />}
              />
              <Kpi
                label="MAE improvement"
                value={number(m.improvements[split].mae_improvement_pct, 2)}
                unit="%"
                note="Pooled; versus last observed speed"
                icon={<ArrowUpRight size={19} />}
              />
              <Kpi
                label="Independent vehicles"
                value={number(ci?.vehicles)}
                note="Vehicle-held-out evaluation"
                icon={<Car size={19} />}
              />
            </div>
            <div className="notice warning">
              <strong>Limits of generalization</strong>
              <ul>
                {m.limitations.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            </div>
            <div className="grid-two">
              <Panel
                title="Model vs. baselines"
                subtitle={`${split} · Lower error is better · km/h`}
              >
                <div
                  className="chart tall"
                  role="img"
                  aria-label="Model and three baselines MAE and RMSE"
                >
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={comparison}
                      layout="vertical"
                      margin={{ left: 0, right: 16 }}
                    >
                      <CartesianGrid stroke="#263142" horizontal={false} />
                      <XAxis type="number" stroke="#8593a7" fontSize={11} />
                      <YAxis
                        dataKey="name"
                        type="category"
                        width={118}
                        stroke="#8593a7"
                        fontSize={11}
                      />
                      <Tooltip
                        contentStyle={tooltipStyle}
                        formatter={(v) => `${number(Number(v), 2)} km/h`}
                      />
                      <Legend />
                      <Bar
                        dataKey="mae_kmh"
                        name="MAE"
                        fill={colors[0]}
                        radius={[0, 3, 3, 0]}
                      />
                      <Bar
                        dataKey="rmse_kmh"
                        name="RMSE"
                        fill={colors[1]}
                        radius={[0, 3, 3, 0]}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
                <details className="chart-data">
                  <summary>View exact errors</summary>
                  <div className="table-wrap">
                    <table>
                      <thead>
                        <tr>
                          <th>Method</th>
                          <th>MAE</th>
                          <th>RMSE</th>
                        </tr>
                      </thead>
                      <tbody>
                        {comparison.map((c) => (
                          <tr key={c.name}>
                            <td>{c.name}</td>
                            <td>{number(c.mae_kmh, 4)}</td>
                            <td>{number(c.rmse_kmh, 4)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              </Panel>
              <Panel
                title="Vehicle-cluster uncertainty"
                subtitle={`${number(ci?.replicates)} fixed-seed whole-vehicle bootstrap resamples · 95% confidence`}
              >
                <ul className="stat-list">
                  {[
                    ["model_mae_kmh", "Pooled model MAE"],
                    ["model_rmse_kmh", "Pooled model RMSE"],
                    ["paired_mae_reduction_kmh", "Paired pooled MAE reduction"],
                    [
                      "paired_vehicle_macro_mae_reduction_kmh",
                      "Paired vehicle-macro MAE reduction",
                    ],
                  ].map(([key, label]) => (
                    <li key={key}>
                      <span>{label}</span>
                      <strong>
                        {number(ci?.intervals[key]?.[0], 2)} to{" "}
                        {number(ci?.intervals[key]?.[1], 2)} <small>km/h</small>
                      </strong>
                    </li>
                  ))}
                </ul>
                <p className="footnote">
                  These quantify evaluation uncertainty, not a prediction
                  interval for an individual trip. The vehicle-macro interval
                  crossing zero limits claims of uniform improvement.
                </p>
                <div className="model-meta">
                  <span className="badge">31 past-only features</span>
                  <span className="badge">No shared vehicles</span>
                  <span className="badge">No overlapping contexts</span>
                </div>
              </Panel>
            </div>
          </>
        )}
      </State>
      <Panel
        title="Performance by cohort"
        subtitle="Groups use actual future target speed for evaluation only; never model inputs."
        action={
          <label className="sr-only-label">
            Cohort grouping
            <select
              aria-label="Cohort grouping"
              value={dimension}
              onChange={(e) => setDimension(e.target.value)}
            >
              <option value="actual_target_speed_range">Speed range</option>
              <option value="powertrain">Powertrain</option>
            </select>
          </label>
        }
      >
        <State {...cohorts} empty={!groups.length}>
          <div
            className="chart"
            role="img"
            aria-label="Cohort model versus last observed speed MAE"
          >
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={groups}>
                <CartesianGrid stroke="#263142" vertical={false} />
                <XAxis dataKey="category" stroke="#8593a7" fontSize={11} />
                <YAxis stroke="#8593a7" fontSize={11} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(v) => `${number(Number(v), 2)} km/h`}
                />
                <Legend />
                <Bar
                  dataKey="model"
                  name="Model MAE"
                  fill={colors[0]}
                  radius={[3, 3, 0, 0]}
                />
                <Bar
                  dataKey="persistence"
                  name="Last observed MAE"
                  fill={colors[2]}
                  radius={[3, 3, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="cohort-counts">
            {groups.map((g) => (
              <span key={g.category}>
                <strong>{g.category}</strong> · {number(g.windows)} windows ·{" "}
                {g.vehicles} vehicles
              </span>
            ))}
          </div>
        </State>
      </Panel>
      <Panel
        title="Vehicle-level model errors"
        subtitle={`${split} vehicles · window counts and errors on identical held-out examples`}
      >
        <State {...errors} empty={!errors.data?.items.length}>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Vehicle</th>
                  <th>Windows</th>
                  <th>MAE · km/h</th>
                  <th>RMSE · km/h</th>
                </tr>
              </thead>
              <tbody>
                {errors.data?.items.map((e) => (
                  <tr key={e.vehicle_id}>
                    <td className="mono">V{e.vehicle_id}</td>
                    <td>{number(e.windows)}</td>
                    <td>{number(e.mae_kmh, 3)}</td>
                    <td>{number(e.rmse_kmh, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </State>
        {errors.data && (
          <Pagination
            total={errors.data.total}
            offset={offset}
            limit={25}
            change={setOffset}
          />
        )}
      </Panel>
    </>
  );
}
