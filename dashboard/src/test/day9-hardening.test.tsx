import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import App from "../App";
import { ApiError, request, useApi } from "../api";
import { Driving } from "../pages/Analytics";
import { Trends } from "../components";

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });
const empty = { items: [], total: 0, limit: 25, offset: 0 };

it("explains an empty gateway error when the backend is unavailable", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(new Response("", { status: 500 })),
      ),
  );
  await expect(request("/health")).rejects.toThrow(
    "Start the FleetPulse backend and retry",
  );
});

it("unchanged query rerenders do not issue additional API requests", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(json({ value: 1 })));
  vi.stubGlobal("fetch", fetcher);
  const hook = renderHook(() => useApi<{ value: number }>("/stable"));
  await waitFor(() => expect(hook.result.current.data?.value).toBe(1));
  hook.rerender();
  hook.rerender();
  expect(fetcher).toHaveBeenCalledTimes(1);
});

it("makes no request for an explicitly paused query", async () => {
  const fetcher = vi.fn();
  vi.stubGlobal("fetch", fetcher);
  const hook = renderHook(() => useApi(null));
  expect(hook.result.current.loading).toBe(false);
  expect(fetcher).not.toHaveBeenCalled();
});

it("invalid vehicle filters do not trigger an unfiltered fleet request", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(json(empty)));
  vi.stubGlobal("fetch", fetcher);
  render(<Driving />);
  await screen.findAllByText("No matching records");
  await userEvent.type(screen.getByLabelText("Vehicle ID"), "8");
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/trips?limit=25&offset=0&vehicle_id=8",
      expect.anything(),
    ),
  );
  const before = fetcher.mock.calls.length;
  await userEvent.type(screen.getByLabelText("Vehicle ID"), "x");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "nonnegative integer",
  );
  expect(fetcher.mock.calls.length).toBe(before);
});

it("inverted dates pause requests rather than loading all historical cohorts", async () => {
  const fetcher = vi
    .fn()
    .mockImplementation(() => Promise.resolve(json(empty)));
  vi.stubGlobal("fetch", fetcher);
  render(<Trends />);
  await screen.findByText("No matching records");
  const { fireEvent } = await import("@testing-library/react");
  fireEvent.change(screen.getByLabelText("From"), {
    target: { value: "2018-01-01" },
  });
  await waitFor(() =>
    expect(fetcher).toHaveBeenCalledWith(
      "/api/v1/trends/monthly?limit=100&offset=0&start_date=2018-01-01",
      expect.anything(),
    ),
  );
  const before = fetcher.mock.calls.length;
  fireEvent.change(screen.getByLabelText("To"), {
    target: { value: "2017-01-01" },
  });
  expect(await screen.findByRole("alert")).toHaveTextContent("Start date");
  expect(fetcher.mock.calls.length).toBe(before);
});

it("recovers the connection badge after a backend restart without a page reload", async () => {
  let healthCalls = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn((path: string) =>
      Promise.resolve(
        path.endsWith("/health")
          ? json(
              ++healthCalls === 1
                ? { error: { message: "Unavailable" } }
                : { status: "ok" },
              healthCalls === 1 ? 503 : 200,
            )
          : json({ error: { message: "Fixture unavailable" } }, 503),
      ),
    ),
  );
  render(
    <MemoryRouter>
      <App />
    </MemoryRouter>,
  );
  await screen.findByText("API unavailable");
  await userEvent.click(
    screen.getByRole("button", { name: "Retry API connection" }),
  );
  expect(await screen.findByText("Local API connected")).toBeVisible();
  expect(healthCalls).toBe(2);
});

it("returns a safe ApiError when an error response is valid JSON null", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(() => Promise.resolve(json(null, 502))),
  );
  await expect(request("/health")).rejects.toBeInstanceOf(ApiError);
  await expect(request("/health")).rejects.toThrow("Request failed (502)");
});

it("aborts obsolete requests and cannot show their late response", async () => {
  const pending: { signal: AbortSignal; resolve: (value: Response) => void }[] =
    [];
  vi.stubGlobal(
    "fetch",
    vi.fn(
      (_path: string, options: RequestInit) =>
        new Promise<Response>((resolve) =>
          pending.push({ signal: options.signal as AbortSignal, resolve }),
        ),
    ),
  );
  const hook = renderHook(({ path }) => useApi<{ value: number }>(path), {
    initialProps: { path: "/first" },
  });
  hook.rerender({ path: "/second" });
  expect(pending[0].signal.aborted).toBe(true);
  pending[1].resolve(json({ value: 2 }));
  await waitFor(() => expect(hook.result.current.data?.value).toBe(2));
  pending[0].resolve(json({ value: 1 }));
  await new Promise((resolve) => setTimeout(resolve, 20));
  expect(hook.result.current.data?.value).toBe(2);
});
