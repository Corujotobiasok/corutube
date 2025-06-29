const { app, BrowserWindow, ipcMain } = require('electron');
const path = require('path');
const { spawn } = require('child_process');

let flaskProcess = null;
let mainWindow = null;
const FLASK_PORT = 5000;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 600,
    resizable: false,
    maximizable: false,
    fullscreenable: false,
    frame: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });

  mainWindow.loadURL(`http://localhost:${FLASK_PORT}`);
}

// 🧠 Recibe los comandos de los botones
ipcMain.on('window-control', (event, action) => {
  if (!mainWindow) return;

  switch (action) {
    case 'minimize':
      mainWindow.minimize();
      break;
    case 'maximize':
      if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
      } else {
        mainWindow.maximize();
      }
      break;
    case 'close':
      mainWindow.close();
      break;
  }
});

function startFlask() {
  const scriptPath = path.join(__dirname, 'app.py');
  flaskProcess = spawn('python', [scriptPath]);

  flaskProcess.stdout.on('data', (data) => console.log(`Flask: ${data}`));
  flaskProcess.stderr.on('data', (data) => console.error(`Flask error: ${data}`));
}

app.whenReady().then(() => {
  startFlask();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('before-quit', () => {
  if (flaskProcess) flaskProcess.kill();
});