"use strict";
/**
 * Cursor MCP: ensure .qmd/ exists, set INDEX_PATH, then exec qmd mcp (stdio stays on this process tree).
 * Args: [node, thisScript, workspaceFolder?] — workspaceFolder from mcp.json ${workspaceFolder} when cwd is wrong.
 */
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const root = process.argv[2] ? path.resolve(process.argv[2]) : process.cwd();
const qmdDir = path.join(root, ".qmd");
fs.mkdirSync(qmdDir, { recursive: true });
process.env.INDEX_PATH = path.join(qmdDir, "index.sqlite");

const qmdJs = path.join(root, "node_modules", "@tobilu", "qmd", "dist", "cli", "qmd.js");
if (!fs.existsSync(qmdJs)) {
  console.error(
    "qmd CLI missing. Run: npm install   (expected " + qmdJs + ")",
  );
  process.exit(1);
}

execFileSync(process.execPath, [qmdJs, "mcp"], { stdio: "inherit", env: process.env });
