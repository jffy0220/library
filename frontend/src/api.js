import axios from 'axios'

const api = axios.create({ baseURL: '/api', withCredentials: true })

let unauthorizedHandler = null

export function setUnauthorizedHandler(handler) {
  unauthorizedHandler = handler
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401 && unauthorizedHandler) {
      unauthorizedHandler()
    }
    return Promise.reject(error)
  }
)

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

export async function login(credentials) {
  const { data } = await api.post('/auth/login', credentials)
  return data
}

export async function logout() {
  await api.post('/auth/logout')
}

export async function fetchCurrentUser() {
  const { data } = await api.get('/auth/me')
  return data
}

export default api