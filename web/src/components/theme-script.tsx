const themeScript = `
(() => {
  try {
    const storedTheme = localStorage.getItem("chatgpt2api-theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    const theme = storedTheme === "light" || storedTheme === "dark" ? storedTheme : prefersDark ? "dark" : "light";
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.style.colorScheme = theme;
  } catch {
    document.documentElement.classList.remove("dark");
    document.documentElement.style.colorScheme = "light";
  }

  try {
    const storedLocale = localStorage.getItem("chatgpt2api_locale");
    const browserLang = navigator.language?.toLowerCase() || "";
    const locale = (storedLocale === "en" || storedLocale === "fa" || storedLocale === "ar" || storedLocale === "zh")
      ? storedLocale
      : browserLang.startsWith("fa") ? "fa" : browserLang.startsWith("ar") ? "ar" : browserLang.startsWith("zh") ? "zh" : "en";
    const isRtl = locale === "fa" || locale === "ar";
    document.documentElement.lang = locale;
    document.documentElement.dir = isRtl ? "rtl" : "ltr";
    if (isRtl) {
      document.documentElement.classList.add("rtl");
      document.documentElement.classList.remove("ltr");
    } else {
      document.documentElement.classList.add("ltr");
      document.documentElement.classList.remove("rtl");
    }
  } catch {
    document.documentElement.lang = "en";
    document.documentElement.dir = "ltr";
  }
})();
`;

export function ThemeScript() {
  return <script dangerouslySetInnerHTML={{ __html: themeScript }} />;
}
