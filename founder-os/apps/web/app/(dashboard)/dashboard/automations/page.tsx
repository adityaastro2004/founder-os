import { redirect } from "next/navigation";

// The Automations and Workflows tabs were merged. The functional page lives at
// /dashboard/workflows (labelled "Automations"); keep the old URL working for
// existing tabs and bookmarks.
export default function AutomationsRedirect() {
  redirect("/dashboard/workflows");
}
