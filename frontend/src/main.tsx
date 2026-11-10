import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.tsx'
import './index.css'

const savedTheme = localStorage.getItem('warik_theme');
document.documentElement.dataset.theme = savedTheme === 'dark' ? 'dark' : 'light';
document.documentElement.style.setProperty('--warik-accent', localStorage.getItem('warik_accent') || '#8b5cf6');
document.documentElement.dataset.fontSize = (localStorage.getItem('warik_font_size') || 'Regular').toLowerCase();
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
)
