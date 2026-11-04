import { Suspense } from "react";
import { PlotsView } from "./PlotsView";

export default function Page() {
  return (
    <Suspense>
      <PlotsView />
    </Suspense>
  );
}
