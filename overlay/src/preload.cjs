// Bridge between the overlay pages and main.mjs. Pages never touch Node or the network directly.
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('kin', {
  start: (opts) => ipcRenderer.invoke('kin:start', opts),
  stop: () => ipcRenderer.invoke('kin:stop'),
  graph: (familyId) => ipcRenderer.invoke('kin:graph', familyId),
  families: () => ipcRenderer.invoke('kin:families'),
  languages: () => ipcRenderer.invoke('kin:languages'),
  relations: () => ipcRenderer.invoke('kin:relations'),
  suggest: (term, familyId) => ipcRenderer.invoke('kin:suggest', term, familyId),
  setup: (body) => ipcRenderer.invoke('kin:setup', body),
  addRelative: (body) => ipcRenderer.invoke('kin:add-relative', body),
  selectFamily: (familyId) => ipcRenderer.send('kin:family-selected', familyId),
  text: (line) => ipcRenderer.send('kin:text', line),
  mouse: (inside) => ipcRenderer.send('kin:mouse', inside),
  cards: (count) => ipcRenderer.send('kin:cards', count),
  pcm: (buf) => ipcRenderer.send('kin:pcm', buf),
  captureError: (msg) => ipcRenderer.send('kin:capture-error', msg),
  quit: () => ipcRenderer.send('kin:quit'),
  on: (fn) => ipcRenderer.on('kin:event', (_e, msg) => fn(msg)),
})
