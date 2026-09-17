export async function getJSON(path) {
  const r = await fetch(path)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function postJSON(path, body) {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}
export async function requestJSON(method, path, body) {
  const r = await fetch(path, {
    method,
    headers: body === undefined ? {} : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) {
    let payload = null
    const text = await r.text()
    try { payload = JSON.parse(text) } catch { payload = { message: text } }
    const err = new Error(payload?.detail?.message || payload?.message || text)
    err.status = r.status
    err.payload = payload?.detail || payload
    throw err
  }
  return r.status === 204 ? null : r.json()
}
