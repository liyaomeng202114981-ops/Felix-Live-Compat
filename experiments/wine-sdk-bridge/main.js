// SPDX-License-Identifier: BSD-3-Clause
// Copyright 2026 Felix Li, with OpenAI Codex assistance.
const {app, BrowserWindow, ipcMain} = require('electron');
const fs = require('fs');
const path = require('path');
const {execFile} = require('child_process');
const config = JSON.parse(fs.readFileSync(process.env.FELIX_SDK_BRIDGE_CONFIG, 'utf8'));
app.setName('Felix Native SDK Preview Demo');
let query;
app.on('before-quit',()=>{if(query)query.kill('SIGTERM')});
app.on('window-all-closed', () => app.quit());
app.whenReady().then(async () => {
  const win = new BrowserWindow({width:1040,height:780,minWidth:700,minHeight:620,
    title:'Felix 原生 SDK 预览原型（快照）',backgroundColor:'#151a24',autoHideMenuBar:true,
    webPreferences:{preload:path.join(__dirname,'preload.js'),contextIsolation:true,nodeIntegration:false}});
  let pending = false;
  function request(event, preview) {
    if (event.sender !== win.webContents || pending) throw new Error('Query unavailable');
    pending = true;
    const directory = preview ? config.previewCase : config.case;
    return new Promise(resolve => { query=execFile('/usr/bin/python3', ['-B',config.runner,
      '--root',config.root,'--case',directory,'--result',preview?'ui-preview.json':'ui-status.json',
      preview?'--preview-test':'--probe-only'],
      {timeout:25000,maxBuffer:65536}, (error, stdout) => {
        pending = false;
        query = undefined;
        if (error) return resolve({loaded:false,error:'独立查询失败，请查看本机诊断记录'});
        try {
          const result=JSON.parse(stdout);
          if (preview && result.previewSnapshots?.length===2) {
            result.images=['a','b'].map(phase=>{
              const data=fs.readFileSync(path.join(directory,'sdk-state',`preview-${phase}.png`));
              if(data.length>1048576)throw new Error('Oversized test snapshot');
              return {phase,url:'data:image/png;base64,'+data.toString('base64')};
            });
          }
          resolve(result);
        } catch (_) { resolve({loaded:false,error:'查询结果格式异常'}); }
      }); });
  }
  ipcMain.handle('sdk-status', event=>request(event,false));
  ipcMain.handle('sdk-preview', event=>request(event,true));
  win.webContents.setWindowOpenHandler(()=>({action:'deny'}));
  win.webContents.on('will-navigate', event=>event.preventDefault());
  await win.loadFile(path.join(__dirname,'index.html'));
  if (process.argv.includes('--self-test')) {
    const result = await win.webContents.executeJavaScript('window.bridgeDone');
    const imageReady=await win.webContents.executeJavaScript('document.getElementById("preview").decode().then(()=>document.getElementById("preview").naturalWidth)');
    const passed = result.initialized === true && result.serverAlive === true && result.complete === true &&
      result.sdkVersion?.version==='13.3.5.7' && result.images?.length===2 && imageReady===320;
    const out = process.env.FELIX_DEMO_OUTPUT;
    fs.writeFileSync(path.join(out,'linux-ui-check.json'),JSON.stringify({passed,result},null,2));
    await new Promise(resolve=>setTimeout(resolve,150));
    fs.writeFileSync(path.join(out,'sdk-bridge.png'),(await win.webContents.capturePage()).toPNG());
    console.log(JSON.stringify({passed,initialized:result.initialized,sdkVersion:result.sdkVersion,serverAlive:result.serverAlive}));
    app.exit(passed?0:1);
  }
});
