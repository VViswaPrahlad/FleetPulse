import { useEffect, useState } from "react";

export function apiBase(value?: string): string {
  if (!value) return "/api/v1";
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
  return url.origin + "/api/v1";
}
const API_BASE = apiBase(import.meta.env.VITE_API_URL);
export const IS_PUBLIC_API = API_BASE.startsWith("https://");
const PUBLIC_UNAVAILABLE =
  "The API may be unavailable or waking from sleep. Wait about a minute and retry.";

export type Page<T> = {
  items: T[];
  total: number;
  limit: number;
  offset: number;
};
export type Stats = {
  observation_count: number;
  vehicle_count: number;
  trip_count: number;
  speed_sample_mean_kmh: number | null;
  speed_sample_p50_kmh: number | null;
  speed_sample_p95_kmh: number | null;
  speed_max_kmh: number | null;
  speed_time_weighted_mean_kmh: number | null;
  observed_distance_km: number | null;
  gap_gt_2s_count: number;
  duplicate_timestamp_count: number;
  flagged_observation_count: number;
  missing_speed_count: number;
  missing_fuel_rate_count: number;
  first_trip_start_reference_day: string;
  last_trip_start_reference_day: string;
};
export type Vehicle = Stats & { vehicle_id: number; engine_type: string };
export type Trip = Vehicle & { trip_id: number; elapsed_span_s: number };
export type Trend = Stats & {
  trip_start_reference_day?: string;
  trip_start_reference_month?: string;
};
export type Powertrain = Stats & { engine_type: string };
export type Quality = {
  overview: Stats;
  flags: Page<{
    quality_flag: string;
    observation_count: number;
    observation_fraction: number;
  }>;
  semantics: string;
};
export type Pipeline = {
  bronze_observations: number;
  silver_observations: number;
  quarantined_observations: number;
  gold_source_observations: number;
  gold_vehicles: number;
  gold_trips: number;
  exclusion_reasons: Record<string, number>;
  missing_measurements: Record<string, number>;
  semantics: string;
};
export type Split = "validation" | "test";
export type Method =
  | "hist_gradient_boosting"
  | "last_observed_speed"
  | "past_mean_persistence"
  | "training_historical_mean";
export const methodNames: Record<Method, string> = {
  hist_gradient_boosting: "Gradient boosting",
  last_observed_speed: "Last observed speed",
  past_mean_persistence: "Past mean speed",
  training_historical_mean: "Training average",
};
export type Metrics = {
  model_id: string;
  target: string;
  feature_count: number;
  metrics: Record<Split, Record<Method, { mae_kmh: number; rmse_kmh: number }>>;
  improvements: Record<
    Split,
    { mae_improvement_pct: number; rmse_improvement_pct: number }
  >;
  vehicle_cluster_bootstrap: Record<
    Split,
    {
      vehicles: number;
      replicates: number;
      confidence: number;
      intervals: Record<string, [number, number]>;
    }
  >;
  limitations: string[];
};
export type Cohort = {
  split: Split;
  dimension: string;
  category: string;
  method: Method;
  windows: number;
  vehicles: number;
  mae_kmh: number;
  rmse_kmh: number;
};
export type VehicleError = {
  vehicle_id: number;
  method: Method;
  split: Split;
  windows: number;
  mae_kmh: number;
  rmse_kmh: number;
};
export type Feature = {
  name: string;
  units: string;
  required: boolean;
  nullable: boolean;
  ge?: number;
  le?: number;
};
export type Contract = {
  schema_version: string;
  history_seconds: number;
  forecast_seconds: number;
  max_sampling_gap_seconds: number;
  input_kind: string;
  feature_order: string[];
  features: Feature[];
  null_policy: string;
  scope: string;
};
export type Prediction = {
  predicted_mean_speed_kmh: number;
  forecast_seconds: number;
  history_seconds: number;
  units: string;
  model_id: string;
  warning: string;
};
export class ApiError extends Error {
  constructor(
    message: string,
    public details: { field?: string; message?: string }[] = [],
  ) {
    super(message);
  }
}
export async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(API_BASE + path, options);
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw new ApiError(
      IS_PUBLIC_API
        ? PUBLIC_UNAVAILABLE
        : "Cannot reach the local API. Start the FleetPulse backend and retry.",
    );
  }
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    if (!response.ok && response.status >= 500) {
      throw new ApiError(
        IS_PUBLIC_API
          ? PUBLIC_UNAVAILABLE
          : "Local API is unavailable. Start the FleetPulse backend and retry.",
      );
    }
    throw new ApiError(
      IS_PUBLIC_API
        ? PUBLIC_UNAVAILABLE
        : "The API returned an unreadable response.",
    );
  }
  if (!response.ok) {
    const error = (
      body as {
        error?: { message?: string; details?: ApiError["details"] };
      } | null
    )?.error;
    throw new ApiError(
      typeof error?.message === "string"
        ? error.message
        : `Request failed (${response.status}).`,
      Array.isArray(error?.details) ? error.details : [],
    );
  }
  return body as T;
}
export function useApi<T>(path: string | null) {
  const [state, setState] = useState<{
    data?: T;
    loading: boolean;
    error?: string;
  }>({ loading: path !== null });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (path === null) {
      setState({ loading: false });
      return;
    }
    const controller = new AbortController();
    setState({ loading: true });
    request<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted) setState({ data, loading: false });
      })
      .catch((e) => {
        if (!controller.signal.aborted)
          setState({ loading: false, error: (e as Error).message });
      });
    return () => controller.abort();
  }, [path, revision]);
  return { ...state, retry: () => setRevision((x) => x + 1) };
}
export function query(
  path: string,
  params: Record<string, string | number | undefined>,
) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== "") search.set(key, String(value));
  });
  return path + "?" + search.toString();
}
