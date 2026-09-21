// Team-tab research, tracked per company.
//
// A research pass runs about a minute and outlives the card that started
// it: switching company or tab re-renders the card. So the in-flight set
// lives here, keyed by company id, instead of in one card's local state —
// that local flag used to leave the next company's card spinning, and the
// late result was drawn over whichever company was on screen by then.
import { reactive } from "vue";
import { api } from "./api.js";

export const researchingCompanies = reactive(new Set());

/**
 * Run the web research for one company's team. Returns the dossier, or null
 * when a pass for that company is already running (the button is disabled
 * then, so this only guards a double click).
 */
export async function researchTeam(companyId, request = api.deepSearchFounder) {
  if (!companyId || researchingCompanies.has(companyId)) return null;
  researchingCompanies.add(companyId);
  try {
    return await request(companyId);
  } finally {
    researchingCompanies.delete(companyId);
  }
}
