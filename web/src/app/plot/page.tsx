import { Suspense } from "react";
import { PlotView } from "./PlotView";

export default function Page() {
  return (
    <Suspense>
      <PlotView />
    </Suspense>
  );
}
