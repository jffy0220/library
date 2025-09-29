import React from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import 'bootstrap/dist/css/bootstrap.min.css'
import './styles/theme.css'

createRoot(document.getElementById('root')).render(
  <BrowserRouter>
    <App />
  </BrowserRouter>
)

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/service-worker.js')
      .then((registration) => {
        navigator.serviceWorker.ready.then((readyRegistration) => {
          readyRegistration.active?.postMessage('processQueue')
        })
        window.addEventListener('online', () => {
          registration.active?.postMessage('processQueue')
        })
      })
      .catch((error) => {
        console.error('Service worker registration failed', error)
      })
  })
}
