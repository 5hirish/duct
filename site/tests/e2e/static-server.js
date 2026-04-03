const http = require("http");
const fs = require("fs");
const path = require("path");

const port = Number(process.env.PORT || 4317);
const root = path.resolve(__dirname, "..", "..");

const routeMap = {
  "/": "index.html",
  "/for-product-intelligence": "for-product-intelligence.html",
  "/for-organic-growth": "for-organic-growth.html",
  "/for-paid-ads": "for-paid-ads.html",
  "/blog": "blog/index.html",
  "/blog/post": "blog/post.html",
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

function resolvePath(urlPath) {
  if (routeMap[urlPath]) {
    return path.join(root, routeMap[urlPath]);
  }

  const clean = decodeURIComponent(urlPath.replace(/^\/+/, ""));
  if (!clean) {
    return path.join(root, "index.html");
  }

  return path.join(root, clean);
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
