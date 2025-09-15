import axios from 'axios'
const api = axios.create({ baseURL: '/api' })

export async function listSnippets() {
  const { data } = await api.get('/snippets')
  return data
}
export async function createSnippet(payload) {
  const { data } = await api.post('/snippets', payload)
  return data
}
export async function getSnippet(id) {
  const { data } = await api.get(`/snippets/${id}`)
  return data
}

export default api
