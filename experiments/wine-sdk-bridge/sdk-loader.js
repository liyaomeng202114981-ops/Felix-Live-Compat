// SPDX-License-Identifier: BSD-3-Clause
// Copyright 2026 Felix Li, with OpenAI Codex assistance.
// Load only selected SDK helpers from a user-supplied, pinned official bundle.
// The official application entry points are deliberately NOT executed.
const fs = require('fs');
const path = require('path');
const Module = require('module');
module.exports = function loadSdkHelpers(filename) {
  const entry = '__webpack_require__(__webpack_require__.s=49034);var __webpack_exports__=__webpack_require__(__webpack_require__.s=29761);module.exports=__webpack_exports__';
  const text = fs.readFileSync(filename, 'utf8');
  if (text.split(entry).length !== 2) throw new Error('Unsupported client bundle entry; refuse to run');
  const host = new Module(filename, module);
  host.filename = filename;
  host.paths = Module._nodeModulePaths(path.dirname(filename));
  host._compile(text.replace(entry, 'module.exports=__webpack_require__'), filename);
  return host.exports(33137);
};
