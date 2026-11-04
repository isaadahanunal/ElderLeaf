import { Suspense } from "react";
import { LoginView } from "./LoginView";

export const metadata = { title: "Sign in · ElderLeaf" };

export default function Page() {
  return (
    <Suspense>
      <LoginView />
    </Suspense>
  );
}
