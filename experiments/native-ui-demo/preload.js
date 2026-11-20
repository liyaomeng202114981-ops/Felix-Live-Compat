// SPDX-License-Identifier: BSD-3-Clause
// Copyright 2026 Felix Li, with OpenAI Codex assistance.
const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('previewDemo', {
  onFrame: callback => ipcRenderer.on('frame', (_event, data) => callback(data)),
  acknowledge: () => ipcRenderer.send('frame-ack'),
  pause: () => ipcRenderer.send('toggle-pause'),
  onStatus: callback => ipcRenderer.on('backend-state', (_event, state) => callback(state))
});
