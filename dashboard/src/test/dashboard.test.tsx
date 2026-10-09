import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import App from "../App";
import { ApiError, query, request, type Contract } from "../api";
import { number, Pagination, State } from "../components";
import { PredictionLab, prepare } from "../pages/Prediction";
import example from "../../../docs/examples/day7_prediction_request.json";

const definitions = Object.keys(example.features).map((name) => ({
  name,
  units: "test-only unit",
  required: true,
  nullable: name.endsWith("_sample_mean") && !name.includes("speed"),
}));
const contract: Contract = {
  schema_version: "ved-speed-1",
  history_seconds: 60,
  forecast_seconds: 60,
  max_sampling_gap_seconds: 2,
  input_kind: "prepared_past_features",
  feature_order: definitions.map((d) => d.name),
  features: definitions,
  null_policy: "preserve",
  scope: "prepared only",
};
const inputExample = Object.fromEntries(
  Object.entries(example.features).map(([k, v]) => [
    k,
    v === null ? "" : String(v),
  ]),
);
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });

describe("API and numeric semantics", () => {
  it("keeps null distinct from zero", () => {
    expect(number(null)).toBe("—");
    expect(number(0)).toBe("0");
    expect(number(1234)).toBe("1,234");
  });
  it("encodes only explicit query filters", () => {
    expect(
      query("/trips", {
        limit: 25,
        offset: 0,
        powertrain: "ICE",
        vehicle_id: "",
        extra: undefined,
      }),
    ).toBe("/trips?limit=25&offset=0&powertrain=ICE");
  });
  it("preserves safe backend validation details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        json(
          {
            error: {
              message: "Invalid prepared features.",
              details: [
                { field: "features", message: "Inconsistent extrema." },
              ],
            },
          },
          422,
        ),
      ),
    );
    await expect(request("/ml/predict")).rejects.toMatchObject({
      message: "Invalid prepared features.",
      details: [{ field: "features", message: "Inconsistent extrema." }],
    });
  });
  it("gives an actionable network error", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new TypeError("fetch failed")),
    );
    await expect(request("/health")).rejects.toBeInstanceOf(ApiError);
  });
  it("rejects non-JSON responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("unreadable")),
    );
    await expect(request("/health")).rejects.toThrow("unreadable");
  });
});

describe("visible states and navigation", () => {
  it("shows loading, error with retry, and empty states", async () => {
    const retry = vi.fn();
    const view = render(<State loading retry={retry} />);
    expect(screen.getByRole("status")).toHaveAccessibleName("Loading API data");
    view.rerender(
      <State loading={false} error="Backend unavailable" retry={retry} />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Retry request" }),
    );
    expect(retry).toHaveBeenCalledOnce();
    view.rerender(<State loading={false} empty retry={retry} />);
    expect(screen.getByText("No matching records")).toBeVisible();
  });
  it("bounds pagination and calls the next offset", async () => {
    const change = vi.fn();
    render(<Pagination total={51} offset={0} limit={25} change={change} />);
    expect(
      screen.getByRole("button", { name: "Previous page" }),
    ).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next page" }));
    expect(change).toHaveBeenCalledWith(25);
  });
  it("routes all five sidebar links and handles API failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          json({ error: { message: "Fixture: no data available." } }, 503),
        ),
    );
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    await screen.findByText("Fixture: no data available.");
    await userEvent.click(
      screen.getByRole("link", { name: "Driving analytics" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Patterns behind the journey.",
      }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("link", { name: "Data quality" }));
    expect(
      await screen.findByRole("heading", { name: "Quality you can trace." }),
    ).toBeVisible();
    await userEvent.click(
      screen.getByRole("link", { name: "ML intelligence" }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "A forecast. With perspective.",
      }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole("link", { name: "Prediction lab" }));
    expect(
      await screen.findByText(/Raw GPS input is not sufficient/),
    ).toBeVisible();
  });
  it("updates server-side filters and resets pagination", async () => {
    const fetcher = vi.fn((url: string, _options?: RequestInit) =>
      Promise.resolve(
        json(
          url.endsWith("/health")
            ? { status: "ok" }
            : { items: [], total: 0, limit: 25, offset: 0 },
        ),
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    render(
      <MemoryRouter initialEntries={["/driving"]}>
        <App />
      </MemoryRouter>,
    );
    await screen.findAllByText("No matching records");
    await userEvent.selectOptions(screen.getByLabelText("Powertrain"), "EV");
    await waitFor(() =>
      expect(fetcher).toHaveBeenCalledWith(
        "/api/v1/trips?limit=25&offset=0&powertrain=EV",
        expect.anything(),
      ),
    );
    await userEvent.type(screen.getByLabelText("Vehicle ID"), "8");
    await waitFor(() =>
      expect(fetcher).toHaveBeenCalledWith(
        "/api/v1/trips?limit=25&offset=0&powertrain=EV&vehicle_id=8",
        expect.anything(),
      ),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Reset filters" }),
    );
    expect(screen.getByLabelText("Vehicle ID")).toHaveValue("");
  });
  it("opens and closes the mobile navigation", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          json({ error: { message: "Fixture unavailable" } }, 503),
        ),
    );
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );
    const button = screen.getByRole("button", { name: "Open navigation" });
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(screen.getByRole("link", { name: "Prediction lab" }));
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});

