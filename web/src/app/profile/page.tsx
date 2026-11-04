import { Suspense } from "react";
import { SettingsView } from "../settings/SettingsView";

// older links to /profile open the same screen as /settings
export const metadata = { title: "Settings · ElderLeaf" };

export default function Page() {
  return (
    <Suspense>
      <SettingsView />
    </Suspense>
  );
}
