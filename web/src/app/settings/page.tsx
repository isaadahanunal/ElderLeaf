import { Suspense } from "react";
import { SettingsView } from "./SettingsView";

export const metadata = { title: "Settings · ElderLeaf" };

export default function Page() {
  return (
    <Suspense>
      <SettingsView />
    </Suspense>
  );
}
