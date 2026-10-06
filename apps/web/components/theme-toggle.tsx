"use client";

import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useT } from "@/components/i18n-provider";
import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const t = useT();
  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label={t("shell.theme")}
      onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")}
    >
      <Sun className="hidden size-4 dark:block" />
      <Moon className="size-4 dark:hidden" />
    </Button>
  );
}
