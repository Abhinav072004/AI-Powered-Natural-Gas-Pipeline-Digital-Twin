import { StrictMode, useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { createRoot } from 'react-dom/client'
import {
  Activity, ArrowDownUp, ArrowLeftRight, ArrowUpRight, Bot, CircleGauge, Clock3,
  Droplets, GitBranch, LayoutDashboard, Radio, Search, ShieldAlert, Waypoints, Wrench, Zap,
} from 'lucide-react'
import {
  CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'
import type { AssistantResult, EnergyResult, Event, RiskAssessment, RiskMatrix, Twin } from './types'
import { askCopilot, calculateEnergy, calculateRisk, hasBackend, loadEnergyOptions, loadRisk, loadTwin, publishedReplay } from './data'
import type { EnergyOptions } from './data'
import './style.css'

const nav = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'twin', label: 'Digital twin', icon: Waypoints },
  { key: 'leaks', label: 'Leak detection', icon: Droplets },
  { key: 'energy', label: 'Energy optimization', icon: Zap },
  { key: 'maintenance', label: 'Maintenance', icon: Wrench },
  { key: 'risk', label: 'Safety & risk', icon: ShieldAlert },
  { key: 'copilot', label: 'Engineering copilot', icon: Bot },
] as const
type Page = typeof nav[number]['key']

const names: Record<string, string> = {
  normal: 'Normal operation', demand_increase: 'Demand increase', pressure_drop: 'Pressure drop',
  large_leak: 'Large simulated leak', small_leak: 'Small simulated leak', pressure_drift: 'Pressure sensor drift',
  flow_fault: 'Flow meter fault', compressor_degradation: 'Compressor degradation',
  communication_failure: 'Communication failure', valve_abnormal: 'Abnormal valve indication',
}
const fmt = (n: number | null | undefined, digits = 1) => n == null ? '—' : n.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits })
const bar = (n: number | null | undefined) => n == null ? null : n / 1e5
const mw = (n: number | null | undefined) => n == null ? null : n / 1e6
const pct = (n: number | null | undefined) => n == null ? '—' : fmt(n * 100, 0) + '%'
const clock = (stamp: string) => new Date(stamp).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' })
const titleCase = (value: string) => value.charAt(0).toUpperCase() + value.slice(1)

function Card({ title, detail, children, className = '' }: { title: string; detail?: string; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><header><h2>{title}</h2>{detail && <p>{detail}</p>}</header>{children}</section>
}

function Metric({ label, value, unit, icon: Icon, note }: {
  label: string; value: string; unit?: string; icon: typeof Activity; note?: string
}) {
  return <section className="panel metric"><div className="metric-heading"><span>{label}</span><Icon size={17} /></div>
    <strong>{value}{unit && <small>{unit}</small>}</strong>{note && <span className="muted">{note}</span>}</section>
}

function Chart({ data, lines, unit, x = 'name' }: {
  data: object[]; lines: { key: string; label: string; color: string; dashed?: boolean }[]; unit: string; x?: string
}) {
  if (!data.length) return <p className="empty">Waiting for chart data.</p>
  return <>
    <div className="legend">{lines.map(line => <span key={line.key}><i style={{ background: line.color }} />{line.label}</span>)}</div>
    <div className="chart"><ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 12, right: 15, bottom: 0, left: -15 }}>
        <CartesianGrid stroke="#e8edf2" vertical={false} />
        <XAxis dataKey={x} tickLine={false} axisLine={false} minTickGap={18} tick={{ fill: '#5b6c7d', fontSize: 11 }} />
        <YAxis domain={['auto', 'auto']} tickLine={false} axisLine={false} tick={{ fill: '#5b6c7d', fontSize: 11 }} width={60} tickFormatter={value => fmt(value)} />
        <Tooltip formatter={(value, label) => [`${fmt(typeof value === 'number' ? value : null, 2)} ${unit}`, label]} />
        {lines.map(line => <Line key={line.key} dataKey={line.key} name={line.label} stroke={line.color}
          strokeWidth={2.5} strokeDasharray={line.dashed ? '6 5' : undefined} dot={data.length <= 9} isAnimationActive={false} />)}
      </LineChart>
    </ResponsiveContainer></div>
  </>
}

