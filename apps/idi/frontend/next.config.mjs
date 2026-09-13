/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // README / local workflow uses http://127.0.0.1:3000 while `next dev` binds as localhost.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
