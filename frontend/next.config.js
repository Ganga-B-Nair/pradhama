/**
 * The browser only ever talks to this origin: /api/* is proxied to FastAPI.
 * Same-origin keeps the session cookie simple and lets a phone that opens the
 * QR link on the LAN reach the API too (it can't reach the laptop's localhost).
 */
const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

module.exports = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND_URL}/api/:path*` }];
  },
};
