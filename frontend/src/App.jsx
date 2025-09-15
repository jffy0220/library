import React from 'react'
import { Routes, Route } from 'react-router-dom'
import Navbar from './components/Navbar'
import List from './pages/List'
import NewSnippet from './pages/NewSnippet'
import ViewSnippet from './pages/ViewSnippet'   // <-- add

export default function App() {
  return (
    <>
      <Navbar />
      <div className="container">
        <Routes>
          <Route path="/" element={<List />} />
          <Route path="/new" element={<NewSnippet />} />
          <Route path="/snippet/:id" element={<ViewSnippet />} />  {/* <-- add */}
        </Routes>
      </div>
    </>
  )
}
