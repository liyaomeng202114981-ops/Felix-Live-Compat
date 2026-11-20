// SPDX-License-Identifier: BSD-3-Clause
// Copyright 2026 Felix Li, with OpenAI Codex assistance.
const {contextBridge,ipcRenderer}=require('electron');
contextBridge.exposeInMainWorld('sdkBridge',{
  status:()=>ipcRenderer.invoke('sdk-status'), preview:()=>ipcRenderer.invoke('sdk-preview')});