function Schematic({ data }: { data: Twin }) {
  const [selected, select] = useState(1)
  const segment = data.segments.find(s => s.segment_id === selected) || data.segments[0]
  return <Card title="Pipeline schematic" detail="Virtual stations · distances along the simulated centerline">
    <div className="route"><span className="route-end"><Radio size={15} /> Inlet</span>
      <div className="route-segments">{data.segments.map(s => <button key={s.segment_id}
        className={`route-node ${s.segment_id === segment.segment_id ? 'chosen' : ''} ${s.segment_id === data.detection?.estimated_segment ? 'alert' : ''}`}
        aria-pressed={s.segment_id === segment.segment_id} onClick={() => select(s.segment_id)}>
        <span>S{s.segment_id}</span><small>{fmt(s.end_km, s.segment_id === data.segments.length ? 1 : 0)} km</small>
      </button>)}</div><span className="route-end"><ArrowUpRight size={15} /> Delivery</span>
    </div>
    <dl className="segment-detail">
      <div><dt>Segment {segment.segment_id}</dt><dd>{fmt(segment.start_km)}–{fmt(segment.end_km, 3)} km</dd></div>
      <div><dt>Measured outlet</dt><dd>{fmt(bar(segment.observed_outlet_pa), 2)} bar(a)</dd></div>
      <div><dt>Baseline velocity</dt><dd>{fmt(segment.velocity_m_s, 2)} m/s</dd></div>
      <div><dt>Baseline mass flow</dt><dd>{fmt(segment.mass_flow_kg_s)} kg/s</dd></div>
    </dl>
  </Card>
}

function Events({ events }: { events: Event[] }) {
  if (!events.length) return <p className="empty">No anomaly samples in this window.</p>
  return <div className="table-wrap"><table><thead><tr><th>Time (UTC)</th><th>Classification</th><th>Segment</th><th>Residual (kg/s)</th></tr></thead>
    <tbody>{events.slice(-12).reverse().map(event => <tr key={event.observed_at}><td>{clock(event.observed_at)}</td>
      <td>{titleCase(event.classification)}</td><td>{event.estimated_segment ?? '—'}</td><td>{fmt(event.residual_kg_s, 2)}</td></tr>)}</tbody></table></div>
}

const teal = '#067d74'
const navy = '#233f75'
const amber = '#ad630c'

function Overview({ data, go }: { data: Twin; go: (page: Page) => void }) {
  const flow = data.latest_readings.find(r => r.sensor_id === 'FT-102')?.value
  const alert = data.detection?.classification
  const currentAlerts = alert && alert !== 'normal operation' ? '1' : alert ? '0' : '—'
  const latestHealth = data.maintenance.filter(item => item.health_score != null)
  const health = latestHealth.length ? Math.min(...latestHealth.map(item => item.health_score!)) : null
  return <div className="stack">
    <div className="intro"><div><p className="location">BOKARO–ANGUL PIPELINE · ODISHA SECTION</p><h1>Operations overview</h1>
      <p>Track simulated pressure, delivery and equipment condition across eight virtual segments.</p></div><Waypoints size={56} strokeWidth={1.1} aria-hidden="true" /></div>
    <div className="metrics">
      <Metric icon={GitBranch} label="Pipeline length" value={fmt(data.case_study.length_km, 3)} unit="km" note="8 virtual segments" />
      <Metric icon={CircleGauge} label="Average pressure" value={fmt(bar(data.average_pressure_pa), 2)} unit="bar(a)" note="Available transmitters" />
      <Metric icon={ArrowLeftRight} label="Delivery flow" value={fmt(flow)} unit="kg/s" note="FT-102 · outlet meter" />
      <Metric icon={Activity} label="Active anomaly" value={currentAlerts} note={alert ? titleCase(alert) : 'Awaiting readings'} />
    </div>
    <Schematic data={data} />
    <div className="cols">
      <Card title="Pressure trend" detail="Inlet and delivery pressure · bar(a)"><Chart data={data.trends.map(r => ({ name: clock(r.observed_at), inlet: bar(r.inlet_pressure_pa), outlet: bar(r.outlet_pressure_pa) }))}
        lines={[{ key: 'inlet', label: 'Inlet', color: teal }, { key: 'outlet', label: 'Delivery', color: navy }]} unit="bar(a)" /></Card>
      <Card title="Equipment condition" detail="Lowest available health score">
        <div className="hero-number">{fmt(health, 0)}<small> / 100</small></div>
        <ul className="equipment-list">{data.maintenance.map(item => <li key={item.equipment}><span>{titleCase(item.equipment)}</span><strong>{fmt(item.health_score, 0)}</strong></li>)}</ul>
        <button className="text-button" onClick={() => go('maintenance')}>View equipment <ArrowUpRight size={15} /></button>
      </Card>
    </div>
  </div>
}

