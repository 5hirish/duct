const http = require("http");
const fs = require("fs");
const path = require("path");

const port = Number(process.env.PORT || 4317);
const root = path.resolve(__dirname, "..", "..");

const routeMap = {
  "/": "index.html",
};

const mimeTypes = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".xml": "application/xml; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".md": "text/markdown; charset=utf-8",
};

function toSafePath(relativePath) {
  const normalized = path.normalize(relativePath).replace(/^(\.\.(\/|\\|$))+/, "");
  return path.join(root, normalized);
}

function resolvePath(urlPath) {
  const mapped = routeMap[urlPath];
  if (mapped) {
    return toSafePath(mapped);
  }

  const clean = decodeURIComponent(urlPath.replace(/^\/+/, ""));
  if (!clean) {
    return toSafePath("index.html");
  }

  const hasExtension = path.extname(clean) !== "";
  const candidates = hasExtension
    ? [clean]
    : [clean, `${clean}.html`, path.join(clean, "index.html")];

  for (const candidate of candidates) {
    const fullPath = toSafePath(candidate);
    if (fs.existsSync(fullPath)) {
      return fullPath;
    }
  }

  return toSafePath(clean);
}

const server = http.createServer((req, res) => {
  const requestUrl = new URL(req.url, `http://${req.headers.host}`);
  let filePath = resolvePath(requestUrl.pathname);

  if (fs.existsSync(filePath) && fs.statSync(filePath).isDirectory()) {
    filePath = path.join(filePath, "index.html");
  }

  if (!fs.existsSync(filePath)) {
    res.writeHead(404, { "Content-Type": "text/plain; charset=utf-8" });
    res.end("Not found");
    return;
  }

  const ext = path.extname(filePath).toLowerCase();
  const contentType = mimeTypes[ext] || "application/octet-stream";
  res.writeHead(200, { "Content-Type": contentType });
  fs.createReadStream(filePath).pipe(res);
});

server.listen(port, "127.0.0.1", () => {
  console.log(`Serving site test server on http://127.0.0.1:${port}`);
});
