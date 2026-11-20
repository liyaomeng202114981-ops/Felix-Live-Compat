// SPDX-License-Identifier: BSD-3-Clause
// Copyright 2026 Felix Li, with OpenAI Codex assistance.
// Only load the supplied official addon in its original Windows runtime.
const fs = require('fs');
const result = { kind: 'official-addon-load-probe',
  versions: { node: process.versions.node, electron: process.versions.electron,
    napi: process.versions.napi, modules: process.versions.modules }, loaded: false };
try {
  const sdk = require(process.env.FELIX_SDK_ADDON);
  result.loaded = true;
  result.exports = Object.getOwnPropertyNames(sdk).map(name => ({name, type: typeof sdk[name]}));
  result.initialized = sdk.MS_API_IsInitialized();
  result.serverAlive = sdk.MS_API_IsServerAlive();
  if (process.env.FELIX_SDK_BUNDLE) {
    const api = require('./sdk-loader.js')(process.env.FELIX_SDK_BUNDLE);
    result.helpers = Object.keys(api);
    result.protoKeys = Object.keys(api.proto).slice(0, 25);
    const initialize = api.proto.msapi?.Initialize?.Request;
    result.initializeType = typeof initialize;
    if (initialize) result.initializeFields = Object.keys(initialize);
    const lookup = api.proto.lookupType?.('msapi.Initialize.Request');
    if (lookup) result.initializeSchema = lookup.fieldsArray.map(f => ({name:f.name,type:f.type,required:f.required}));
  }
} catch (error) { result.error = String(error.message); }
result.complete = true;
fs.writeFileSync(process.env.FELIX_SDK_RESULT, JSON.stringify(result, null, 2));
console.log(JSON.stringify({loaded:result.loaded, versions:result.versions}));
process.exit(result.loaded && !result.error ? 0 : 1);
