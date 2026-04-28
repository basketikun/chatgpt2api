"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { fetchSetupStatus } from "@/lib/api";
import { getDefaultRouteForRole, getStoredAuthSession } from "@/store/auth";

export default function HomePage() {
  const router = useRouter();

  useEffect(() => {
    let active = true;

    const redirect = async () => {
      const session = await getStoredAuthSession();
      if (!active) {
        return;
      }
      if (session) {
        router.replace(getDefaultRouteForRole(session.role));
        return;
      }
      try {
        const status = await fetchSetupStatus();
        router.replace(status.requires_setup ? "/setup" : "/login");
      } catch {
        router.replace("/login");
      }
    };

    void redirect();
    return () => {
      active = false;
    };
  }, [router]);

  return null;
}
