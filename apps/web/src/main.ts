/**
 * The VeriTrade client, in the form every platform runs.
 *
 * It is deliberately thin: pick an economy and a pillar, run, read the
 * mappings. The three slots the tenant must still design by hand -- the
 * coverage matrix, the confidence view and the review queue -- are named in
 * `bench/out/product/slots.md` and are not faked here. A screen that looks
 * finished is how a gap stops being visible.
 */
import "./style.css";
import { api, type EvidenceMapping, type PipelineRunResponse } from "./api";
import type { Economy, RunMeta } from "./generated/types";
import { apiBase, platform } from "./platform";

// Not a hand-kept list: the enum is generated from the backend's own Economy,
// so an economy added in Python appears here and nowhere else has to change.
const ECONOMIES: Economy[] = ["SG", "AU", "MY", "CN", "IN", "MN", "TH", "VN", "ID", "KZ", "LA", "RU"];

const app = document.querySelector<HTMLDivElement>("#app")!;

function h(html: string): string {
  return html;
}

function escape(text: string): string {
  const d = document.createElement("div");
  d.textContent = text;
  return d.innerHTML;
}

function confidencePill(score: number): string {
  // The thresholds the pipeline itself publishes: accept / review / set aside.
  const cls = score >= 0.85 ? "ok" : score >= 0.6 ? "warn" : "bad";
  return `<span class="pill ${cls}">${score.toFixed(2)}</span>`;
}

function shell(): void {
  app.innerHTML = h(`
    <header>
      <h1>VeriTrade</h1>
      <span class="badge" id="platform"></span>
      <span class="badge" id="health">checking…</span>
    </header>
    <p class="sub">
      Finds digital-trade law on official portals, reads it, and maps each provision to a
      UN ESCAP RDTII 2.1 indicator with a citation you can check.
    </p>

    <div class="panel">
      <div class="row">
        <div>
          <label for="economy">Economy</label>
          <select id="economy">${ECONOMIES.map((e) => `<option value="${e}">${e}</option>`).join("")}</select>
        </div>
        <div>
          <label for="pillar">Pillar</label>
          <select id="pillar">
            <option value="6">6 — Cross-border data rules</option>
            <option value="7">7 — Data protection &amp; cybersecurity</option>
          </select>
        </div>
        <div>
          <label for="corpus">Corpus</label>
          <select id="corpus">
            <option value="samples">Bundled offline examples</option>
            <option value="live">Live search of official portals</option>
          </select>
        </div>
        <button class="primary" id="run">Run analysis</button>
      </div>
      <p class="sub" id="status" style="margin:14px 0 0"></p>
    </div>

    <div id="results"></div>
  `);

  document.querySelector<HTMLSpanElement>("#platform")!.textContent =
    `${platform()} · ${apiBase()}`;
  document.querySelector<HTMLButtonElement>("#run")!.addEventListener("click", run);
}

async function checkHealth(): Promise<void> {
  const el = document.querySelector<HTMLSpanElement>("#health")!;
  try {
    const { status } = await api.health();
    el.textContent = `api ${status}`;
  } catch (err) {
    el.textContent = "api unreachable";
    el.classList.add("err");
    setStatus(
      `Cannot reach the API at ${apiBase()} — ${(err as Error).message}. ` +
        `Start it with: uvicorn backend.main:app --port 8000`,
      true,
    );
  }
}

function setStatus(text: string, isError = false): void {
  const el = document.querySelector<HTMLParagraphElement>("#status")!;
  el.textContent = text;
  el.classList.toggle("err", isError);
}

async function run(): Promise<void> {
  const button = document.querySelector<HTMLButtonElement>("#run")!;
  const economy = document.querySelector<HTMLSelectElement>("#economy")!.value;
  const pillar = Number(document.querySelector<HTMLSelectElement>("#pillar")!.value);
  const useSamples = document.querySelector<HTMLSelectElement>("#corpus")!.value === "samples";

  button.disabled = true;
  setStatus(
    useSamples
      ? "Running against the bundled corpus…"
      : "Searching the official portals — a live run takes several minutes…",
  );
  const started = performance.now();
  try {
    const result = await api.run({
      economy: economy as Economy,
      pillars: [pillar],
      use_samples: useSamples,
    });
    const seconds = ((performance.now() - started) / 1000).toFixed(1);
    setStatus(`Finished in ${seconds}s.`);
    render(result);
  } catch (err) {
    setStatus((err as Error).message, true);
  } finally {
    button.disabled = false;
  }
}

function render(result: PipelineRunResponse): void {
  const meta: RunMeta = result.run;
  const mappings: EvidenceMapping[] = result.mappings ?? [];
  const high = mappings.filter((m) => m.confidence_score >= 0.85).length;
  const review = mappings.filter((m) => m.confidence_score >= 0.6 && m.confidence_score < 0.85).length;

  const stat = (value: unknown, label: string): string =>
    `<div class="stat"><b>${escape(String(value ?? "—"))}</b><span>${label}</span></div>`;

  document.querySelector<HTMLDivElement>("#results")!.innerHTML = h(`
    <div class="panel">
      <div class="stats">
        ${stat(meta.docs_discovered, "documents")}
        ${stat(meta.provisions_extracted, "provisions")}
        ${stat(mappings.length, "mappings")}
        ${stat(high, "high confidence")}
        ${stat(review, "needs review")}
        ${stat(meta.llm_provider, "grader")}
      </div>
    </div>
    <div class="panel">
      <div class="scroll">
        <table>
          <thead>
            <tr><th>Indicator</th><th>Law</th><th>Section</th><th>Verbatim snippet</th><th>Confidence</th></tr>
          </thead>
          <tbody>
            ${
              mappings.length
                ? mappings
                    .map(
                      (m) => `<tr>
                        <td><b>${escape(m.indicator_id)}</b></td>
                        <td>${escape(m.law_name)}<br /><a href="${escape(m.source_url)}" target="_blank" rel="noreferrer noopener">source</a></td>
                        <td>${escape(m.article_section)}</td>
                        <td class="snippet">${escape((m.verbatim_snippet || "").slice(0, 260))}…</td>
                        <td>${confidencePill(m.confidence_score)}</td>
                      </tr>`,
                    )
                    .join("")
                : `<tr><td colspan="5">No provision met an indicator's legal test in this run.</td></tr>`
            }
          </tbody>
        </table>
      </div>
    </div>
  `);
}

shell();
void checkHealth();