function TwinPage({ data }: { data: Twin }) {
  const segments = data.segments.map(s => ({ name: `S${s.segment_id}`, measured: bar(s.observed_outlet_pa), baseline: bar(s.outlet_pressure_pa_absolute), flow: s.mass_flow_kg_s }))
  return <div className="stack"><h1>Pipeline digital twin</h1><Schematic data={data} />
    <div className="cols balanced">
      <Card title="Segment pressure" detail="Outlet pressure by segment · bar(a)"><Chart data={segments} unit="bar(a)" lines={[
        { key: 'measured', label: 'Observed', color: teal }, { key: 'baseline', label: 'Baseline', color: navy, dashed: true },
      ]} /></Card>
      <Card title="Flow distribution" detail="Modeled steady mass flow across segments · kg/s"><Chart data={segments} unit="kg/s" lines={[{ key: 'flow', label: 'Steady baseline', color: teal }]}/></Card>
    </div>
    <Card title="Sensor readings"><div className="table-wrap"><table><thead><tr><th>Sensor</th><th>Boundary</th><th>Reading</th><th>Quality</th></tr></thead>
      <tbody>{data.latest_readings.map(r => <tr key={r.sensor_id}><td>{r.sensor_id}</td><td>{r.boundary_index ?? '—'}</td><td>{r.unit === 'boolean' && r.value != null ? (r.value ? 'Open' : 'Closed') : r.value == null ? '—' : `${fmt(r.value, 2)} ${r.unit}`}</td><td>{titleCase(r.quality)}</td></tr>)}</tbody></table>
      {!data.latest_readings.length && <p className="empty">No current sensor readings.</p>}</div></Card>
  </div>
}

function Leaks({ data }: { data: Twin }) {
  const d = data.detection
  return <div className="stack"><h1>Leak detection</h1><div className="metrics">
    <Metric icon={Activity} label="Classification" value={d ? titleCase(d.classification) : '—'} note={data.model_loaded ? 'ML and physics' : 'Physics baseline'} />
    <Metric icon={Droplets} label="Leak probability" value={pct(d?.leak_probability)} note="Synthetic classifier score" />
    <Metric icon={Waypoints} label="Estimated segment" value={d?.estimated_segment ? `S${d.estimated_segment}` : '—'} note="Localization estimate" />
    <Metric icon={Radio} label="Telemetry coverage" value={pct(d?.availability)} note={data.inference_ms == null ? undefined : `${fmt(data.inference_ms, 2)} ms latest inference`} />
  </div><div className="cols balanced">
    <Card title="Mass-balance residual" detail="Inflow minus delivery and observed inventory change">
      <Chart data={data.trends.map(t => ({ name: clock(t.observed_at), residual: t.residual_kg_s }))} unit="kg/s" lines={[{ key: 'residual', label: 'Smoothed residual', color: teal }]} />
    </Card>
    <Card title="Delivery pressure deviation" detail="Observed outlet minus the flow-adjusted reference">
      <Chart data={data.trends.map(t => ({ name: clock(t.observed_at), deviation: bar(t.pressure_deviation_pa) }))} unit="bar" lines={[{ key: 'deviation', label: 'Pressure difference', color: amber }]} />
    </Card>
  </div><Card title="Event timeline"><Events events={data.events} /></Card></div>
}

