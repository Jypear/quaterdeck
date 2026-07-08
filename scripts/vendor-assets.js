#!/usr/bin/env node
// Copies the built Bootstrap/HTMX/Alpine files from node_modules into
// static/vendor/, so the app can serve them locally without a CDN or a
// Node build step in production (see Dockerfile — it never runs npm).
// Run after `npm install` (also via `npm run vendor`) whenever versions
// change; the copied output is committed to the repo.

const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");

const FILES = [
  ["node_modules/bootstrap/dist/css/bootstrap.min.css", "bootstrap/bootstrap.min.css"],
  ["node_modules/bootstrap/dist/css/bootstrap.min.css.map", "bootstrap/bootstrap.min.css.map"],
  ["node_modules/bootstrap/dist/js/bootstrap.bundle.min.js", "bootstrap/bootstrap.bundle.min.js"],
  ["node_modules/bootstrap/dist/js/bootstrap.bundle.min.js.map", "bootstrap/bootstrap.bundle.min.js.map"],
  ["node_modules/htmx.org/dist/htmx.min.js", "htmx/htmx.min.js"],
  ["node_modules/alpinejs/dist/cdn.min.js", "alpinejs/alpine.min.js"],
];

for (const [src, dest] of FILES) {
  const srcPath = path.join(ROOT, src);
  const destPath = path.join(ROOT, "static", "vendor", dest);
  fs.mkdirSync(path.dirname(destPath), { recursive: true });
  fs.copyFileSync(srcPath, destPath);
  console.log(`vendored ${dest}`);
}
