/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const api = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    // Proxy media through Next so <video>/<img> tags can use relative URLs.
    return [{ source: "/media/:path*", destination: `${api}/media/:path*` }];
  },
};

export default nextConfig;
