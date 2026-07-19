/** @type {import('next').NextConfig} */

// Baseline security headers for every response. `frame-ancestors 'none'` +
// X-Frame-Options block clickjacking; nosniff blocks MIME confusion; HSTS pins
// HTTPS. Only `frame-ancestors` is used from CSP so the app's own scripts/styles
// (Next.js, Clerk) are not restricted — a full CSP would need per-source tuning.
const securityHeaders = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  {
    key: "Strict-Transport-Security",
    value: "max-age=63072000; includeSubDomains; preload",
  },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=()",
  },
];

const nextConfig = {
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async rewrites() {
    // eslint-disable-next-line no-undef
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        // Proxy all /api/* requests to the FastAPI backend
        source: "/api/:path*",
        destination: `${api}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