function Energy({ data }: { data: Twin }) {
  const [result, setResult] = useState<EnergyResult | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  const [options, setOptions] = useState<EnergyOptions | null>(null)
  useEffect(() => {
    if (publishedReplay) loadEnergyOptions().then(setOptions).catch(err => setError(String(err)))
  }, [])
  async function calculate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const fields = new FormData(event.currentTarget)
    const flow = Number(fields.get('flow'))
    const pressure = Number(fields.get('delivery_bar'))
    const hours = Number(fields.get('hours'))
    setError(''); setPending(true)
    try { setResult(await calculateEnergy(flow, pressure, hours)) }
    catch (err) { setError(String(err)); setResult(null) }
    finally { setPending(false) }
  }
  return <div className="stack"><h1>Energy optimization</h1>
    <div className="cols">
      <Card title="Compressor power" detail="Observed simulated shaft power · MW"><Chart data={data.trends.map(t => ({ name: clock(t.observed_at), power: mw(t.power_w) }))} unit="MW" lines={[{ key: 'power', label: 'Shaft power', color: teal }]} /></Card>
      <Card title="Evaluate a scenario" detail="Fixed delivery flow with a minimum outlet pressure">
        <form className="form" onSubmit={calculate}>
          <label>Delivery flow (kg/s){publishedReplay
            ? options && <select name="flow" defaultValue="60">{options.flows.map(value => <option key={value}>{value}</option>)}</select>
            : <input name="flow" type="number" min="0.1" max="200" step="any" defaultValue="60" required />}</label>
          <label>Minimum delivery pressure (bar(a)){publishedReplay
            ? options && <select name="delivery_bar" defaultValue="45">{options.delivery_pressures.map(value => <option key={value}>{value}</option>)}</select>
            : <input name="delivery_bar" type="number" min="1" max="100" step="any" defaultValue="45" required />}</label>
          <label>Duration (hours)<input name="hours" type="number" min="0.1" max="720" step="any" defaultValue="1" required /></label>
          <button className="primary" disabled={pending || (publishedReplay && !options)}>{pending ? 'Calculating…' : 'Compare operating points'}</button>
        </form>
      </Card>
    </div>
    {error && <p className="notice" role="alert">{error}</p>}
    {result && <Card title="Simulated comparison" detail={result.status === 'feasible' ? 'Calculated at constant delivery flow' : 'No feasible operating point with the selected limits'}>
      <div className="table-wrap"><table><thead><tr><th>Operating point</th><th>Discharge (bar(a))</th><th>Delivery (bar(a))</th><th>Power (MW)</th></tr></thead>
        <tbody>{([['Configured baseline', result.baseline], ['Minimum-power scenario', result.optimized]] as const).map(([name, point]) => <tr key={name}>
          <td>{name}</td><td>{fmt(bar(point?.discharge_pa_absolute), 2)}</td><td>{fmt(bar(point?.delivery_pa_absolute), 2)}</td><td>{fmt(mw(point?.power_w), 3)}</td>
        </tr>)}</tbody></table></div>
      <p className="result">Estimated savings over {fmt(result.duration_h)} h: <strong>{fmt(result.estimated_savings_kwh)} kWh</strong></p>
    </Card>}
  </div>
}

function Maintenance({ data }: { data: Twin }) {
  return <div className="stack"><h1>Predictive maintenance</h1><Card title="Equipment priority" detail="Scored against a ten-sample synthetic failure window">
    <div className="table-wrap"><table><thead><tr><th>Equipment</th><th>Health / 100</th><th>Failure probability</th><th>Priority / 100</th><th>Inspection for review</th></tr></thead>
      <tbody>{data.maintenance.map(item => <tr key={item.equipment}><td>{titleCase(item.equipment)}</td>
        <td>{fmt(item.health_score, 0)}</td><td>{pct(item.failure_probability)}</td><td>{fmt(item.priority, 0)}</td><td>{item.inspection}</td></tr>)}</tbody>
    </table></div></Card>
    <Card title="Recent condition indicators" detail="Relative deviation from each virtual instrument's baseline">
      <Chart data={Array.from({ length: 5 }, (_, i) => Object.fromEntries([['name', `Sample ${i + 1}`], ...data.maintenance.map(item => [item.equipment, item.indicator_trend[i] ?? null])]))}
        unit="index" lines={data.maintenance.map((item, index) => ({ key: item.equipment, label: titleCase(item.equipment), color: [teal, amber, navy, '#7850a8', '#64748b'][index] }))} />
    </Card>
  </div>
}

