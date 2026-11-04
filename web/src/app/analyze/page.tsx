import { Suspense } from "react";
import { CaptureView } from "./CaptureView";

export default function Page() {
  return (
    <Suspense>
      <CaptureView />
    </Suspense>
  );
}