describe("exact prepared inference contract", () => {
  it("serializes all 31 features and preserves nullable measured semantics", () => {
    const payload = prepare(contract, inputExample);
    expect(payload).toEqual(example);
    expect(Object.keys(payload.features)).toHaveLength(31);
    expect(Object.keys(payload.features)).not.toContain("vehicle_id");
  });
  it("rejects missing mandatory features and nonfinite values", () => {
    expect(() => prepare(contract, {})).toThrow("Enter");
    expect(() =>
      prepare(contract, { ...inputExample, past_speed_last_kmh: "Infinity" }),
    ).toThrow("finite number");
  });
  it("enforces declared bounds", () => {
    const bounded = {
      ...contract,
      features: contract.features.map((f) =>
        f.name === "past_gap_max_s" ? { ...f, le: 2 } : f,
      ),
    };
    expect(() =>
      prepare(bounded, { ...inputExample, past_gap_max_s: "3" }),
    ).toThrow("allowed range");
  });
  it("rejects incompatible feature schema", () => {
    expect(() =>
      prepare({ ...contract, feature_order: ["wrong"] }, inputExample),
    ).toThrow("incompatible");
  });
  it("requires null mean and zero availability together", () => {
    expect(() =>
      prepare(contract, {
        ...inputExample,
        past_engine_rpm_sample_mean: "",
        past_engine_rpm_observed_fraction: "1",
      }),
    ).toThrow("observed fraction");
  });
  it("does not call inference for an incomplete form", async () => {
    const fetcher = vi.fn().mockResolvedValue(json(contract));
    vi.stubGlobal("fetch", fetcher);
    render(<PredictionLab />);
    await screen.findByLabelText(/speed last kmh/);
    await userEvent.click(
      screen.getByText("Advanced: Prepared feature vector"),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Predict mean speed" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter");
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
  it("posts the verified vector and shows only returned predictions", async () => {
    const fetcher = vi.fn((url: string, _options?: RequestInit) =>
      Promise.resolve(
        json(
          url.endsWith("/features")
            ? contract
            : {
                predicted_mean_speed_kmh: 36.61748855856695,
                forecast_seconds: 60,
                history_seconds: 60,
                units: "km/h",
                model_id: "test-response",
                warning: "Prepared inputs required.",
              },
        ),
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<PredictionLab />);
    await screen.findByLabelText(/speed last kmh/);
    await userEvent.click(
      screen.getByText("Advanced: Prepared feature vector"),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Load verified example" }),
    );
    await userEvent.click(
      screen.getByRole("button", { name: "Predict mean speed" }),
    );
    expect(
      await screen.findByRole("status", { name: "Prediction result" }),
    ).toHaveTextContent("36.62");
    const options = fetcher.mock.calls.find((call) =>
      call[0].endsWith("/predict"),
    )![1] as RequestInit;
    expect(JSON.parse(options.body as string)).toEqual(example);
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(
      screen.queryByRole("status", { name: "Prediction result" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText(/speed last kmh/)).toHaveValue("");
  });
});
