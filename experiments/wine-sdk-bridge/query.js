// SPDX-License-Identifier: BSD-3-Clause
// Copyright 2026 Felix Li, with OpenAI Codex assistance.
const fs = require('fs');
const path = require('path');
const { app, BrowserWindow } = require('electron');
const result = {kind:'official-sdk-query', initialized:false};
const native = require(process.env.FELIX_SDK_ADDON);
const api = require('./sdk-loader.js')(process.env.FELIX_SDK_BUNDLE);
api.setInstance(native);
native.MS_API_SetCallback((...args) => { if (args[0] === 3001) api.handlePbCallback(...args); });
const bounded = (promise, ms = 6000) => Promise.race([promise,
  new Promise((_, reject) => setTimeout(() => reject(new Error('bounded SDK timeout')), ms))]);
function progress(stage) {
  result.stage = stage;
  fs.writeFileSync(process.env.FELIX_SDK_RESULT, JSON.stringify(result, null, 2));
}
app.whenReady().then(async () => {
  const owner = new BrowserWindow({show:false, width:320, height:180});
  try {
    progress('helpers-loaded');
    api.setCallConfig('msapi.GetSDKVersion', {timeout:1500});
    if (process.env.FELIX_SDK_INITIALIZE === '1') {
      const lib = path.dirname(process.env.FELIX_SDK_ADDON);
      const state = process.env.FELIX_SDK_STATE;
      const args = {workDirectory:lib, resourceDirectory:path.join(lib,'../resource'),
        installDirectory:process.env.FELIX_SDK_INSTALL,
        hwnd:owner.getNativeWindowHandle().readInt32LE(), fps:30, useWindowlessView:true,
        video:{outputSize:{x:320,y:180},
          format:api.proto.base.VIDEO_PIXEL_FORMAT.PIXEL_FORMAT_NV12,
          colorSpace:api.proto.base.COLOR_SPACE.COLOR_SPACE_BT709,
          colorTransfer:api.proto.base.COLOR_TRANSFER.COLOR_TRANSFER_BT709},
        audio:{sampleRate:48000,channels:2},
        administrator:false, addDefaultEffect:false,
        serverDebug:{logFile:path.join(state,'server.log')},
        clientDebug:{logFile:path.join(state,'client.log')}};
      if (process.env.FELIX_SDK_EMPTY_SIGN_INFO === '1') args.signInfo = {};
      if (process.env.FELIX_SDK_CLIENT_PRODUCT === '1') {
        args.signInfo = require('./product-context.js')(process.env.FELIX_SDK_BUNDLE);
        result.clientProductContext = true;
        result.accountIdentifiersProvided = false;
      }
      try {
        progress('initializing');
        result.initializeResponse = await bounded(api.call.msapi.Initialize(args));
        api.setProtosdkSetupState(true);
        result.initialized = native.MS_API_IsInitialized();
        result.serverAlive = native.MS_API_IsServerAlive();
        progress('querying-version');
        result.sdkVersion = await bounded(api.call.msapi.GetSDKVersion({}), 2500);
        if (process.env.FELIX_SDK_PREVIEW_TEST === '1') {
          try {
            const info = {visualId:'felix-sdk-fixture',visualTrack:0,
              defaultTransform:{visible:true,layout:2}};
            progress('rendering-own-fixture');
            await bounded(api.call.image.Create({visualInfo:info,filePath:path.join(state,'fixture-a.bmp')}));
            await new Promise(resolve=>setTimeout(resolve,500));
            result.imageInfo = await bounded(api.call.image.GetImageInfo({visualInfo:info}));
            result.previewSnapshots = [];
            for (const phase of ['a','b']) {
              if (phase==='b') {
                await bounded(api.call.image.SetFile({visualInfo:info,filePath:path.join(state,'fixture-b.bmp')}));
                await new Promise(resolve=>setTimeout(resolve,450));
              }
              const file = path.join(state,`preview-${phase}.png`);
              await bounded(api.call.msapi.PreviewThumbnailSaveAs({viewIndex:0,filePath:file,
                format:api.proto.base.IMAGE_FILE_FORMAT.PNG}),2500);
              if (!fs.existsSync(file) || fs.statSync(file).size < 100) throw new Error('SDK thumbnail file missing');
              result.previewSnapshots.push({phase,bytes:fs.statSync(file).size});
            }
            await bounded(api.call.visual.Destroy({visualInfo:info}));
          } catch (error) { result.previewError = String(error.message); }
        }
      } catch (error) { result.initializeError = String(error.message); }
    }
  } catch (error) { result.error = String(error.message); }
  finally {
    result.nativeInitializedAtCleanup = native.MS_API_IsInitialized();
    result.serverAliveAtCleanup = native.MS_API_IsServerAlive();
    result.complete = true;
    progress('finished');
    // The bounded owner service reclaims its own process group. A general
    // graceful SDK teardown adapter has not yet been implemented.
    console.log(JSON.stringify({initialized:result.initialized, version:result.sdkVersion,
      error:result.error || result.initializeError}));
    owner.destroy();
    app.exit(result.sdkVersion ? 0 : 1);
  }
});
