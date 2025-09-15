import React from 'react'
import { Link } from 'react-router-dom'

export default function Navbar() {
  return (
    <nav className="navbar navbar-dark bg-dark mb-4">
      <div className="container d-flex justify-content-between">
        <Link className="navbar-brand" to="/">Book Snippets</Link>
        <Link className="btn btn-sm btn-primary" to="/new">New</Link>
      </div>
    </nav>
  )
}
