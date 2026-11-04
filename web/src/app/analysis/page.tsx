import { Suspense } from "react";
import { AnalysisView } from "./AnalysisView";

export default function Page() {
  return (
    <Suspense>
      <AnalysisView />
    </Suspense>
  );
}
