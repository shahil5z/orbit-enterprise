// Phase 1 shell: renders API health and the current recommendations. The full UI is Phase 2.
import { OrbitClient } from "./api/client.js";

const client = new OrbitClient();

function el(tag: string, text: string, className?: string): HTMLElement {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

async function render(root: HTMLElement): Promise<void> {
  try {
    const health = await client.health();
    root.append(el("p", `API ${health.status}, database ${health.database.status}`, "status"));
    const { recommendations } = await client.recommendations();
    for (const r of recommendations) {
      const card = el("article", "", `card priority-${r.priority.toLowerCase()}`);
      card.append(el("h3", `${r.entity_id} (${r.priority})`), el("p", r.observation), el("p", r.recommendation));
      root.append(card);
    }
  } catch (err) {
    root.append(el("p", `API unavailable: ${(err as Error).message}`, "error"));
  }
}

const mount = document.getElementById("app");
if (mount) void render(mount);
