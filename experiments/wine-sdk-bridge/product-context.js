// SPDX-License-Identifier: BSD-3-Clause
// Copyright 2026 Felix Li, with OpenAI Codex assistance.
// Reuse installed-client product configuration verbatim, never print or vendor it.
const fs = require('fs');
module.exports = function clientProductContext(bundle) {
  const text = fs.readFileSync(bundle, 'utf8');
  const map = /SIGN_INFO_LICENSE=\{([^}]+)\}/.exec(text);
  if (!map) throw new Error('Unsupported client product configuration');
  const license = /(?:^|,)2079:["']([^"']+)["']/.exec(map[1]);
  if (!license || !text.includes('aid:"2079"')) throw new Error('Product configuration does not match client');
  return {aid:'2079', license:license[1]};
};