function Risk({ data }: { data: Twin }) {
  const [matrix, setMatrix] = useState<RiskMatrix | null>(null)
  const [assessment, setAssessment] = useState<RiskAssessment | null>(null)
  const [scores, setScores] = useState({ p: 3, s: 3 })
  const [error, setError] = useState('')
  useEffect(() => { loadRisk().then(setMatrix).catch(err => setError(String(err))) }, [])
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!matrix) return
    const form = new FormData(event.currentTarget)
    const save = (event.nativeEvent as SubmitEvent).submitter?.getAttribute('name') === 'save'
    try {
      setError('')
      setAssessment(await calculateRisk({
        hazard: String(form.get('hazard')), probability: scores.p, severity: scores.s,
        note: String(form.get('note') ?? ''), save,
      }, matrix))
    } catch (err) { setError(String(err)) }
  }
  return <div className="stack"><h1>Safety &amp; risk</h1><div className="cols balanced">
    <Card title="Risk matrix" detail="Probability rows × consequence columns">
      {matrix && <div className="risk-grid"><span /><span>1</span><span>2</span><span>3</span><span>4</span><span>5</span>
        {matrix.matrix.map((row, rowIndex) => <div className="risk-row" key={rowIndex}><span>{rowIndex + 1}</span>{row.map(cell =>
          <button key={cell.severity} className={`risk-cell ${cell.level}`} aria-label={`Probability ${cell.probability}, severity ${cell.severity}: ${cell.level}`}
            aria-pressed={scores.p === cell.probability && scores.s === cell.severity} onClick={() => setScores({ p: cell.probability, s: cell.severity })}>{cell.score}</button>)}</div>)}
      </div>}
    </Card>
    <Card title="Assess an educational scenario">
      {matrix && <form className="form" onSubmit={submit}>
        <label>Hazard<select name="hazard">{matrix.hazards.map(h => <option value={h} key={h}>{titleCase(h)}</option>)}</select></label>
        <div className="fields"><label>Probability<input type="number" min="1" max="5" value={scores.p} onChange={e => setScores({ ...scores, p: +e.target.value })} required /></label>
          <label>Consequence<input type="number" min="1" max="5" value={scores.s} onChange={e => setScores({ ...scores, s: +e.target.value })} required /></label></div>
        {hasBackend && <label>Review note<input name="note" maxLength={1000} /></label>}
        <div className="actions"><button className="primary">Evaluate risk</button>{hasBackend && <button className="secondary" name="save">Save review</button>}</div>
      </form>}
      {error && <p className="notice" role="alert">{error}</p>}
      {assessment && <p className={`risk-result ${assessment.level}`}><strong>{titleCase(assessment.level)} · {assessment.score}/25</strong><br />{assessment.response}{assessment.review_id && ` · Review #${assessment.review_id}`}</p>}
    </Card>
  </div><Card title="Alarm history"><Events events={data.events} /></Card></div>
}

function Copilot({ source, data }: { source: string; data: Twin }) {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<AssistantResult | null>(null)
  const [error, setError] = useState('')
  const [pending, setPending] = useState(false)
  async function ask(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(''); setPending(true); setResult(null)
    try {
      setResult(await askCopilot(question, source, data))
    } catch (err) { setError(String(err)) }
    finally { setPending(false) }
  }
  const prompts = ['What is linepack and why does it matter?', 'How can I distinguish a leak from a sensor malfunction?', 'What can increase compressor power?']
  return <div className="stack"><h1>Engineering copilot</h1><Card title="Ask about the simulation" detail="Answers draw on the project references and the selected telemetry window.">
    <form className="question" onSubmit={ask}><label className="sr-only" htmlFor="question">Engineering question</label>
      <Search size={19} /><input id="question" minLength={5} maxLength={1000} required value={question} onChange={event => setQuestion(event.target.value)} placeholder="Enter an engineering question" />
      <button className="primary" disabled={pending}>{pending ? 'Retrieving…' : 'Ask'}</button></form>
    <div className="prompts">{prompts.map(p => <button key={p} type="button" onClick={() => setQuestion(p)}>{p}</button>)}</div>
    {error && <p className="notice" role="alert">{error}</p>}
  </Card>{result && <Card title="Response" detail={result.mode === 'generated' ? 'Generated using retrieved sources' : result.sources.length ? 'Retrieved source excerpts' : undefined}>
    <div className="answer">{result.answer}</div>
    {result.simulated_context && <p className="context"><strong>Simulation context</strong><br />{result.simulated_context}</p>}
    <h3>Sources</h3><ol className="sources">{result.sources.map((item, index) => <li key={index}><strong>{item.title}{item.page ? ` · p. ${item.page}` : ''}</strong>
      <div className="muted">{item.reference}</div><p>{item.excerpt}</p></li>)}</ol>
  </Card>}</div>
}

