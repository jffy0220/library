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

export async function updateSnippet(id, payload) {
  const { data } = await api.patch(`/snippets/${id}`, payload)
  return data
}

export async function deleteSnippet(id) {
  const { data } = await api.delete(`/snippets/${id}`)
  return data
}

export async function listSnippetComments(snippetId) {
  const { data } = await api.get(`/snippets/${snippetId}/comments`)
  return data
}

export async function createSnippetComment(snippetId, payload) {
  const { data } = await api.post(`/snippets/${snippetId}/comments`, payload)
  return data
}

export async function updateComment(commentId, payload) {
  const { data } = await api.patch(`/comments/${commentId}`, payload)
  return data
}

export async function deleteComment(commentId) {
  const { data } = await api.delete(`/comments/${commentId}`)
  return data
}

export async function voteComment(commentId, payload) {
  const { data } = await api.post(`/comments/${commentId}/vote`, payload)
  return data
}

export async function reportSnippet(snippetId, payload) {
  const { data } = await api.post(`/snippets/${snippetId}/report`, payload)
  return data
}

export async function reportComment(commentId, payload) {
  const { data } = await api.post(`/comments/${commentId}/report`, payload)
  return data
}

export async function listModerationReports() {
  const { data } = await api.get('/moderation/reports')
  return data
}

export async function resolveModerationReport(reportId, payload) {
  const { data } = await api.post(`/moderation/reports/${reportId}/resolve`, payload)
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