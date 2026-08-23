/**
 * The transport, over the endpoints the backend actually exposes today.
 *
 * The types come from `src/generated`, which `ledger product` derives from the
 * backend's own Pydantic models -- so a field renamed in Python breaks this
 * file at compile time rather than at a user's desk.
 *
 * The generated *client* is not used yet, and deliberately so. It describes the
 * asynchronous job API the product spec intends (`POST /runs`, then poll
 * `/runs/{id}/result`), while `POST /pipeline/run` is synchronous and blocks
 * for the length of a run. Rather than fake one shape with the other, this
 * adapter speaks what exists and is the single place that changes when the
 * backend grows real jobs.
 */
import type { EvidenceMapping, RunMeta, RunRequest, RunResult } from "./generated/types";
import { apiBase, authHeaders } from "./platform";

export type { EvidenceMapping, RunMeta, RunRequest, RunResult };

/**
 * What `POST /pipeline/run` actually returns.
 *
 * The manifest declares `result: backend.schemas:RunResult`, which is `{meta,
 * mappings}`. The endpoint returns a wider envelope and carries no
 * `response_model`, so nothing on the Python side enforces the declared type
 * and the two drifted. The inner types are right -- `RunMeta` and
 * `EvidenceMapping` are generated from the models the endpoint dumps -- so only
 * the envelope is described here, and it is described honestly rather than
 * asserted to be RunResult.
 */
export interface PipelineRunResponse {
  run: RunMeta;
  summary: Record<string, number> | null;
  exports: Record<string, string>;
  mappings: EvidenceMapping[];
}

export interface Provider {
  name: string;
  label: string;
  ready: boolean;
  note: string;
}

async function send<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(apiBase() + path, {
    method,
    headers: {
      accept: "application/json",
      ...(body ? { "content-type": "application/json" } : {}),
      ...authHeaders(),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const problem = (await res.json()) as { detail?: string };
      if (problem.detail) detail = problem.detail;
    } catch {
      /* a non-JSON error body is still an error; the status carries it */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export const api = {
  health: () => send<{ status: string }>("GET", "/health"),
  providers: () => send<{ ocr: Provider[]; llm: Provider[] }>("GET", "/providers"),
  run: (body: RunRequest) => send<PipelineRunResponse>("POST", "/pipeline/run", body),
  runs: () => send<unknown[]>("GET", "/runs"),
};