function getPage(): Page {
  const hash = window.location.hash.slice(1)
  return nav.find(item => item.key === hash)?.key || 'overview'
}

function App() {
  const [page, setPage] = useState<Page>(getPage)
  const [source, setSource] = useState('normal')
  const [snapshot, setSnapshot] = useState<{ source: string; data: Twin } | null>(null)
  const [error, setError] = useState('')
  const data = snapshot?.source === source ? snapshot.data : null
  useEffect(() => {
    function onHash() { setPage(getPage()) }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])
  useEffect(() => {
    const abort = new AbortController()
    let timer: number | undefined
    async function refresh() {
      try {
        const next = await loadTwin(source, abort.signal)
        if (!abort.signal.aborted) { setSnapshot({ source, data: next }); setError('') }
      } catch (err) { if (!abort.signal.aborted) setError(String(err)) }
      if (source === 'live' && !abort.signal.aborted) timer = window.setTimeout(refresh, 4000)
    }
    void refresh()
    return () => { abort.abort(); window.clearTimeout(timer) }
  }, [source])
  const go = (target: Page) => { window.location.hash = target }
  const status = data?.state === 'demo' ? (publishedReplay ? 'Published simulation' : 'Scenario replay') : data?.state === 'live' ? 'Live MQTT' : data?.state === 'stale' ? 'Telemetry stale' : 'Waiting for telemetry'
  return <div className="shell"><aside className="sidebar">
    <div className="brand"><span><Waypoints size={22} /></span><div>Pipeline Twin<small>SIMULATION WORKSPACE</small></div></div>
    <nav aria-label="Workspace views">{nav.map(({ key, label, icon: Icon }) =>
      <a key={key} href={`#${key}`} aria-current={page === key ? 'page' : undefined}><Icon size={17} />{label}</a>)}</nav>
    <div className="sidebar-bottom"><ShieldAlert size={17} /><span>Academic decision support<br /><small>Simulated data only</small></span></div>
  </aside><main>
    <div className="topbar"><span className={`status ${data?.state === 'stale' ? 'stale' : ''}`}><span />{status}</span>
      <div className="top-controls">{data?.observed_at && <time dateTime={data.observed_at}><Clock3 size={14} />{clock(data.observed_at)} UTC</time>}
        <label><ArrowDownUp size={15} /><span className="sr-only">Telemetry source</span><select value={source} onChange={e => { setError(''); setSource(e.target.value) }}>
          {hasBackend && <optgroup label="Telemetry"><option value="live">Live MQTT stream</option></optgroup>}
          <optgroup label="Scenario replay">{Object.entries(names).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</optgroup>
        </select></label></div>
    </div>
    <div className="content">
      {error && <p className="notice" role="alert">{error}</p>}
      {!data && !error && <p className="empty" role="status">Loading simulation…</p>}
      {data && (() => {
        switch (page) {
          case 'overview': return <Overview data={data} go={go} />
          case 'twin': return <TwinPage data={data} />
          case 'leaks': return <Leaks data={data} />
          case 'energy': return <Energy data={data} />
          case 'maintenance': return <Maintenance data={data} />
          case 'risk': return <Risk data={data} />
          case 'copilot': return <Copilot source={source} data={data} />
        }
      })()}
    </div>
  </main></div>
}

createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>)
