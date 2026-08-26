import {
  Activity,
  ArrowUpRight,
  Clock3,
  MousePointerClick,
  RefreshCw,
  Smartphone,
  UsersRound,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import {
  fetchDevStats,
  formatDuration,
  humanizeFeatureCode,
} from '../services/siteAnalytics'
import type { DevStats } from '../services/siteAnalytics'

const ranges = [7, 30, 90] as const
type StatsRange = (typeof ranges)[number]

function appHomeHref() {
  return window.location.pathname.replace(/devstats\/?$/, '') || '/'
}

function formatCompact(value: number) {
  return new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function formatDay(value: string, range: StatsRange) {
  const date = new Date(`${value}T00:00:00`)
  return new Intl.DateTimeFormat('en', range === 7
    ? { weekday: 'short' }
    : { month: 'short', day: 'numeric' }).format(date)
}

export function DevStatsPage() {
  const [range, setRange] = useState<StatsRange>(30)
  const [stats, setStats] = useState<DevStats>()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string>()
  const [refreshKey, setRefreshKey] = useState(0)

  const loadStats = useCallback(() => setRefreshKey((current) => current + 1), [])

  useEffect(() => {
    let current = true
    setLoading(true)
    setError(undefined)
    void fetchDevStats(range)
      .then((result) => {
        if (current) setStats(result)
      })
      .catch((loadError: unknown) => {
        if (!current) return
        setStats(undefined)
        setError(loadError instanceof Error ? loadError.message : 'Analytics could not be loaded.')
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => {
      current = false
    }
  }, [range, refreshKey])

  const maxVisitors = useMemo(
    () => Math.max(1, ...(stats?.daily.map((day) => day.visitors) ?? [])),
    [stats],
  )
  const maxFeatureUses = Math.max(1, ...(stats?.features.map((feature) => feature.uses) ?? []))
  const maxPageViews = Math.max(1, ...(stats?.pages.map((page) => page.views) ?? []))
  const totalDeviceSessions = stats?.devices.reduce((sum, device) => sum + device.sessions, 0) ?? 0
  const hasData = Boolean(stats && stats.totals.sessions > 0)

  return (
    <main className="devstats-page">
      <header className="devstats-header">
        <a className="devstats-brand" href={appHomeHref()}>
          SỌRT RÁC <ArrowUpRight size={16} aria-hidden="true" />
        </a>
        <div className="devstats-header-actions">
          <div className="devstats-range" aria-label="Statistics date range">
            {ranges.map((days) => (
              <button
                type="button"
                key={days}
                className={range === days ? 'active' : ''}
                aria-pressed={range === days}
                onClick={() => setRange(days)}
              >
                {days}D
              </button>
            ))}
          </div>
          <button type="button" className="devstats-refresh" onClick={loadStats} disabled={loading} aria-label="Refresh statistics">
            <RefreshCw size={17} className={loading ? 'spinning' : ''} aria-hidden="true" />
          </button>
        </div>
      </header>

      <section className="devstats-intro">
        <p className="devstats-kicker">Field telemetry / aggregate view<span className="vi-note">Dữ liệu sử dụng tổng hợp</span></p>
        <h1>How people use<br /><em>the sorter.</em><span className="vi-note">Cách mọi người sử dụng công cụ phân loại</span></h1>
        <p className="devstats-intro-copy">
          Anonymous, privacy-minimized signals from real sessions. Dashboard visits are excluded from every figure below.
          <span className="vi-note">Dữ liệu ẩn danh, tối giản quyền riêng tư từ các phiên sử dụng thật. Lượt xem trang thống kê không được tính.</span>
        </p>
      </section>

      {loading && !stats ? <DevStatsLoading /> : null}

      {error ? (
        <section className="devstats-message devstats-error" role="alert">
          <p className="devstats-kicker">Connection needed<span className="vi-note">Cần kết nối</span></p>
          <h2>The statistics endpoint is not ready.<span className="vi-note">Điểm kết nối thống kê chưa sẵn sàng.</span></h2>
          <p>{error}</p>
          <p>Apply Supabase migration 005 to enable anonymous collection and aggregate reads.<span className="vi-note">Chạy Supabase migration 005 để bật thu thập ẩn danh và đọc dữ liệu tổng hợp.</span></p>
          <button type="button" onClick={loadStats}>Try again<span className="vi-note">Thử lại</span></button>
        </section>
      ) : null}

      {!loading && stats && !hasData ? (
        <section className="devstats-message">
          <p className="devstats-kicker">Ready to collect<span className="vi-note">Sẵn sàng thu thập</span></p>
          <h2>No tracked visits in this period yet.<span className="vi-note">Chưa có lượt truy cập nào trong khoảng thời gian này.</span></h2>
          <p>Once people use the deployed sorter, daily visitors, active time, and feature activity will appear here.<span className="vi-note">Khi người dùng trải nghiệm bản đã triển khai, lượt truy cập, thời gian hoạt động và thao tác tính năng sẽ xuất hiện tại đây.</span></p>
        </section>
      ) : null}

      {stats && hasData ? (
        <>
          <section className="devstats-kpi-grid" aria-label="Key metrics">
            <MetricCard icon={<UsersRound />} label="Visitors" labelVi="Người truy cập" value={formatCompact(stats.totals.visitors)} note={`Unique browsers / ${range} days`} noteVi={`Trình duyệt riêng biệt / ${range} ngày`} tone="orange" />
            <MetricCard icon={<Activity />} label="Sessions" labelVi="Phiên sử dụng" value={formatCompact(stats.totals.sessions)} note="Tracked site visits" noteVi="Lượt truy cập được ghi nhận" tone="blue" />
            <MetricCard icon={<Clock3 />} label="Avg. active time" labelVi="Thời gian hoạt động TB" value={formatDuration(stats.totals.avgActiveSeconds)} note="Visible, engaged time" noteVi="Thời gian tương tác thực" tone="yellow" />
            <MetricCard icon={<MousePointerClick />} label="Feature actions" labelVi="Thao tác tính năng" value={formatCompact(stats.totals.featureUses)} note="Scans, uploads, feedback + more" noteVi="Quét, tải ảnh, phản hồi và hơn thế nữa" tone="red" />
          </section>

          <section className="devstats-dashboard-grid">
            <article className="devstats-panel devstats-traffic-panel">
              <PanelHeader index="01" title="Daily visitors" titleVi="Người truy cập mỗi ngày" meta={`${range}-day view`} metaVi={`Trong ${range} ngày`} />
              <div className={`devstats-bars range-${range}`} role="img" aria-label="Daily unique visitors bar chart">
                {stats.daily.map((day, index) => (
                  <div className="devstats-bar-column" key={day.date} title={`${formatDay(day.date, range)}: ${day.visitors} visitors`}>
                    <span className="devstats-bar-value">{day.visitors}</span>
                    <span className="devstats-bar-track">
                      <i style={{ height: `${Math.max(4, (day.visitors / maxVisitors) * 100)}%` }} />
                    </span>
                    {(range === 7 || index === 0 || index === stats.daily.length - 1 || index % Math.ceil(stats.daily.length / 5) === 0) ? (
                      <small>{formatDay(day.date, range)}</small>
                    ) : <small aria-hidden="true">&nbsp;</small>}
                  </div>
                ))}
              </div>
            </article>

            <article className="devstats-panel">
              <PanelHeader index="02" title="Top features" titleVi="Tính năng phổ biến" meta="By action count" metaVi="Theo số thao tác" />
              <div className="devstats-ranking">
                {stats.features.map((feature, index) => (
                  <div className="devstats-rank-row" key={feature.code}>
                    <span className="devstats-rank-index">{String(index + 1).padStart(2, '0')}</span>
                    <div>
                      <div className="devstats-rank-label">
                        <strong>{humanizeFeatureCode(feature.code)}</strong>
                        <span>{formatCompact(feature.uses)}</span>
                      </div>
                      <span className="devstats-progress"><i style={{ width: `${(feature.uses / maxFeatureUses) * 100}%` }} /></span>
                    </div>
                  </div>
                ))}
              </div>
            </article>

            <article className="devstats-panel">
              <PanelHeader index="03" title="Top pages" titleVi="Trang phổ biến" meta="By page views" metaVi="Theo lượt xem" />
              <div className="devstats-page-list">
                {stats.pages.map((page) => (
                  <div key={page.path}>
                    <span className="devstats-page-path" title={page.path}>{friendlyPath(page.path)}</span>
                    <span className="devstats-page-count">{formatCompact(page.views)}</span>
                    <i style={{ width: `${(page.views / maxPageViews) * 100}%` }} />
                  </div>
                ))}
              </div>
            </article>

            <article className="devstats-panel">
              <PanelHeader index="04" title="Device mix" titleVi="Thiết bị sử dụng" meta="By sessions" metaVi="Theo phiên" />
              <div className="devstats-device-list">
                {stats.devices.map((device) => {
                  const percentage = totalDeviceSessions ? Math.round((device.sessions / totalDeviceSessions) * 100) : 0
                  return (
                    <div key={device.category}>
                      <span className="devstats-device-icon"><Smartphone size={18} aria-hidden="true" /></span>
                      <span><strong>{humanizeFeatureCode(device.category)}</strong><small>{formatCompact(device.sessions)} sessions</small></span>
                      <b>{percentage}%</b>
                    </div>
                  )
                })}
              </div>
            </article>

            <article className="devstats-panel devstats-sources-panel">
              <PanelHeader index="05" title="Traffic sources" titleVi="Nguồn truy cập" meta="Referral host only" metaVi="Chỉ hiển thị tên miền giới thiệu" />
              <div className="devstats-source-list">
                {stats.sources.map((source) => (
                  <div key={source.host}>
                    <span>{source.host}</span>
                    <strong>{formatCompact(source.sessions)}</strong>
                  </div>
                ))}
              </div>
            </article>
          </section>

          <footer className="devstats-footer">
            <p>Last updated {new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(stats.generatedAt))}<span className="vi-note">Cập nhật gần nhất</span></p>
            <p>Daily totals use Vietnam time (UTC+7). No names, images, precise device fingerprints, or raw visitor records are shown.<span className="vi-note">Tổng số theo ngày dùng giờ Việt Nam (UTC+7). Không hiển thị tên, hình ảnh, dấu vân tay thiết bị chi tiết hoặc dữ liệu thô của người truy cập.</span></p>
          </footer>
        </>
      ) : null}
    </main>
  )
}

function MetricCard({ icon, label, labelVi, value, note, noteVi, tone }: { icon: ReactNode; label: string; labelVi: string; value: string; note: string; noteVi: string; tone: string }) {
  return (
    <article className={`devstats-kpi tone-${tone}`}>
      <span className="devstats-kpi-icon">{icon}</span>
      <span className="devstats-kpi-label">{label}<span className="vi-note">{labelVi}</span></span>
      <strong>{value}</strong>
      <small>{note}<span className="vi-note">{noteVi}</span></small>
    </article>
  )
}

function PanelHeader({ index, title, titleVi, meta, metaVi }: { index: string; title: string; titleVi: string; meta: string; metaVi: string }) {
  return (
    <header className="devstats-panel-header">
      <span>{index}</span>
      <h2>{title}<span className="vi-note">{titleVi}</span></h2>
      <small>{meta}<span className="vi-note">{metaVi}</span></small>
    </header>
  )
}

function friendlyPath(path: string) {
  const hashRoute = path.split('#')[1] || '/'
  if (hashRoute === '/') return 'Waste scan'
  return humanizeFeatureCode(hashRoute.replace(/^\//, '').replace(/\//g, '_'))
}

function DevStatsLoading() {
  return (
    <section className="devstats-loading" aria-label="Loading statistics" aria-live="polite">
      <span>Loading aggregate data<span className="vi-note">Đang tải dữ liệu tổng hợp</span></span>
      <i /><i /><i /><i />
    </section>
  )
}
