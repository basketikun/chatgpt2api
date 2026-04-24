const webConfig = {
    // Same-origin by default so Next.js route handlers act as the API entrypoint.
    apiUrl: process.env.NEXT_PUBLIC_API_BASE_URL || "",
    appVersion: process.env.NEXT_PUBLIC_APP_VERSION || "0.0.0",
};

export default webConfig;
