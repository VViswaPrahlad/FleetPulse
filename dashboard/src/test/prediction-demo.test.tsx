import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { PredictionLab } from "../pages/Prediction";
import example from "../../../docs/examples/day7_prediction_request.json";

const contract = {
  input_kind: example.input_kind,
  schema_version: example.feature_schema_version,
  history_seconds: 60,
  feature_order: Object.keys(example.features),
  features: Object.keys(example.features).map((name) => ({
    name,
    units: "fixture unit",
    nullable: name.endsWith("_sample_mean") && !name.includes("speed"),
  })),
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
// An intentionally different fixture response proves the UI renders the API
// result, never a hardcoded verified-example prediction.
const predicted = {
  predicted_mean_speed_kmh: 27.43,
  forecast_seconds: 60,
  units: "km/h",
  model_id: "fixture-response",
  warning: "Prepared input provenance is caller-supplied.",
};

describe("Quick Demo prediction flow", () => {
  it("defaults to collapsed advanced inputs with no automatic prediction", async () => {
    const fetcher = vi.fn().mockResolvedValue(json(contract));
    vi.stubGlobal("fetch", fetcher);
    render(<PredictionLab />);
    expect(
      await screen.findByRole("button", { name: "Run example prediction" }),
    ).toBeVisible();
    expect(
      screen.getByText("Advanced: Prepared feature vector").closest("details"),
    ).not.toHaveAttribute("open");
    expect(screen.getByLabelText(/speed last kmh/)).not.toBeVisible();
    expect(
      screen.queryByRole("status", { name: "Prediction result" }),
    ).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("one click sends the exact verified payload and displays only the returned value", async () => {
    const fetcher = vi.fn((url: string, _options?: RequestInit) =>
      Promise.resolve(json(url.endsWith("/features") ? contract : predicted)),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<PredictionLab />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Run example prediction" }),
    );
    const result = await screen.findByRole("status", {
      name: "Prediction result",
    });
    expect(result).toHaveTextContent("27.43");
    expect(result).toHaveTextContent("km/h");
    expect(result).not.toHaveTextContent("36.62");
    const calls = fetcher.mock.calls.filter(([url]) =>
      url.endsWith("/predict"),
    );
    expect(calls).toHaveLength(1);
    expect(JSON.parse((calls[0][1] as RequestInit).body as string)).toEqual(
      example,
    );
    await userEvent.click(
      screen.getByText("Advanced: Prepared feature vector"),
    );
    expect(screen.getByLabelText(/speed last kmh/)).toBeVisible();
    expect(screen.getByLabelText(/speed last kmh/)).toHaveValue(
      String(example.features.past_speed_last_kmh),
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(
      screen.queryByRole("status", { name: "Prediction result" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText(/speed last kmh/)).toHaveValue("");
  });

  it("blocks repeated clicks while pending and exposes safe failures outside Advanced", async () => {
    let complete!: (response: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      complete = resolve;
    });
    const fetcher = vi.fn((url: string) =>
      url.endsWith("/features") ? Promise.resolve(json(contract)) : pending,
    );
    vi.stubGlobal("fetch", fetcher);
    render(<PredictionLab />);
    await userEvent.click(
      await screen.findByRole("button", { name: "Run example prediction" }),
    );
    expect(
      screen.getByRole("button", { name: /Running prediction/ }),
    ).toBeDisabled();
    expect(screen.getByRole("button", { name: "Reset" })).toBeDisabled();
    complete(json({ error: { message: "Saved model unavailable." } }, 503));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Saved model unavailable.",
    );
    expect(
      screen.queryByRole("status", { name: "Prediction result" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Advanced: Prepared feature vector").closest("details"),
    ).not.toHaveAttribute("open");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "Run example prediction" }),
      ).toBeEnabled(),
    );
    expect(
      fetcher.mock.calls.filter(([url]) => url.endsWith("/predict")),
    ).toHaveLength(1);
  });
});
