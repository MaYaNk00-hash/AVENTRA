"use client";

import React, { useEffect, useState, Suspense } from "react";
import AgentRuntime from "./agent/page";
import ConsolePage from "./console/page";

function RootWorkspace() {
  const [activeMode, setActiveMode] = useState<"agent" | "console">("agent");

  useEffect(() => {
    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      if (params.has("tab")) {
        setActiveMode("console");
      } else {
        setActiveMode("agent");
      }
    }
  }, []);

  return activeMode === "console" ? <ConsolePage /> : <AgentRuntime />;
}

export default function Home() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen w-screen items-center justify-center bg-[#090B10] text-[#E6EDF3]">
          Loading AVENTRA...
        </div>
      }
    >
      <RootWorkspace />
    </Suspense>
  );
}
