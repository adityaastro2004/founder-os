/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
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
