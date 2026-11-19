import type { AssistantResult, EnergyResult, RiskAssessment, RiskMatrix, Twin } from './types'

const isPages = import.meta.env.VITE_DEPLOY_TARGET === 'pages'
const apiBase = (import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '')
export const hasBackend = !isPages || Boolean(apiBase)
export const publishedReplay = isPages && !hasBackend

export type RiskInput = { hazard: string; probability: number; severity: number; note: string; save: boolean }
export type EnergyOptions = { flows: number[]; delivery_pressures: number[]; cases: Record<string, EnergyResult> }

async function read<T>(url: string, init?: RequestInit): Promise<T> {
  const result = await fetch(url, init)
  if (!result.ok) {
    const body = await result.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${result.status})`)
  }
  return result.json()
}

function asset<T>(name: string, init?: RequestInit): Promise<T> {
  return read(`${import.meta.env.BASE_URL}published/${name}.json`, init)
}

function api<T>(path: string, init?: RequestInit): Promise<T> {
  return read(`${apiBase}/api/${path}`, init)
}

function post<T>(path: string, input: object): Promise<T> {
  return api(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) })
}

export function loadTwin(source: string, signal?: AbortSignal): Promise<Twin> {
  if (publishedReplay) return asset(`demo/${source}`, { signal })
  return api(source === 'live' ? 'dashboard' : `demo/${source}`, { signal })
}

export function loadEnergyOptions(): Promise<EnergyOptions> {
  return asset('energy')
}

export async function calculateEnergy(flow: number, pressure: number, hours: number): Promise<EnergyResult> {
  if (publishedReplay) {
    const { cases } = await loadEnergyOptions()
    const result = cases[`${flow}:${pressure}`]
    if (!result) throw new Error('Choose a published flow and delivery pressure.')
    return {
      ...result, duration_h: hours,
      estimated_savings_kwh: result.estimated_savings_kwh === null ? null : result.estimated_savings_kwh * hours,
    }
  }
  const query = new URLSearchParams({ flow: String(flow), delivery_bar: String(pressure), hours: String(hours) })
  return api(`energy?${query}`)
}

export function loadRisk(): Promise<RiskMatrix> {
  return publishedReplay ? asset('risk') : api('risk')
}

export async function calculateRisk(input: RiskInput, matrix: RiskMatrix): Promise<RiskAssessment> {
  if (!publishedReplay) return post('risk', input)
  const result = matrix.matrix[input.probability - 1]?.[input.severity - 1]
  if (!result || !matrix.hazards.includes(input.hazard)) throw new Error('Choose a hazard and scores from 1 to 5.')
  return { ...result, hazard: input.hazard }
}

const stopWords = new Set(['what', 'when', 'where', 'which', 'with', 'does', 'about', 'there', 'from', 'this', 'that', 'have', 'could', 'will', 'would', 'should', 'matter'])
function terms(text: string) {
  return new Set((text.toLowerCase().match(/[a-z]{3,}/g) ?? [])
    .map(word => word.endsWith('s') && word.length > 4 ? word.slice(0, -1) : word)
    .filter(word => word !== 'how' && word !== 'why' && !stopWords.has(word)))
}

export async function askCopilot(question: string, source: string, snapshot: Twin): Promise<AssistantResult> {
  if (!publishedReplay) return post('copilot', { question, scenario: source === 'live' ? null : source })
  const references = await asset<AssistantResult['sources']>('references')
  const query = terms(question)
  const sources = references.map(reference => {
    const words = terms(reference.excerpt)
    const matches = [...query].filter(word => words.has(word)).length
    return { reference, matches, score: matches / Math.sqrt(Math.max(words.size, 1)) }
  }).filter(entry => entry.matches >= Math.min(2, query.size) && entry.matches > 0)
    .sort((left, right) => right.score - left.score).slice(0, 3).map(entry => entry.reference)
  const simulated_context = `Simulated run ${snapshot.run_id}. ${snapshot.detection?.classification ?? 'No classification'}. `
    + (snapshot.average_pressure_pa == null ? 'Average pressure unavailable.' : `Average pressure ${(snapshot.average_pressure_pa / 1e5).toFixed(2)} bar(a).`)
  return {
    mode: sources.length ? 'excerpts' : 'insufficient evidence', simulated_context, sources,
    answer: sources.length ? sources.map((source, index) => {
      const sentences = source.excerpt.split(/(?<=[.!?])\s+|\n+/).filter(line => !line.startsWith('#') && line.length > 25)
      const [excerpt] = sentences.sort((left, right) => {
        const leftTerms = terms(left)
        const rightTerms = terms(right)
        return [...query].reduce((score, word) => score + Number(rightTerms.has(word)) - Number(leftTerms.has(word)), 0)
      })
      return `${excerpt ?? source.title} [${index + 1}]`
    }).join('\n\n') : 'The published engineering references do not contain enough evidence for this question.',
  }
}
