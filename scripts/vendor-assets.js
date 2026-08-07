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
  // Budget "Flow" view's Sankey diagram — standalone build, no extra files.
  ["node_modules/echarts/dist/echarts.min.js", "echarts/echarts.min.js"],
  // Display face for branding/headings — latin subset only, two weights.
  ["node_modules/@fontsource/fraunces/files/fraunces-latin-500-normal.woff2", "fraunces/fraunces-500.woff2"],
  ["node_modules/@fontsource/fraunces/files/fraunces-latin-700-normal.woff2", "fraunces/fraunces-700.woff2"],
];

for (const [src, dest] of FILES) {
  const srcPath = path.join(ROOT, src);
  const destPath = path.join(ROOT, "static", "vendor", dest);
  fs.mkdirSync(path.dirname(destPath), { recursive: true });
  fs.copyFileSync(srcPath, destPath);
  console.log(`vendored ${dest}`);
}

// Bootstrap Icons ships ~2000 individual SVGs. The UI only needs a couple
// dozen, so instead of vendoring the whole set (or a webfont), pull just
// these into one <symbol>-per-icon sprite, referenced from templates as
// {% include "_icon.html" with name="pencil-square" %} -> <use href="#icon-pencil-square">.
// Add a name here (matching a file under node_modules/bootstrap-icons/icons/)
// whenever a template needs a new glyph.
const ICON_NAMES = [
  // nav / subnav
  "speedometer2", "wallet2", "list-task", "calendar3", "kanban", "sticky", "gear",
  "graph-up", "bank2", "piggy-bank", "clock-history", "diagram-3",
  // theme toggle
  "sun-fill", "moon-fill", "circle-half",
  // actions
  "pencil-square", "trash3", "plus-lg", "check-lg", "arrow-counterclockwise",
  // status badges
  "check-circle-fill", "exclamation-triangle-fill", "dash-circle", "arrow-repeat",
  "arrow-up-short", "arrow-down-short", "arrow-left-short", "arrow-left-right", "calendar-event", "flag-fill",
];

const symbols = ICON_NAMES.map((name) => {
  const svgPath = path.join(ROOT, "node_modules", "bootstrap-icons", "icons", `${name}.svg`);
  const svg = fs.readFileSync(svgPath, "utf8");
  const viewBox = svg.match(/viewBox="([^"]+)"/)[1];
  const inner = svg.replace(/^<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");
  return `  <symbol id="icon-${name}" viewBox="${viewBox}">${inner}</symbol>`;
}).join("\n");

const spritePath = path.join(ROOT, "static", "vendor", "bootstrap-icons", "sprite.svg");
fs.mkdirSync(path.dirname(spritePath), { recursive: true });
fs.writeFileSync(
  spritePath,
  `<svg xmlns="http://www.w3.org/2000/svg" style="display:none">\n${symbols}\n</svg>\n`
);
console.log(`vendored bootstrap-icons/sprite.svg (${ICON_NAMES.length} icons)`);
