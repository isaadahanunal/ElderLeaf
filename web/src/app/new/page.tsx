import { Suspense } from "react";
import { NewPlotView } from "./NewPlotView";

export default function Page() {
  return (
    <Suspense>
      <NewPlotView />
    </Suspense>
  );
}
