// SPDX-License-Identifier: BSD-3-Clause
// Copyright 2026 Felix Li, with OpenAI Codex assistance.
const { app, BrowserWindow, ipcMain } = require('electron');
const { spawn } = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const check = process.argv.includes('--self-test');
app.setName('Felix Native Preview Demo');
let worker, win, timer, paused = false, closing = false, busy = false, latest;
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
function cleanup() {
  closing = true;
  clearInterval(timer);
  if (worker && worker.exitCode === null) {
    worker.kill('SIGCONT');
    worker.kill('SIGTERM');
  }
}
app.on('before-quit', cleanup);
app.on('window-all-closed', () => app.quit());
app.whenReady().then(async () => {
  win = new BrowserWindow({
    width: 1060, height: 740, minWidth: 620, minHeight: 480,
    title: 'Felix 原生 Linux 预览演示（独立测试）',
    backgroundColor: '#151a24', autoHideMenuBar: true,
    webPreferences: { preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true, nodeIntegration: false, backgroundThrottling: false }
  });
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  win.webContents.on('will-navigate', event => event.preventDefault());
  await win.loadFile(path.join(__dirname, 'index.html'));
  worker = spawn('/usr/bin/python3', ['-B', path.join(__dirname, 'producer.py')],
    { stdio: ['ignore', 'pipe', 'inherit'] });
  let buffered = Buffer.alloc(0);
  const frameSize = 16 + 320 * 180 * 4;
  worker.stdout.on('data', chunk => {
    buffered = Buffer.concat([buffered, chunk]);
    while (buffered.length >= frameSize) {
      if (buffered.toString('ascii', 0, 4) !== 'FLX1') { app.quit(); return; }
      latest = { sequence: buffered.readUInt32LE(4),
        pixels: Buffer.from(buffered.subarray(16, frameSize)) };
      buffered = buffered.subarray(frameSize);
    }
  });
  worker.on('error', error => { console.error(error.message); app.quit(); });
  worker.on('exit', () => {
    if (!closing && !win.isDestroyed()) win.webContents.send('backend-state', 'stopped');
  });
  ipcMain.on('frame-ack', event => { if (event.sender === win.webContents) busy = false; });
  ipcMain.on('toggle-pause', event => {
    if (event.sender !== win.webContents || worker.exitCode !== null) return;
    paused = !paused;
    worker.kill(paused ? 'SIGSTOP' : 'SIGCONT');
    win.webContents.send('backend-state', paused ? 'paused' : 'running');
  });
  timer = setInterval(() => {
    if (!busy && latest && !win.isDestroyed()) {
      busy = true;
      win.webContents.send('frame', latest);
      latest = undefined;
    }
  }, 16);
  console.log(JSON.stringify({ ready: true, electron: process.versions.electron,
    backend: 'separate Linux Python synthetic frame producer', workerPid: worker.pid }));
  if (check) {
    try {
      const stats = () => win.webContents.executeJavaScript('({...window.demoStats})');
      await wait(1200);
      const initial = await stats();
      win.setSize(780, 560); await wait(300);
      win.setSize(1120, 780); await wait(300);
      const resized = await stats();
      await win.webContents.executeJavaScript('document.getElementById("pause").click()');
      await wait(250); const stopped = await stats();
      await wait(600); const duringPause = await stats();
      await win.webContents.executeJavaScript('document.getElementById("pause").click()');
      await wait(450); const resumed = await stats();
      const passed = initial.sequence > 5 && resized.sequence > initial.sequence &&
        duringPause.sequence === stopped.sequence && duringPause.ticks > stopped.ticks &&
        resumed.sequence > duringPause.sequence && resumed.backend === 'running';
      const result = { passed, initial, resized, stopped, duringPause, resumed,
        note: 'functional synthetic-frame checks; not a companion performance comparison' };
      const output = process.env.FELIX_DEMO_OUTPUT;
      if (output) {
        fs.writeFileSync(path.join(output, 'self-test.json'), JSON.stringify(result, null, 2));
        fs.writeFileSync(path.join(output, 'demo.png'), (await win.webContents.capturePage()).toPNG());
      }
      console.log(JSON.stringify(result));
      cleanup(); app.exit(passed ? 0 : 1);
    } catch (error) { console.error(error); cleanup(); app.exit(1); }
  }
});
